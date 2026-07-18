import unittest
import importlib
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError
from fastapi.testclient import TestClient

from backend.app.core.errors import AppError
from backend.app.core.contracts import Role
from backend.app.features.encounter import service
from backend.app.features.encounter.router import StageChange
from backend.app.main import app

encounter_router = importlib.import_module("backend.app.features.encounter.router")
ROOT = Path(__file__).parents[2]


CONTEXT = {
    "id": "00000000-0000-0000-0000-000000000003",
    "stage": "CHECK_IN",
    "version": 1,
    "patient": {"id": "00000000-0000-0000-0000-000000000001", "mrn": "DENTAL-001", "full_name": "Nguyen Minh Anh", "date_of_birth": "1992-04-12"},
    "appointment": {"id": "00000000-0000-0000-0000-000000000002", "starts_at": "2026-07-17T02:00:00+00:00", "ends_at": "2026-07-17T02:45:00+00:00", "chair": "CHAIR-01", "status": "CHECKED_IN"},
}


class FakeConnection:
    def __init__(self, rows):
        self.rows = iter(rows)
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        return self

    def fetchone(self):
        return next(self.rows)

    def fetchall(self):
        return next(self.rows)


class EncounterTest(unittest.TestCase):
    def test_patient_cannot_read_internal_encounter_context(self):
        with self.assertRaises(AppError) as caught:
            encounter_router.encounter(CONTEXT["id"], Role.PATIENT)
        self.assertEqual(caught.exception.status_code, 403)

    def connection(self, rows):
        connection = FakeConnection(rows)

        @contextmanager
        def connect():
            yield connection

        return connection, connect

    def test_get_returns_synthetic_encounter_context(self):
        connection, connect = self.connection([CONTEXT])
        with patch.object(service, "_connect", connect):
            result = service.get_encounter(CONTEXT["id"])

        self.assertEqual(result, CONTEXT)
        self.assertIn("JOIN patients", connection.calls[0][0])
        self.assertIn("LEFT JOIN appointments", connection.calls[0][0])

    def test_pre_treatment_requires_a_checked_in_appointment(self):
        for appointment, expected in (({"status": "CHECKED_IN"}, None), ({"status": "BOOKED"}, "APPOINTMENT_NOT_CHECKED_IN"), (None, "APPOINTMENT_NOT_CHECKED_IN")):
            connection, _connect = self.connection([appointment])
            with self.subTest(appointment=appointment):
                result = service.check_in_transition_guard(connection, CONTEXT["id"], Role.FRONT_DESK)
                self.assertEqual(result["code"] if result else None, expected)
                self.assertIn("FOR UPDATE OF a", connection.calls[0][0])

    def test_next_stage_updates_with_optimistic_version_and_keeps_context(self):
        updated = {**CONTEXT, "stage": "PRE_TREATMENT", "version": 2}
        connection, connect = self.connection([CONTEXT, {"id": CONTEXT["id"]}, updated])
        with patch.object(service, "_connect", connect):
            result = service.advance_stage(CONTEXT["id"], "PRE_TREATMENT", 1, Role.DENTIST)

        self.assertEqual(result, updated)
        update_query, update_params = connection.calls[1]
        self.assertIn("version = version + 1", update_query)
        self.assertIn("version = %s", update_query)
        self.assertEqual(update_params, ("PRE_TREATMENT", CONTEXT["id"], 1))

    def test_skip_backward_and_stale_version_are_rejected(self):
        for target in ("TREATMENT", "CHECK_IN"):
            _connection, connect = self.connection([CONTEXT])
            with self.subTest(target=target), patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
                service.advance_stage(CONTEXT["id"], target, 1, Role.DENTIST)
            self.assertEqual(caught.exception.payload["code"], "INVALID_STAGE_TRANSITION")

        _connection, connect = self.connection([CONTEXT, None])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.advance_stage(CONTEXT["id"], "PRE_TREATMENT", 0, Role.DENTIST)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.payload["code"], "STALE_ENCOUNTER_VERSION")

    def test_stale_version_wins_after_another_request_progressed_the_stage(self):
        progressed = {**CONTEXT, "stage": "PRE_TREATMENT", "version": 2}
        connection, connect = self.connection([progressed])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.advance_stage(CONTEXT["id"], "PRE_TREATMENT", 1, Role.DENTIST)

        self.assertEqual(caught.exception.payload["code"], "STALE_ENCOUNTER_VERSION")
        self.assertEqual(len(connection.calls), 1)

    def test_lost_update_refreshes_current_version_before_returning_conflict(self):
        progressed = {**CONTEXT, "stage": "PRE_TREATMENT", "version": 2}
        connection, connect = self.connection([CONTEXT, None, progressed])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.advance_stage(CONTEXT["id"], "PRE_TREATMENT", 1, Role.DENTIST)

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.payload["code"], "STALE_ENCOUNTER_VERSION")
        self.assertEqual(caught.exception.payload["details"]["current_version"], 2)
        self.assertEqual(caught.exception.payload["details"]["current_stage"], "PRE_TREATMENT")
        self.assertEqual(len(connection.calls), 3)

    def test_close_guard_blocks_before_stage_update_and_preserves_version(self):
        post_treatment = {**CONTEXT, "stage": "POST_TREATMENT", "version": 4}
        connection, connect = self.connection([post_treatment])
        seen_connection = []

        def guard(active_connection, encounter_id, role):
            seen_connection.append(active_connection)
            self.assertEqual(encounter_id, CONTEXT["id"])
            self.assertEqual(role, Role.DENTIST)
            return {
                "code": "COMPLIANCE_NOT_READY",
                "message": "Not ready",
                "details": {"blockers": [{"code": "POST_RECALL", "state": "MISSING"}]},
                "status_code": 409,
            }

        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.advance_stage(CONTEXT["id"], "CLOSED", 4, Role.DENTIST, guard)

        self.assertEqual(caught.exception.payload["code"], "COMPLIANCE_NOT_READY")
        self.assertEqual(seen_connection, [connection])
        self.assertFalse(any("UPDATE encounters" in query for query, _params in connection.calls))

    def test_stage_change_denies_patient_and_qa(self):
        change = StageChange(stage="PRE_TREATMENT", version=1)
        for role in (Role.PATIENT, Role.QA):
            with self.subTest(role=role), patch.object(encounter_router, "advance_stage") as advance, self.assertRaises(AppError) as caught:
                encounter_router.change_stage(CONTEXT["id"], change, role)
            self.assertEqual(caught.exception.status_code, 403)
            self.assertEqual(caught.exception.payload["code"], "ROLE_FORBIDDEN")
            advance.assert_not_called()

        for role in (Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST):
            with self.subTest(role=role), patch.object(encounter_router, "advance_stage", return_value=CONTEXT) as advance:
                encounter_router.change_stage(CONTEXT["id"], change, role)
            advance.assert_called_once_with(
                CONTEXT["id"], change.stage, change.version, role,
                encounter_router.check_in_transition_guard,
            )

    def test_only_dentist_can_start_or_finish_clinical_treatment(self):
        for stage, guard in (
            ("TREATMENT", encounter_router.treatment_transition_guard),
            ("POST_TREATMENT", encounter_router.post_treatment_transition_guard),
            ("CLOSED", encounter_router.close_transition_guard),
        ):
            change = StageChange(stage=stage, version=2)
            for role in (Role.FRONT_DESK, Role.ASSISTANT):
                with self.subTest(stage=stage, role=role), patch.object(encounter_router, "advance_stage") as advance, self.assertRaises(AppError) as caught:
                    encounter_router.change_stage(CONTEXT["id"], change, role)
                self.assertEqual(caught.exception.payload["code"], "ROLE_FORBIDDEN")
                advance.assert_not_called()
            with self.subTest(stage=stage, role=Role.DENTIST), patch.object(encounter_router, "advance_stage", return_value={**CONTEXT, "stage": stage}) as advance, patch.object(encounter_router, "transition_readiness", return_value={"ready": True, "target_stage": "POST_TREATMENT", "policy_version": "dental-policy.v1", "blockers": []}):
                encounter_router.change_stage(CONTEXT["id"], change, Role.DENTIST)
            advance.assert_called_once_with(CONTEXT["id"], change.stage, change.version, Role.DENTIST, guard)

    def test_stage_endpoint_rejects_a_valid_enum_that_is_not_a_forward_target(self):
        change = StageChange(stage="CHECK_IN", version=1)
        with patch.object(encounter_router, "advance_stage") as advance, self.assertRaises(AppError) as caught:
            encounter_router.change_stage(CONTEXT["id"], change, Role.DENTIST)

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.payload["code"], "INVALID_STAGE_TRANSITION")
        advance.assert_not_called()

    def test_stage_change_requires_a_positive_version(self):
        for version in (0, -1):
            with self.subTest(version=version), self.assertRaises(ValidationError):
                StageChange(stage="PRE_TREATMENT", version=version)

    def test_full_stage_sequence_preserves_context_and_increments_version(self):
        state = dict(CONTEXT)

        class StatefulConnection:
            def execute(self, query, params):
                if "UPDATE encounters" in query:
                    if params[2] != state["version"]:
                        self.row = None
                    else:
                        state["stage"], state["version"] = params[0], state["version"] + 1
                        self.row = {"id": state["id"]}
                else:
                    self.row = dict(state)
                return self

            def fetchone(self):
                return self.row

        @contextmanager
        def connect():
            yield StatefulConnection()

        with patch.object(service, "_connect", connect):
            for version, stage in enumerate(("PRE_TREATMENT", "TREATMENT", "POST_TREATMENT", "CLOSED"), 1):
                result = service.advance_stage(CONTEXT["id"], stage, version, Role.DENTIST)
                self.assertEqual(result["version"], version + 1)
                self.assertEqual(result["patient"], CONTEXT["patient"])
                self.assertEqual(result["appointment"], CONTEXT["appointment"])

    def test_unknown_encounter_is_404(self):
        _connection, connect = self.connection([None])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.get_encounter("missing")
        self.assertEqual(caught.exception.status_code, 404)

    def test_stage_history_uses_append_only_safe_audit_metadata(self):
        transition = {
            "id": "00000000-0000-0000-0000-000000000010",
            "from_stage": "CHECK_IN",
            "to_stage": "PRE_TREATMENT",
            "actor_role": "DENTIST",
            "from_version": 1,
            "to_version": 2,
            "occurred_at": "2026-07-17T02:01:00+00:00",
        }
        connection, connect = self.connection([CONTEXT, [transition]])
        with patch.object(service, "_connect", connect):
            result = service.get_stage_transitions(CONTEXT["id"])

        self.assertEqual(result, [transition])
        self.assertIn("ENCOUNTER_STAGE_CHANGED", connection.calls[1][0])
        self.assertIn("ORDER BY created_at, id", connection.calls[1][0])

    def test_frontend_preserves_context_and_handles_pending_and_stale_requests(self):
        source = (ROOT / "frontend/src/features/encounter/index.jsx").read_text(encoding="utf-8")

        self.assertIn('export const route = { path: "/encounter"', source)
        self.assertIn("aria-current", source)
        self.assertIn("disabled={isAdvancing}", source)
        self.assertIn("STALE_ENCOUNTER_VERSION", source)
        self.assertIn("await load(undefined, true)", source)
        self.assertIn("URLSearchParams", source)
        self.assertIn("careguard.demoRole", source)
        self.assertIn("Xác nhận đóng ca", source)
        self.assertIn("visibilitychange", source)
        self.assertNotIn("const DEMO_ROLE", source)
        self.assertNotIn("stage: stages[stages.indexOf(data.stage) + 1]", source)

    def test_demo_bootstrap_registers_encounter_and_api_proxy(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/api/v1/encounters/{encounter_id}", paths)
        self.assertIn("/api/v1/encounters/{encounter_id}/stage", paths)
        self.assertIn("/api/v1/encounters/{encounter_id}/transitions", paths)

        registry = (ROOT / "frontend/src/routes.js").read_text(encoding="utf-8")
        vite_config = (ROOT / "frontend/vite.config.js").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('import { route as encounterRoute }', registry)
        self.assertIn("export const featureRoutes = [", registry)
        self.assertIn('"/api"', vite_config)
        self.assertIn('"http://localhost:8000"', vite_config)
        self.assertIn("API_PROXY_TARGET: http://api:8000", compose)


class EncounterHttpContractTest(unittest.TestCase):
    client = TestClient(app, raise_server_exceptions=False)
    headers = {"X-Demo-Role": "DENTIST"}

    def test_missing_and_invalid_demo_roles_use_error_contract(self):
        missing = self.client.get(f"/api/v1/encounters/{CONTEXT['id']}")
        invalid = self.client.get(
            f"/api/v1/encounters/{CONTEXT['id']}",
            headers={"X-Demo-Role": "ADMIN"},
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 403)
        self.assertEqual(set(missing.json()), {"code", "message", "details"})
        self.assertEqual(set(invalid.json()), {"code", "message", "details"})

    def test_invalid_uuid_and_body_use_sanitized_validation_contract(self):
        invalid_uuid = self.client.get("/api/v1/encounters/not-a-uuid", headers=self.headers)
        invalid_body = self.client.post(
            f"/api/v1/encounters/{CONTEXT['id']}/stage",
            headers=self.headers,
            json={"stage": "PRE_TREATMENT", "version": 0},
        )

        for response in (invalid_uuid, invalid_body):
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["code"], "VALIDATION_ERROR")
            self.assertEqual(set(response.json()), {"code", "message", "details"})
            self.assertNotIn("traceback", response.text.lower())

    def test_get_response_model_exposes_capability_without_extra_fields(self):
        with patch.object(encounter_router, "get_encounter", return_value={**CONTEXT, "internal_secret": "never-return"}):
            response = self.client.get(f"/api/v1/encounters/{CONTEXT['id']}", headers=self.headers)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["next_stage"], "PRE_TREATMENT")
        self.assertTrue(body["can_advance"])
        self.assertNotIn("internal_secret", body)

    def test_patient_is_denied_and_qa_is_read_only(self):
        patient_read = self.client.get(
            f"/api/v1/encounters/{CONTEXT['id']}",
            headers={"X-Demo-Role": "PATIENT"},
        )
        self.assertEqual(patient_read.status_code, 403)

        with patch.object(encounter_router, "get_encounter", return_value=CONTEXT):
            qa_read = self.client.get(
                f"/api/v1/encounters/{CONTEXT['id']}",
                headers={"X-Demo-Role": "QA"},
            )
        self.assertEqual(qa_read.status_code, 200)
        self.assertFalse(qa_read.json()["can_advance"])

        for role in ("PATIENT", "QA"):
            with self.subTest(role=role):
                write = self.client.post(
                    f"/api/v1/encounters/{CONTEXT['id']}/stage",
                    headers={"X-Demo-Role": role},
                    json={"stage": "PRE_TREATMENT", "version": 1},
                )
                self.assertEqual(write.status_code, 403)
                self.assertEqual(write.json()["code"], "ROLE_FORBIDDEN")

    def test_close_http_contract_uses_compliance_guard(self):
        post_treatment = {**CONTEXT, "stage": "POST_TREATMENT", "version": 4}
        error = AppError(
            "COMPLIANCE_NOT_READY",
            "Encounter cannot be closed",
            {"blockers": [{"code": "POST_RECALL", "state": "MISSING", "owner_role": "FRONT_DESK"}]},
            409,
        )
        with patch.object(encounter_router, "advance_stage", side_effect=error) as advance:
            response = self.client.post(
                f"/api/v1/encounters/{CONTEXT['id']}/stage",
                headers=self.headers,
                json={"stage": "CLOSED", "version": post_treatment["version"]},
            )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "COMPLIANCE_NOT_READY")
        self.assertIs(advance.call_args.args[-1], encounter_router.close_transition_guard)


if __name__ == "__main__":
    unittest.main()
