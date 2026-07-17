import unittest
import importlib
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import UUID
from unittest.mock import patch

from backend.app.core.contracts import Role
from backend.app.core.errors import AppError
module = importlib.import_module("backend.app.features.coordination.router")


class CoordinationLogicTest(unittest.TestCase):
    def test_overlap_is_half_open_and_ignores_cancelled(self):
        at = lambda hour, minute=0: datetime(2026, 7, 17, hour, minute, tzinfo=timezone.utc)
        base = {"id": "a", "chair": "C1", "starts_at": at(9), "ends_at": at(10), "status": "BOOKED"}
        boundary = {"id": "boundary", "chair": "C1", "starts_at": at(10), "ends_at": at(11), "status": "BOOKED"}
        self.assertEqual(module.find_conflicts([base, boundary]), [])
        rows = [
            base,
            {"id": "overlap", "chair": "C1", "starts_at": at(9, 30), "ends_at": at(10, 30), "status": "BOOKED"},
            {"id": "cancelled", "chair": "C1", "starts_at": at(9, 15), "ends_at": at(9, 45), "status": "CANCELLED"},
            {"id": "other-chair", "chair": "C2", "starts_at": at(9, 15), "ends_at": at(9, 45), "status": "BOOKED"},
        ]
        self.assertEqual(module.find_conflicts(rows), [{"appointment_id": "a", "conflicts_with": "overlap", "chair": "C1"}])

    def test_conflicts_are_anchored_to_encounter_appointment(self):
        at = lambda hour, minute=0: datetime(2026, 7, 17, hour, minute, tzinfo=timezone.utc)
        rows = [
            {"id": "anchor", "is_anchor": True, "chair": "C1", "starts_at": at(9), "ends_at": at(10), "status": "BOOKED"},
            {"id": "unrelated-a", "is_anchor": False, "chair": "C2", "starts_at": at(11), "ends_at": at(12), "status": "BOOKED"},
            {"id": "unrelated-b", "is_anchor": False, "chair": "C2", "starts_at": at(11, 30), "ends_at": at(12, 30), "status": "BOOKED"},
        ]
        self.assertEqual(module.find_conflicts(rows), [])

    def test_task_mutations_require_owner_and_non_patient(self):
        task = {"id": "t1", "encounter_id": "e1", "owner_role": "ASSISTANT", "status": "OPEN"}
        self.assertRaises(AppError, module.authorize_task_mutation, task, Role.PATIENT)
        self.assertRaises(AppError, module.authorize_task_mutation, task, Role.DENTIST)
        module.authorize_task_mutation(task, Role.ASSISTANT)

    def test_handoff_must_be_acknowledged_before_completion(self):
        with self.assertRaises(AppError) as caught:
            module.validate_completion({"task_type": "HANDOFF", "status": "OPEN"})
        self.assertEqual(caught.exception.payload["code"], "ACKNOWLEDGMENT_REQUIRED")
        module.validate_completion({"task_type": "HANDOFF", "status": "ACKNOWLEDGED"})

    def test_referral_requires_owner(self):
        with self.assertRaises(AppError) as caught:
            module.validate_task_request("REFERRAL", None)
        self.assertEqual(caught.exception.payload["code"], "REFERRAL_OWNER_REQUIRED")
        with self.assertRaises(AppError) as caught:
            module.validate_task_request("REFERRAL", Role.PATIENT)
        self.assertEqual(caught.exception.payload["code"], "REFERRAL_OWNER_INVALID")

    @patch.object(module, "append_audit")
    @patch.object(module, "upsert_evidence")
    @patch.object(module, "ensure_task")
    def test_evaluation_uses_stable_idempotency_key(self, ensure_task, upsert_evidence, _append_audit):
        ensure_task.return_value = {"id": "t1", "idempotency_key": "coord:e1:schedule-conflict"}
        with patch.object(module, "load_appointments", return_value=[
            {"id": "a", "is_anchor": True, "chair": "C1", "starts_at": datetime(2026, 1, 1, 9, tzinfo=timezone.utc), "ends_at": datetime(2026, 1, 1, 10, tzinfo=timezone.utc), "status": "BOOKED"},
            {"id": "b", "is_anchor": False, "chair": "C1", "starts_at": datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc), "ends_at": datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc), "status": "BOOKED"},
        ]):
            encounter_id = UUID("00000000-0000-0000-0000-000000000003")
            module.evaluate_coordination(encounter_id, Role.FRONT_DESK)
            module.evaluate_coordination(encounter_id, Role.FRONT_DESK)
        self.assertEqual([call.args[-1] for call in ensure_task.call_args_list], ["coord:00000000-0000-0000-0000-000000000003:schedule-conflict"] * 2)
        self.assertEqual(upsert_evidence.call_args.args[1:3], ("COORD_SCHEDULE_CLEAR", "VERIFIED"))

    @patch.object(module, "append_audit")
    @patch.object(module, "ensure_task")
    def test_created_task_key_is_server_derived_and_scoped_to_encounter(self, ensure_task, _append_audit):
        ensure_task.side_effect = lambda *args: {"encounter_id": str(args[0]), "idempotency_key": args[-1], "id": "t"}
        base = dict(obligation_code="COORD_HANDOFF_ACK", task_type="HANDOFF", owner_role=Role.ASSISTANT, due_at=None)
        one = module.create_task(module.TaskRequest(encounter_id=UUID("00000000-0000-0000-0000-000000000001"), **base), Role.FRONT_DESK)
        two = module.create_task(module.TaskRequest(encounter_id=UUID("00000000-0000-0000-0000-000000000002"), **base), Role.FRONT_DESK)
        self.assertNotEqual(one["idempotency_key"], two["idempotency_key"])
        self.assertEqual(one["encounter_id"], "00000000-0000-0000-0000-000000000001")

    def test_identifiers_are_uuid_typed(self):
        self.assertIs(module.TaskRequest.model_fields["encounter_id"].annotation, UUID)
        routes = {route.path: route.endpoint for route in module.router.routes}
        self.assertIs(routes["/api/v1/tasks/{task_id}/acknowledge"].__annotations__["task_id"], UUID)


class CoordinationApiTest(unittest.TestCase):
    def test_worklist_filters_requested_role_but_patient_cannot_read_it(self):
        @contextmanager
        def fake_connect():
            class Connection:
                def execute(self, query, params):
                    self.params = params
                    return self
                def fetchall(self):
                    return [{"id": "t1", "owner_role": self.params[0], "status": "OPEN"}]
            yield Connection()
        with patch.object(module, "_connect", fake_connect):
            response = module.worklist(Role.ASSISTANT, Role.ASSISTANT)
        self.assertEqual(response[0]["owner_role"], "ASSISTANT")
        with self.assertRaises(AppError) as caught:
            module.worklist(Role.ASSISTANT, Role.PATIENT)
        self.assertEqual(caught.exception.status_code, 403)

    def test_react_route_exports_worklist_controls(self):
        source = (Path(__file__).parents[2] / "frontend/src/features/coordination/index.jsx").read_text()
        self.assertIn("export const route", source)
        self.assertIn("/api/v1/tasks", source)
        self.assertIn("acknowledge", source)
        self.assertIn("complete", source)


if __name__ == "__main__":
    unittest.main()
