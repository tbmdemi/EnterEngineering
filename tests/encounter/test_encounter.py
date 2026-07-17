import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backend.app.core.errors import AppError
from backend.app.features.encounter import service


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

    def test_unknown_encounter_is_404(self):
        _connection, connect = self.connection([None])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.get_encounter("missing")
        self.assertEqual(caught.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
