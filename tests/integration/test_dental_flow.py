import os
import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
from unittest.mock import patch

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
        premature_treatment = self.client.post(
            f"/api/v1/encounters/{self.encounter_id}/stage",
            headers={"X-Demo-Role": "DENTIST"},
            json={"stage": "TREATMENT", "version": 2},
        )
        self.assertEqual(premature_treatment.status_code, 409)
        self.assertEqual(premature_treatment.json()["code"], "STAGE_REQUIREMENTS_NOT_READY")
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
            "PRE_MEDICAL_HISTORY": {"summary": "Reviewed", "reviewed_source_refs": ["DOC-DEMO-001"]},
            "PRE_ALLERGY": {"status": "NONE_KNOWN"},
            "PRE_VITALS": {"systolic": 120, "diastolic": 80, "pulse": 72},
            "PRE_STERILIZATION": {"confirmed": True, "cycle_or_tray_id": "INT-CYCLE"},
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
        release_payload = {
            "care_instructions": "Keep the area clean.",
            "recall_at": (now + timedelta(days=30)).isoformat(),
            "monitor_until": (now + timedelta(days=7)).isoformat(),
        }
        first_release = self.request("POST", f"/api/v1/encounters/{self.encounter_id}/release", "DENTIST", json=release_payload)
        replay = self.request("POST", f"/api/v1/encounters/{self.encounter_id}/release", "DENTIST", json=release_payload)
        self.assertFalse(first_release["idempotent_replay"])
        self.assertTrue(replay["idempotent_replay"])
        readiness = self.request("GET", f"/api/v1/encounters/{self.encounter_id}/readiness", "QA")
        self.assertTrue(readiness["ready_to_close"])
        closed = self.advance("CLOSED", 4)
        self.assertEqual((closed["stage"], closed["version"]), ("CLOSED", 5))
        self.assertEqual(closed["appointment"]["status"], "FULFILLED")

        immutable = self.client.post(
            f"/api/v1/encounters/{self.encounter_id}/release",
            headers={"X-Demo-Role": "DENTIST"},
            json={
                "care_instructions": "Changed after close.",
                "recall_at": (now + timedelta(days=60)).isoformat(),
                "monitor_until": (now + timedelta(days=14)).isoformat(),
            },
        )
        self.assertEqual(immutable.status_code, 409)
        self.assertEqual(immutable.json()["code"], "ENCOUNTER_CLOSED")

    def test_live_ai_failure_persists_abstention_without_raw_note(self):
        raw_note = "Sensitive synthetic note that must not be stored on provider failure."
        with patch.dict(os.environ, {"AI_MODE": "live"}, clear=False):
            for name in ("MODEL_BASE_URL", "MODEL_API_KEY", "MODEL_NAME"):
                os.environ.pop(name, None)
            response = self.client.post(
                "/api/v1/ai/extract-note",
                headers={"X-Demo-Role": "ASSISTANT"},
                json={"encounter_id": str(self.encounter_id), "note": raw_note},
            )

        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["code"], "AI_PROVIDER_UNAVAILABLE")
        self.assertEqual(response.json()["details"]["state"], "ABSTAINED")
        self.assertTrue(response.json()["details"]["manual_fallback"])

        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(DATABASE_URL, row_factory=dict_row) as connection:
            run = connection.execute(
                "SELECT status, output FROM ai_runs WHERE id = %s",
                (response.json()["details"]["ai_run_id"],),
            ).fetchone()
            audit = connection.execute(
                """SELECT metadata FROM audit_events
                   WHERE encounter_id = %s AND action = 'AI_EXTRACTION_ABSTAINED'
                   ORDER BY created_at DESC LIMIT 1""",
                (self.encounter_id,),
            ).fetchone()
        self.assertEqual(run["status"], "ABSTAINED")
        self.assertNotIn(raw_note, str(run["output"]))
        self.assertNotIn(raw_note, str(audit["metadata"]))

    def test_patient_chat_rejects_unknown_encounter_with_stable_contract(self):
        response = self.client.post(
            "/api/v1/portal/chat",
            headers={"X-Demo-Role": "PATIENT"},
            json={"encounter_id": str(uuid4()), "message": "Giờ mở cửa?"},
        )
        self.assertEqual(response.status_code, 404, response.text)
        self.assertEqual(response.json()["code"], "ENCOUNTER_NOT_FOUND")
