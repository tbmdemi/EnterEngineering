import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.main import app


DATABASE_URL = os.environ.get("ENCOUNTER_TEST_DATABASE_URL")


@unittest.skipUnless(DATABASE_URL, "Set ENCOUNTER_TEST_DATABASE_URL to run PostgreSQL integration tests")
class DentalFlowIntegrationTest(unittest.TestCase):
    def setUp(self):
        os.environ["DATABASE_URL"] = DATABASE_URL
        self.patient_id = uuid4()
        self.appointment_id = uuid4()
        self.encounter_id = uuid4()
        self.client = TestClient(app, raise_server_exceptions=False)
        now = datetime.now(timezone.utc).replace(microsecond=0)
        import psycopg

        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "INSERT INTO patients (id, mrn, full_name, date_of_birth) VALUES (%s, %s, 'Integration Patient', '1990-01-01')",
                (self.patient_id, f"INT-{str(self.patient_id)[:8]}"),
            )
            connection.execute(
                """INSERT INTO appointments (id, patient_id, starts_at, ends_at, chair, status)
                   VALUES (%s, %s, %s, %s, 'INT-CHAIR', 'CHECKED_IN')""",
                (self.appointment_id, self.patient_id, now, now + timedelta(minutes=45)),
            )
            connection.execute(
                "INSERT INTO encounters (id, patient_id, appointment_id, stage) VALUES (%s, %s, %s, 'CHECK_IN')",
                (self.encounter_id, self.patient_id, self.appointment_id),
            )
            connection.execute(
                """INSERT INTO evidence_items
                     (encounter_id, code, state, value, source_type, source_ref, actor_role)
                   VALUES (%s, 'PRE_PROCEDURE', 'VERIFIED', '{"requires_imaging":false}', 'TEST', 'integration', 'QA')""",
                (self.encounter_id,),
            )

    def tearDown(self):
        import psycopg

        with psycopg.connect(DATABASE_URL) as connection:
            for table in ("audit_events", "obligation_checks", "tasks", "ai_runs", "evidence_items"):
                connection.execute(f"DELETE FROM {table} WHERE encounter_id = %s", (self.encounter_id,))
            connection.execute("DELETE FROM encounters WHERE id = %s", (self.encounter_id,))
            connection.execute("DELETE FROM appointments WHERE id = %s", (self.appointment_id,))
            connection.execute("DELETE FROM patients WHERE id = %s", (self.patient_id,))

    def request(self, method, path, role, **kwargs):
        response = self.client.request(method, path, headers={"X-Demo-Role": role}, **kwargs)
        self.assertLess(response.status_code, 400, response.text)
        return response.json()

    def advance(self, stage, version):
        return self.request(
            "POST",
            f"/api/v1/encounters/{self.encounter_id}/stage",
            "DENTIST",
            json={"stage": stage, "version": version},
        )

    def test_full_flow_blocks_then_closes_after_all_modules_produce_evidence(self):
        self.advance("PRE_TREATMENT", 1)
        self.request("POST", "/api/v1/documentation", "DENTIST", json={
            "encounter_id": str(self.encounter_id),
            "consent_signed": True,
            "treatment_plan_signed": True,
            "progress_note": "Routine cleaning completed.",
            "tooth": "11",
            "surface": "F",
            "medication_prescribed": False,
        })

        performed_at = datetime.now(timezone.utc).isoformat()
        for code, value in {
            "PRE_MEDICAL_HISTORY": {"summary": "Reviewed"},
            "PRE_ALLERGY": {"status": "NONE_KNOWN"},
            "PRE_VITALS": {"systolic": 120, "diastolic": 80, "pulse": 72},
            "PRE_STERILIZATION": {"cycle_or_tray_id": "INT-CYCLE"},
        }.items():
            self.request(
                "PUT", f"/api/v1/encounters/{self.encounter_id}/pre-treatment/{code}",
                "ASSISTANT", json={"value": value, "performed_at": performed_at},
            )

        self.request("POST", f"/api/v1/encounters/{self.encounter_id}/coordination/evaluate", "FRONT_DESK")
        handoff = self.request("POST", "/api/v1/coordination/tasks", "FRONT_DESK", json={
            "encounter_id": str(self.encounter_id),
            "obligation_code": "COORD_HANDOFF_ACK",
            "task_type": "HANDOFF",
            "owner_role": "ASSISTANT",
        })
        self.request("POST", f"/api/v1/tasks/{handoff['id']}/acknowledge", "ASSISTANT")
        self.request("POST", "/api/v1/coordination/tasks", "FRONT_DESK", json={
            "encounter_id": str(self.encounter_id),
            "obligation_code": "COORD_REFERRAL_OWNER",
            "task_type": "REFERRAL",
            "owner_role": "DENTIST",
        })

        self.advance("TREATMENT", 2)
        self.advance("POST_TREATMENT", 3)
        blocked = self.client.post(
            f"/api/v1/encounters/{self.encounter_id}/stage",
            headers={"X-Demo-Role": "DENTIST"},
            json={"stage": "CLOSED", "version": 4},
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["code"], "COMPLIANCE_NOT_READY")

        now = datetime.now(timezone.utc)
        self.request("POST", f"/api/v1/encounters/{self.encounter_id}/release", "DENTIST", json={
            "care_instructions": "Keep the area clean.",
            "recall_at": (now + timedelta(days=30)).isoformat(),
            "monitor_until": (now + timedelta(days=7)).isoformat(),
        })
        readiness = self.request("GET", f"/api/v1/encounters/{self.encounter_id}/readiness", "QA")
        self.assertTrue(readiness["ready_to_close"])
        closed = self.advance("CLOSED", 4)
        self.assertEqual((closed["stage"], closed["version"]), ("CLOSED", 5))
