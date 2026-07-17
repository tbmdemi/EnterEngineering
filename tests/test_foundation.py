import inspect
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).parents[1]


class FoundationContractTest(unittest.TestCase):
    def test_shared_contracts_are_stable(self):
        from backend.app.core.contracts import (
            EncounterStage,
            EvidenceState,
            ObligationState,
            Role,
            TaskStatus,
        )

        self.assertEqual([x.value for x in Role], ["FRONT_DESK", "ASSISTANT", "DENTIST", "PATIENT", "QA"])
        self.assertEqual([x.value for x in EncounterStage], ["CHECK_IN", "PRE_TREATMENT", "TREATMENT", "POST_TREATMENT", "CLOSED"])
        self.assertEqual([x.value for x in EvidenceState], ["DRAFT", "VERIFIED"])
        self.assertEqual([x.value for x in ObligationState], ["PENDING", "MISSING", "UNVERIFIED", "SATISFIED", "NOT_APPLICABLE"])
        self.assertEqual([x.value for x in TaskStatus], ["OPEN", "ACKNOWLEDGED", "COMPLETED", "CANCELLED"])

    def test_core_service_signatures_are_stable(self):
        from backend.app.core.services import append_audit, ensure_task, upsert_evidence

        self.assertEqual(list(inspect.signature(upsert_evidence).parameters), ["encounter_id", "code", "state", "value", "source_type", "source_ref", "actor_role"])
        self.assertEqual(list(inspect.signature(ensure_task).parameters), ["encounter_id", "obligation_code", "task_type", "owner_role", "due_at", "idempotency_key"])
        self.assertEqual(list(inspect.signature(append_audit).parameters), ["actor_role", "action", "object_type", "object_id", "encounter_id", "metadata"])

    def test_demo_role_parser_rejects_missing_and_invalid_roles(self):
        from backend.app.core.errors import AppError
        from backend.app.core.security import parse_demo_role

        for value in (None, "", "ADMIN"):
            with self.subTest(value=value), self.assertRaises(AppError) as caught:
                parse_demo_role(value)
            self.assertEqual(caught.exception.status_code, 401 if not value else 403)
            self.assertEqual(set(caught.exception.payload), {"code", "message", "details"})
        self.assertEqual(parse_demo_role("DENTIST").value, "DENTIST")

    def test_core_services_persist_and_return_dicts_idempotently(self):
        from backend.app.core import services

        rows = iter([
            {"id": "evidence-1", "code": "PRE_ALLERGY", "state": "VERIFIED"},
            {"id": "task-1", "status": "OPEN", "idempotency_key": "same-key"},
            {"id": "audit-1", "action": "VERIFIED"},
        ])

        class FakeConnection:
            def __init__(self):
                self.calls = []
            def execute(self, query, params):
                self.calls.append((query, params))
                return self
            def fetchone(self):
                return next(rows)

        connection = FakeConnection()

        @contextmanager
        def fake_connect():
            yield connection

        with patch.object(services, "_connect", fake_connect):
            evidence = services.upsert_evidence("enc", "PRE_ALLERGY", "VERIFIED", {"ok": True}, "FORM", "form-1", "ASSISTANT")
            task = services.ensure_task("enc", "PRE_ALLERGY", "REVIEW", "DENTIST", None, "same-key")
            audit = services.append_audit("DENTIST", "VERIFIED", "evidence", "evidence-1", "enc", {"safe": True})

        self.assertEqual(evidence["id"], "evidence-1")
        self.assertEqual(task["idempotency_key"], "same-key")
        self.assertEqual(audit["action"], "VERIFIED")
        self.assertIn("ON CONFLICT (encounter_id, code)", connection.calls[0][0])
        self.assertIn("ON CONFLICT (idempotency_key)", connection.calls[1][0])
        self.assertIn("INSERT INTO audit_events", connection.calls[2][0])

    def test_react_feature_route_contract_and_registry_are_documented(self):
        registry = (ROOT / "frontend/src/routes.js").read_text(encoding="utf-8")
        self.assertIn("export const featureRoutes", registry)
        convention = "export const route = { path, label, Component }"
        for spec in (ROOT / "docs/modules").glob("*.md"):
            self.assertIn(convention, spec.read_text(encoding="utf-8"), spec.name)

    def test_api_registers_validation_and_unhandled_error_boundaries(self):
        source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
        self.assertIn("RequestValidationError", source)
        self.assertIn("@app.exception_handler(Exception)", source)
        self.assertIn('"details"', source)

    def test_database_contains_only_required_foundation_tables_and_seed(self):
        schema = (ROOT / "db/init/00_core.sql").read_text(encoding="utf-8")
        for table in ("patients", "appointments", "encounters", "evidence_items", "obligation_checks", "tasks", "ai_runs", "audit_events"):
            self.assertIn(f"CREATE TABLE {table}", schema)
        seed = (ROOT / "db/init/01_seed.sql").read_text(encoding="utf-8")
        self.assertIn("Nguyen Minh Anh", seed)
        self.assertIn("dental-policy.v1", seed)


if __name__ == "__main__":
    unittest.main()
