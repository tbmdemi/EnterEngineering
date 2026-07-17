import inspect
import unittest
from pathlib import Path


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

    def test_database_contains_only_required_foundation_tables_and_seed(self):
        schema = (ROOT / "db/init/00_core.sql").read_text()
        for table in ("patients", "appointments", "encounters", "evidence_items", "obligation_checks", "tasks", "ai_runs", "audit_events"):
            self.assertIn(f"CREATE TABLE {table}", schema)
        seed = (ROOT / "db/init/01_seed.sql").read_text()
        self.assertIn("Nguyen Minh Anh", seed)
        self.assertIn("dental-policy.v1", seed)


if __name__ == "__main__":
    unittest.main()
