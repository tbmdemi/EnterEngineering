import unittest
import importlib
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from backend.app.core.errors import AppError
from backend.app.core.contracts import Role
from backend.app.features.encounter import service
from backend.app.features.encounter.router import StageChange

encounter_router = importlib.import_module("backend.app.features.encounter.router")
ROOT = Path(__file__).parents[2]


CONTEXT = {
    "id": "00000000-0000-0000-0000-000000000003",
    "stage": "CHECK_IN",
    "version": 1,
    "patient": {"id": "patient-1", "mrn": "DENTAL-001", "full_name": "Nguyen Minh Anh", "date_of_birth": "1992-04-12"},
    "appointment": {"id": "appointment-1", "starts_at": "2026-07-17T02:00:00+00:00", "ends_at": "2026-07-17T02:45:00+00:00", "chair": "CHAIR-01", "status": "CHECKED_IN"},
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


class EncounterTest(unittest.TestCase):
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

    def test_next_stage_updates_with_optimistic_version_and_keeps_context(self):
        updated = {**CONTEXT, "stage": "PRE_TREATMENT", "version": 2}
        connection, connect = self.connection([CONTEXT, {"id": CONTEXT["id"]}, updated])
        with patch.object(service, "_connect", connect):
            result = service.advance_stage(CONTEXT["id"], "PRE_TREATMENT", 1)

        self.assertEqual(result, updated)
        update_query, update_params = connection.calls[1]
        self.assertIn("version = version + 1", update_query)
        self.assertIn("version = %s", update_query)
        self.assertEqual(update_params, ("PRE_TREATMENT", CONTEXT["id"], 1))

    def test_skip_backward_and_stale_version_are_rejected(self):
        for target in ("TREATMENT", "CHECK_IN"):
            _connection, connect = self.connection([CONTEXT])
            with self.subTest(target=target), patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
                service.advance_stage(CONTEXT["id"], target, 1)
            self.assertEqual(caught.exception.payload["code"], "INVALID_STAGE_TRANSITION")

        _connection, connect = self.connection([CONTEXT, None])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.advance_stage(CONTEXT["id"], "PRE_TREATMENT", 0)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.payload["code"], "STALE_ENCOUNTER_VERSION")

    def test_stale_version_wins_after_another_request_progressed_the_stage(self):
        progressed = {**CONTEXT, "stage": "PRE_TREATMENT", "version": 2}
        connection, connect = self.connection([progressed])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.advance_stage(CONTEXT["id"], "PRE_TREATMENT", 1)

        self.assertEqual(caught.exception.payload["code"], "STALE_ENCOUNTER_VERSION")
        self.assertEqual(len(connection.calls), 1)

    def test_lost_update_refreshes_current_version_before_returning_conflict(self):
        progressed = {**CONTEXT, "stage": "PRE_TREATMENT", "version": 2}
        connection, connect = self.connection([CONTEXT, None, progressed])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.advance_stage(CONTEXT["id"], "PRE_TREATMENT", 1)

        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.payload["code"], "STALE_ENCOUNTER_VERSION")
        self.assertEqual(caught.exception.payload["details"]["current_version"], 2)
        self.assertEqual(caught.exception.payload["details"]["current_stage"], "PRE_TREATMENT")
        self.assertEqual(len(connection.calls), 3)

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
            advance.assert_called_once()

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
                result = service.advance_stage(CONTEXT["id"], stage, version)
                self.assertEqual(result["version"], version + 1)
                self.assertEqual(result["patient"], CONTEXT["patient"])
                self.assertEqual(result["appointment"], CONTEXT["appointment"])

    def test_unknown_encounter_is_404(self):
        _connection, connect = self.connection([None])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.get_encounter("missing")
        self.assertEqual(caught.exception.status_code, 404)

    def test_frontend_preserves_context_and_handles_pending_and_stale_requests(self):
        source = (ROOT / "frontend/src/features/encounter/index.jsx").read_text(encoding="utf-8")

        self.assertIn('export const route = { path: "/encounter"', source)
        self.assertIn("aria-current", source)
        self.assertIn("disabled={isAdvancing}", source)
        self.assertIn("STALE_ENCOUNTER_VERSION", source)
        self.assertIn("await load()", source)
        self.assertNotIn("stage: stages[stages.indexOf(data.stage) + 1]", source)

    def test_demo_bootstrap_registers_encounter_and_api_proxy(self):
        from backend.app.main import app

        paths = {route.path for route in app.routes}
        self.assertIn("/api/v1/encounters/{encounter_id}", paths)
        self.assertIn("/api/v1/encounters/{encounter_id}/stage", paths)

        registry = (ROOT / "frontend/src/routes.js").read_text(encoding="utf-8")
        vite_config = (ROOT / "frontend/vite.config.js").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        self.assertIn('import { route as encounterRoute }', registry)
        self.assertIn("featureRoutes = [encounterRoute]", registry)
        self.assertIn('"/api"', vite_config)
        self.assertIn('"http://localhost:8000"', vite_config)
        self.assertIn("API_PROXY_TARGET: http://api:8000", compose)


if __name__ == "__main__":
    unittest.main()
