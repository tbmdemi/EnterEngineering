import unittest
import importlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from backend.app.core.contracts import Role
feature = importlib.import_module("backend.app.features.pre_treatment.router")


class PreTreatmentTest(unittest.TestCase):
    def test_patient_cannot_read_internal_checklist(self):
        with self.assertRaises(feature.AppError) as caught:
            feature.get_checklist("encounter-1", Role.PATIENT)
        self.assertEqual(caught.exception.status_code, 403)

    def test_checklist_keeps_missing_items_visible_and_marks_imaging_not_applicable(self):
        rows = [
            {"code": "PRE_PROCEDURE", "state": "VERIFIED", "value": {"requires_imaging": False}},
            {"code": "PRE_ALLERGY", "state": "VERIFIED", "value": {"answer": "none"}, "actor_role": "ASSISTANT", "updated_at": datetime.now(timezone.utc)},
        ]

        with patch.object(feature, "_read_evidence", return_value=rows):
            result = feature.get_checklist("encounter-1", Role.ASSISTANT)

        by_code = {item["code"]: item for item in result["items"]}
        self.assertIsNone(by_code["PRE_STERILIZATION"]["evidence"])
        self.assertTrue(by_code["PRE_ALLERGY"]["applicable"])
        self.assertFalse(by_code["PRE_IMAGING"]["applicable"])
        self.assertEqual(by_code["PRE_IMAGING"]["suggested_obligation_state"], "NOT_APPLICABLE")

    def test_attestation_requires_staff_role_and_timezone_timestamp(self):
        body = feature.Attestation(value={"answer": "none"}, performed_at=datetime(2026, 7, 17, 9))
        with self.assertRaises(feature.AppError) as caught:
            feature.put_attestation("enc", "PRE_ALLERGY", body, Role.ASSISTANT)
        self.assertEqual(caught.exception.payload["code"], "PERFORMED_AT_TIMEZONE_REQUIRED")

        aware = feature.Attestation(value={"answer": "none"}, performed_at=datetime(2026, 7, 17, 9, tzinfo=timezone.utc))
        with self.assertRaises(feature.AppError) as caught:
            feature.put_attestation("enc", "PRE_ALLERGY", aware, Role.PATIENT)
        self.assertEqual(caught.exception.status_code, 403)

    def test_attestation_uses_shared_evidence_and_audit_services(self):
        performed_at = datetime(2026, 7, 17, 2, tzinfo=timezone.utc)
        body = feature.Attestation(value={"confirmed": True}, performed_at=performed_at)
        evidence = {"id": "00000000-0000-0000-0000-000000000099", "code": "PRE_STERILIZATION"}

        with patch.object(feature.services, "upsert_evidence", return_value=evidence) as upsert, patch.object(feature.services, "append_audit") as audit:
            result = feature.put_attestation("enc", "PRE_STERILIZATION", body, Role.DENTIST)

        stored = {"confirmed": True, "performed_at": "2026-07-17T02:00:00+00:00"}
        upsert.assert_called_once_with("enc", "PRE_STERILIZATION", "VERIFIED", stored, "FORM", "pre-treatment", "DENTIST")
        audit.assert_called_once_with("DENTIST", "PRE_TREATMENT_ATTESTED", "evidence", evidence["id"], "enc", {"code": "PRE_STERILIZATION", "performed_at": stored["performed_at"]})
        self.assertEqual(result, evidence)

    def test_imaging_attestation_is_server_marked_na_when_procedure_does_not_require_it(self):
        body = feature.Attestation(value={"completed": True}, performed_at=datetime(2026, 7, 17, 2, tzinfo=timezone.utc))
        with patch.object(feature, "_requires_imaging", return_value=False), patch.object(feature.services, "upsert_evidence", return_value={"id": "evidence"}) as upsert, patch.object(feature.services, "append_audit"):
            feature.put_attestation("enc", "PRE_IMAGING", body, Role.ASSISTANT)

        self.assertTrue(upsert.call_args.args[3]["not_applicable"])

    def test_unknown_procedure_keeps_imaging_applicable_and_preserves_attestation(self):
        with patch.object(feature, "_read_evidence", return_value=[]):
            result = feature.get_checklist("enc", Role.ASSISTANT)
        imaging = next(item for item in result["items"] if item["code"] == "PRE_IMAGING")
        self.assertTrue(imaging["applicable"])
        self.assertIsNone(imaging["suggested_obligation_state"])

        body = feature.Attestation(value={"completed": True}, performed_at=datetime(2026, 7, 17, 2, tzinfo=timezone.utc))
        with patch.object(feature, "_requires_imaging", return_value=None), patch.object(feature.services, "upsert_evidence", return_value={"id": "evidence"}) as upsert, patch.object(feature.services, "append_audit"):
            feature.put_attestation("enc", "PRE_IMAGING", body, Role.ASSISTANT)
        self.assertEqual(upsert.call_args.args[3]["completed"], True)
        self.assertNotIn("not_applicable", upsert.call_args.args[3])

    def test_attestation_normalizes_positive_offset_to_utc(self):
        body = feature.Attestation(value={"confirmed": True}, performed_at=datetime(2026, 7, 17, 9, tzinfo=timezone(timedelta(hours=7))))
        with patch.object(feature.services, "upsert_evidence", return_value={"id": "evidence"}) as upsert, patch.object(feature.services, "append_audit"):
            feature.put_attestation("enc", "PRE_ALLERGY", body, Role.ASSISTANT)
        self.assertEqual(upsert.call_args.args[3]["performed_at"], "2026-07-17T02:00:00+00:00")

    def test_requires_imaging_treats_null_and_malformed_values_as_unknown(self):
        for value in (None, 0, "false"):
            rows = [{"code": "PRE_PROCEDURE", "state": "VERIFIED", "value": {"requires_imaging": value}}]
            with self.subTest(value=value), patch.object(feature, "_read_evidence", return_value=rows):
                self.assertIsNone(feature._requires_imaging("enc"))

        rows = [{"code": "PRE_PROCEDURE", "state": "VERIFIED", "value": {}}]
        with patch.object(feature, "_read_evidence", return_value=rows):
            self.assertIsNone(feature._requires_imaging("enc"))


if __name__ == "__main__":
    unittest.main()
