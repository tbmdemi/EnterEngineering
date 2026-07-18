import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]


class WorkflowHardeningMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.migration = (ROOT / "db/migrations/003_workflow_hardening.sql").read_text(encoding="utf-8")

    def test_migration_is_atomic_and_idempotent(self):
        self.assertTrue(self.migration.lstrip().startswith("BEGIN;"))
        self.assertTrue(self.migration.rstrip().endswith("COMMIT;"))
        self.assertIn("ADD COLUMN IF NOT EXISTS version", self.migration)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS encounters_one_per_appointment_idx", self.migration)
        self.assertIn("CREATE UNIQUE INDEX IF NOT EXISTS appointments_id_patient_idx", self.migration)
        self.assertIn("CONSTRAINT encounters_appointment_patient_match", self.migration)
        self.assertIn("FOREIGN KEY (appointment_id, patient_id)", self.migration)
        self.assertIn("IF NOT EXISTS", self.migration)

    def test_database_protects_appointment_and_task_state(self):
        for status in ("PENDING", "BOOKED", "ARRIVED", "CHECKED_IN", "FULFILLED", "CANCELLED", "NO_SHOW"):
            self.assertIn(f"'{status}'", self.migration)
        for column in ("acknowledged_at", "completed_at", "cancelled_at", "updated_at"):
            self.assertIn(column, self.migration)

    def test_runtime_updates_state_timestamps_and_appointment_version(self):
        encounter = (ROOT / "backend/app/features/encounter/service.py").read_text(encoding="utf-8")
        coordination = (ROOT / "backend/app/features/coordination/router.py").read_text(encoding="utf-8")

        self.assertIn("version = a.version + 1", encounter)
        self.assertIn("acknowledged_at = now()", coordination)
        self.assertIn("completed_at = now()", coordination)
        self.assertIn("cancelled_at = now()", coordination)


if __name__ == "__main__":
    unittest.main()
