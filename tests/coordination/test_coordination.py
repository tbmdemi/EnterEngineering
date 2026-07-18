import importlib
import json
import unittest
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
        self.assertEqual(module.find_conflicts(rows), [{
            "appointment_id": "a",
            "conflicts_with": "overlap",
            "chair": "C1",
            "starts_at": at(9, 30).isoformat(),
            "ends_at": at(10, 30).isoformat(),
        }])

    def test_conflict_evidence_is_json_serializable_with_database_types(self):
        at = lambda hour, minute=0: datetime(2026, 7, 17, hour, minute, tzinfo=timezone.utc)
        rows = [
            {"id": UUID("00000000-0000-0000-0000-000000000002"), "is_anchor": True, "chair": "C1", "starts_at": at(9), "ends_at": at(10), "status": "BOOKED"},
            {"id": UUID("00000000-0000-0000-0000-000000000040"), "is_anchor": False, "chair": "C1", "starts_at": at(9, 30), "ends_at": at(10, 30), "status": "BOOKED"},
        ]
        conflicts = module.find_conflicts(rows)
        encoded = json.dumps({"clear": False, "conflicts": conflicts})
        self.assertIn("00000000-0000-0000-0000-000000000040", encoded)
        self.assertIn("2026-07-17T09:30:00+00:00", encoded)

    def test_cancelled_anchor_never_reports_a_conflict(self):
        at = lambda hour, minute=0: datetime(2026, 7, 17, hour, minute, tzinfo=timezone.utc)
        rows = [
            {"id": "anchor", "is_anchor": True, "chair": "C1", "starts_at": at(9), "ends_at": at(10), "status": "CANCELLED"},
            {"id": "other", "is_anchor": False, "chair": "C1", "starts_at": at(9, 30), "ends_at": at(10, 30), "status": "BOOKED"},
        ]
        self.assertEqual(module.find_conflicts(rows), [])

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
        with self.assertRaises(AppError) as caught:
            module.validate_task_request("REFERRAL", Role.QA)
        self.assertEqual(caught.exception.payload["code"], "REFERRAL_OWNER_INVALID")

    @patch.object(module, "append_audit")
    def test_terminal_mutations_are_idempotent(self, append_audit):
        acknowledged = {
            "id": "t1", "encounter_id": "e1", "owner_role": "ASSISTANT",
            "task_type": "HANDOFF", "status": "ACKNOWLEDGED",
        }
        with patch.object(module, "_task", return_value=acknowledged):
            self.assertEqual(module.acknowledge("t1", Role.ASSISTANT), acknowledged)

        completed = {**acknowledged, "status": "COMPLETED"}
        with patch.object(module, "_task", return_value=completed):
            self.assertEqual(module.complete("t1", Role.ASSISTANT), completed)
        append_audit.assert_not_called()

    def test_only_handoffs_can_be_acknowledged(self):
        referral = {
            "id": "t1", "encounter_id": "e1", "owner_role": "DENTIST",
            "task_type": "REFERRAL", "status": "OPEN",
        }
        with patch.object(module, "_task", return_value=referral), self.assertRaises(AppError) as caught:
            module.acknowledge("t1", Role.DENTIST)
        self.assertEqual(caught.exception.payload["code"], "TASK_ACKNOWLEDGMENT_NOT_REQUIRED")

    @patch.object(module, "append_audit")
    @patch.object(module, "upsert_evidence")
    def test_handoff_acknowledgment_persists_evidence_and_audit(self, upsert_evidence, append_audit):
        task_id = UUID("00000000-0000-0000-0000-000000000042")
        task = {
            "id": task_id,
            "encounter_id": UUID("00000000-0000-0000-0000-000000000003"),
            "owner_role": "ASSISTANT",
            "task_type": "HANDOFF",
            "status": "OPEN",
        }

        @contextmanager
        def fake_connect():
            class Connection:
                def execute(self, query, params):
                    self.query = query
                    self.params = params
                    return self
                def fetchone(self):
                    return {**task, "status": "ACKNOWLEDGED"}
            yield Connection()

        with patch.object(module, "_task", return_value=task), patch.object(module, "_connect", fake_connect):
            response = module.acknowledge(task_id, Role.ASSISTANT)

        self.assertEqual(response["status"], "ACKNOWLEDGED")
        self.assertEqual(upsert_evidence.call_args.args[1], "COORD_HANDOFF_ACK")
        self.assertEqual(upsert_evidence.call_args.args[2], "VERIFIED")
        self.assertEqual(upsert_evidence.call_args.args[3]["task_id"], str(task_id))
        self.assertEqual(upsert_evidence.call_args.args[5], str(task_id))
        self.assertEqual(append_audit.call_args.args[1], "TASK_ACKNOWLEDGED")

    @patch.object(module, "append_audit")
    def test_referral_can_complete_without_acknowledgment(self, append_audit):
        task_id = UUID("00000000-0000-0000-0000-000000000043")
        task = {
            "id": task_id,
            "encounter_id": UUID("00000000-0000-0000-0000-000000000003"),
            "owner_role": "DENTIST",
            "task_type": "REFERRAL",
            "status": "OPEN",
        }

        @contextmanager
        def fake_connect():
            class Connection:
                def execute(self, query, params):
                    return self
                def fetchone(self):
                    return {**task, "status": "COMPLETED"}
            yield Connection()

        with patch.object(module, "_task", return_value=task), patch.object(module, "_connect", fake_connect):
            response = module.complete(task_id, Role.DENTIST)

        self.assertEqual(response["status"], "COMPLETED")
        self.assertEqual(append_audit.call_args.args[1], "TASK_COMPLETED")

    @patch.object(module, "append_audit")
    @patch.object(module, "upsert_evidence")
    @patch.object(module, "ensure_task")
    def test_evaluation_uses_stable_idempotency_key(self, ensure_task, upsert_evidence, _append_audit):
        ensure_task.return_value = {"id": "t1", "idempotency_key": "coord:e1:schedule-conflict"}
        with patch.object(module, "require_encounter"), patch.object(module, "load_appointments", return_value=[
            {"id": "a", "is_anchor": True, "chair": "C1", "starts_at": datetime(2026, 1, 1, 9, tzinfo=timezone.utc), "ends_at": datetime(2026, 1, 1, 10, tzinfo=timezone.utc), "status": "BOOKED"},
            {"id": "b", "is_anchor": False, "chair": "C1", "starts_at": datetime(2026, 1, 1, 9, 30, tzinfo=timezone.utc), "ends_at": datetime(2026, 1, 1, 10, 30, tzinfo=timezone.utc), "status": "BOOKED"},
        ]):
            encounter_id = UUID("00000000-0000-0000-0000-000000000003")
            module.evaluate_coordination(encounter_id, Role.FRONT_DESK)
            module.evaluate_coordination(encounter_id, Role.FRONT_DESK)
        self.assertEqual([call.args[-1] for call in ensure_task.call_args_list], ["coord:00000000-0000-0000-0000-000000000003:schedule-conflict"] * 2)
        self.assertEqual(upsert_evidence.call_args.args[1:3], ("COORD_SCHEDULE_CLEAR", "VERIFIED"))

    @patch.object(module, "append_audit")
    @patch.object(module, "upsert_evidence")
    def test_clear_schedule_cancels_open_conflict_task(self, _upsert_evidence, _append_audit):
        class Connection:
            def __init__(self): self.calls = []
            def execute(self, query, params): self.calls.append((query, params)); return self
        connection = Connection()
        @contextmanager
        def connect(): yield connection
        with patch.object(module, "require_encounter"), patch.object(module, "load_appointments", return_value=[]), patch.object(module, "_connect", connect):
            module.evaluate_coordination(UUID("00000000-0000-0000-0000-000000000003"), Role.FRONT_DESK)
        self.assertIn("status = 'CANCELLED'", connection.calls[0][0])

    @patch.object(module, "append_audit")
    @patch.object(module, "ensure_task")
    def test_created_task_key_is_server_derived_and_scoped_to_encounter(self, ensure_task, _append_audit):
        ensure_task.side_effect = lambda *args: {"encounter_id": str(args[0]), "idempotency_key": args[-1], "id": "t"}
        base = dict(obligation_code="COORD_HANDOFF_ACK", task_type="HANDOFF", owner_role=Role.ASSISTANT, due_at=None)
        with patch.object(module, "require_encounter"):
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
        queries = []

        @contextmanager
        def fake_connect():
            class Connection:
                def execute(self, query, params):
                    queries.append(query)
                    self.query = query
                    self.params = params
                    return self
                def fetchall(self):
                    return [{"id": "t1", "owner_role": self.params[0], "status": "OPEN"}]
            yield Connection()
        with patch.object(module, "_connect", fake_connect):
            response = module.worklist(Role.ASSISTANT, Role.ASSISTANT)
        self.assertEqual(response[0]["owner_role"], "ASSISTANT")
        self.assertIn("t.status IN ('OPEN', 'ACKNOWLEDGED')", queries[0])
        with self.assertRaises(AppError) as caught:
            module.worklist(Role.ASSISTANT, Role.PATIENT)
        self.assertEqual(caught.exception.status_code, 403)

        with self.assertRaises(AppError) as caught:
            module.worklist(Role.QA, Role.QA)
        self.assertEqual(caught.exception.payload["code"], "WORKLIST_ROLE_INVALID")

    def test_react_route_exports_worklist_controls(self):
        source = (Path(__file__).parents[2] / "frontend/src/features/coordination/index.jsx").read_text(encoding="utf-8")
        self.assertIn("export const route", source)
        self.assertIn("/api/v1/tasks", source)
        self.assertIn("acknowledge", source)
        self.assertIn("complete", source)

    def test_seed_covers_all_roles_and_overlap_boundaries(self):
        source = (Path(__file__).parents[2] / "db/init/40_coordination.sql").read_text(encoding="utf-8")
        self.assertIn("'HANDOFF', 'ASSISTANT'", source)
        self.assertIn("'REFERRAL', 'DENTIST'", source)
        self.assertIn("'REVIEW_SCHEDULE_CONFLICT', 'FRONT_DESK'", source)
        self.assertIn("2026-07-17 09:45+07", source)
        self.assertIn("coord:00000000-0000-0000-0000-000000000003:schedule-conflict", source)

    def test_backend_and_frontend_register_coordination(self):
        from backend.app.main import app

        api_paths = {route.path for route in app.routes}
        self.assertIn("/api/v1/tasks", api_paths)
        self.assertIn("/api/v1/tasks/{task_id}/acknowledge", api_paths)
        self.assertIn("/api/v1/tasks/{task_id}/complete", api_paths)
        self.assertIn("/api/v1/encounters/{encounter_id}/coordination/evaluate", api_paths)

        routes = (Path(__file__).parents[2] / "frontend/src/routes.js").read_text(encoding="utf-8")
        main = (Path(__file__).parents[2] / "frontend/src/main.jsx").read_text(encoding="utf-8")
        self.assertIn("coordinationRoute", routes)
        self.assertIn("export const featureRoutes = [", routes)
        self.assertIn("<ActiveFeature />", main)

    def test_vite_proxy_targets_the_api_service_in_compose(self):
        root = Path(__file__).parents[2]
        vite = (root / "frontend/vite.config.js").read_text(encoding="utf-8")
        compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('"/api"', vite)
        self.assertIn("API_PROXY_TARGET", vite)
        self.assertIn("API_PROXY_TARGET: http://api:8000", compose)


if __name__ == "__main__":
    unittest.main()
