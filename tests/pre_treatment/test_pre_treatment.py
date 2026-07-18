import unittest
import importlib
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from pydantic import ValidationError

from backend.app.core.contracts import Role
feature = importlib.import_module("backend.app.features.pre_treatment.router")


def transaction(procedure=None, stage="PRE_TREATMENT", calls=None):
    class Result:
        def __init__(self, row=None, rowcount=0):
            self._row = row
            self.rowcount = rowcount

        def fetchone(self):
            return self._row

    class Connection:
        def execute(self, query, _params):
            if calls is not None:
                calls.append((query, _params))
            if "SELECT 1 FROM encounters" in query:
                return Result({"exists": 1})
            if "SELECT stage FROM encounters" in query:
                return Result({"stage": stage} if stage is not None else None)
            if "code = 'PRE_PROCEDURE'" in query:
                return Result(procedure)
            return Result()

    @contextmanager
    def connect():
        yield Connection()

    return connect


class PreTreatmentTest(unittest.TestCase):
    def test_patient_cannot_read_internal_checklist(self):
        with self.assertRaises(feature.AppError) as caught:
            feature.get_checklist("encounter-1", Role.PATIENT)
        self.assertEqual(caught.exception.status_code, 403)

    def test_attestation_rejects_unknown_checklist_code(self):
        body = feature.Attestation(
            value={"confirmed": True},
            performed_at=datetime(2026, 7, 17, 2, tzinfo=timezone.utc),
        )

        with self.assertRaises(feature.AppError) as caught:
            feature.put_attestation("enc", "PRE_UNKNOWN", body, Role.ASSISTANT)

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.payload["code"], "PRE_TREATMENT_CODE_INVALID")

    def test_checklist_keeps_missing_items_visible_and_marks_imaging_not_applicable(self):
        rows = [
            {"code": "PRE_PROCEDURE", "state": "VERIFIED", "value": {"requires_imaging": False}},
            {"code": "PRE_ALLERGY", "state": "VERIFIED", "value": {"answer": "none"}, "actor_role": "ASSISTANT", "updated_at": datetime.now(timezone.utc)},
        ]

        with patch.object(feature, "_require_encounter"), patch.object(feature, "_read_evidence", return_value=rows), patch.object(feature, "_read_audit", return_value=[]):
            result = feature.get_checklist("encounter-1", Role.ASSISTANT)

        by_code = {item["code"]: item for item in result["items"]}
        self.assertIsNone(by_code["PRE_STERILIZATION"]["evidence"])
        self.assertTrue(by_code["PRE_ALLERGY"]["applicable"])
        self.assertFalse(by_code["PRE_IMAGING"]["applicable"])
        self.assertEqual(by_code["PRE_IMAGING"]["suggested_obligation_state"], "NOT_APPLICABLE")
        self.assertFalse(result["procedure"]["requires_imaging"])

    def test_checklist_exposes_draft_ai_review_with_citations_for_each_check(self):
        with patch.object(feature, "_require_encounter"), patch.object(feature, "_read_evidence", return_value=[]), patch.object(feature, "_read_audit", return_value=[]):
            result = feature.get_checklist("enc", Role.ASSISTANT)

        for item in result["items"]:
            review = item["ai_review"]
            self.assertEqual(review["state"], "DRAFT")
            self.assertTrue(review["suggestion"])
            self.assertTrue(review["citations"])
            self.assertTrue(review["citations"][0]["ref"])

    def test_attestation_requires_staff_role_and_timezone_timestamp(self):
        body = feature.Attestation(value={"answer": "none"}, performed_at=datetime(2026, 7, 17, 9))
        with self.assertRaises(feature.AppError) as caught:
            feature.put_attestation("enc", "PRE_ALLERGY", body, Role.ASSISTANT)
        self.assertEqual(caught.exception.payload["code"], "PERFORMED_AT_TIMEZONE_REQUIRED")

        aware = feature.Attestation(value={"answer": "none"}, performed_at=datetime(2026, 7, 17, 9, tzinfo=timezone.utc))
        with self.assertRaises(feature.AppError) as caught:
            feature.put_attestation("enc", "PRE_ALLERGY", aware, Role.PATIENT)
        self.assertEqual(caught.exception.status_code, 403)

    def test_clinical_staff_can_declare_procedure_imaging_applicability(self):
        body = feature.ProcedureDeclaration(
            requires_imaging=True,
            performed_at=datetime(2026, 7, 18, 9, tzinfo=timezone(timedelta(hours=7))),
        )
        evidence = {"id": "procedure-evidence", "code": "PRE_PROCEDURE"}
        calls = []
        existing = {"state": "VERIFIED", "value": {"requires_imaging": False}}

        with patch.object(feature.services, "_connect", transaction(existing, calls=calls)), patch.object(feature.services, "require_encounter_in"), patch.object(feature.services, "upsert_evidence", return_value=evidence) as upsert, patch.object(feature.services, "append_audit") as audit:
            result = feature.put_procedure_declaration("enc", body, Role.DENTIST)

        upsert.assert_called_once_with(
            "enc",
            "PRE_PROCEDURE",
            "VERIFIED",
            {"requires_imaging": True, "performed_at": "2026-07-18T02:00:00+00:00"},
            "FORM",
            "pre-treatment-procedure",
            "DENTIST",
        )
        self.assertTrue(any("DELETE FROM evidence_items" in query and "PRE_IMAGING" in query for query, _params in calls))
        self.assertTrue(audit.call_args.args[5]["imaging_attestation_invalidated"])
        self.assertEqual(result, evidence)

    def test_procedure_declaration_accepts_http_datetime_but_requires_a_real_boolean(self):
        body = feature.ProcedureDeclaration.model_validate_json(
            '{"requires_imaging":true,"performed_at":"2026-07-18T02:00:00Z"}'
        )
        self.assertTrue(body.requires_imaging)
        self.assertEqual(body.performed_at.tzinfo, timezone.utc)

        with self.assertRaises(ValidationError):
            feature.ProcedureDeclaration.model_validate_json(
                '{"requires_imaging":"true","performed_at":"2026-07-18T02:00:00Z"}'
            )

    def test_procedure_declaration_has_role_timezone_and_stage_guards(self):
        aware = feature.ProcedureDeclaration(
            requires_imaging=False,
            performed_at=datetime(2026, 7, 18, 2, tzinfo=timezone.utc),
        )
        with self.assertRaises(feature.AppError) as caught:
            feature.put_procedure_declaration("enc", aware, Role.FRONT_DESK)
        self.assertEqual(caught.exception.status_code, 403)

        naive = feature.ProcedureDeclaration(
            requires_imaging=False,
            performed_at=datetime(2026, 7, 18, 2),
        )
        with self.assertRaises(feature.AppError) as caught:
            feature.put_procedure_declaration("enc", naive, Role.ASSISTANT)
        self.assertEqual(caught.exception.payload["code"], "PERFORMED_AT_TIMEZONE_REQUIRED")

        with patch.object(feature.services, "_connect", transaction(stage="TREATMENT")), patch.object(feature.services, "require_encounter_in"), self.assertRaises(feature.AppError) as caught:
            feature.put_procedure_declaration("enc", aware, Role.ASSISTANT)
        self.assertEqual(caught.exception.payload["code"], "PRE_TREATMENT_STAGE_INVALID")

    def test_attestation_uses_shared_evidence_and_audit_services(self):
        performed_at = datetime(2026, 7, 17, 2, tzinfo=timezone.utc)
        body = feature.Attestation(
            value={"confirmed": True, "cycle_or_tray_id": "CYCLE-001"},
            performed_at=performed_at,
        )
        evidence = {"id": "00000000-0000-0000-0000-000000000099", "code": "PRE_STERILIZATION"}

        with patch.object(feature.services, "_connect", transaction()), patch.object(feature.services, "require_encounter_in"), patch.object(feature.services, "upsert_evidence", return_value=evidence) as upsert, patch.object(feature.services, "append_audit") as audit:
            result = feature.put_attestation("enc", "PRE_STERILIZATION", body, Role.DENTIST)

        stored = {"confirmed": True, "cycle_or_tray_id": "CYCLE-001", "performed_at": "2026-07-17T02:00:00+00:00"}
        upsert.assert_called_once_with("enc", "PRE_STERILIZATION", "VERIFIED", stored, "FORM", "pre-treatment", "DENTIST")
        audit.assert_called_once_with("DENTIST", "PRE_TREATMENT_ATTESTED", "evidence", evidence["id"], "enc", {"code": "PRE_STERILIZATION", "performed_at": stored["performed_at"]})
        self.assertEqual(result, evidence)

    def test_medical_history_attestation_accepts_only_cited_source_refs(self):
        body = feature.Attestation(
            value={"summary": "No relevant contraindications noted.", "reviewed_source_refs": ["DOC-DEMO-001", "DOC-DEMO-001"]},
            performed_at=datetime(2026, 7, 18, 2, tzinfo=timezone.utc),
        )
        with patch.object(feature.services, "_connect", transaction()), patch.object(feature.services, "require_encounter_in"), patch.object(feature.services, "upsert_evidence", return_value={"id": "evidence"}) as upsert, patch.object(feature.services, "append_audit"):
            feature.put_attestation("enc", "PRE_MEDICAL_HISTORY", body, Role.ASSISTANT)

        self.assertEqual(upsert.call_args.args[3]["reviewed_source_refs"], ["DOC-DEMO-001"])

        invalid = feature.Attestation(
            value={"summary": "Untrusted", "reviewed_source_refs": ["FAKE-SOURCE"]},
            performed_at=datetime(2026, 7, 18, 2, tzinfo=timezone.utc),
        )
        with patch.object(feature.services, "_connect", transaction()), patch.object(feature.services, "require_encounter_in"), self.assertRaises(feature.AppError) as caught:
            feature.put_attestation("enc", "PRE_MEDICAL_HISTORY", invalid, Role.ASSISTANT)
        self.assertEqual(caught.exception.payload["code"], "PRE_TREATMENT_SOURCE_REF_INVALID")
        self.assertEqual(caught.exception.status_code, 422)

    def test_medical_history_requires_summary_and_at_least_one_reviewed_source(self):
        invalid_values = (
            {"summary": "Reviewed"},
            {"summary": "Reviewed", "reviewed_source_refs": []},
            {"summary": "   ", "reviewed_source_refs": ["DOC-DEMO-001"]},
        )

        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(feature.AppError) as caught:
                feature._validated_value("PRE_MEDICAL_HISTORY", value)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(caught.exception.payload["code"], "PRE_TREATMENT_VALUE_INVALID")

    def test_allergy_requires_known_status_and_allergen_when_present(self):
        self.assertEqual(
            feature._validated_value("PRE_ALLERGY", {"status": "NONE_KNOWN"}),
            {"status": "NONE_KNOWN"},
        )
        self.assertEqual(
            feature._validated_value("PRE_ALLERGY", {"status": "PRESENT", "allergen": "  penicillin  "}),
            {"status": "PRESENT", "allergen": "penicillin"},
        )

        for value in ({}, {"status": "UNKNOWN"}, {"status": "PRESENT"}, {"status": "PRESENT", "allergen": "  "}):
            with self.subTest(value=value), self.assertRaises(feature.AppError) as caught:
                feature._validated_value("PRE_ALLERGY", value)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(caught.exception.payload["code"], "PRE_TREATMENT_VALUE_INVALID")

    def test_vitals_require_finite_positive_numeric_readings(self):
        valid = feature._validated_value("PRE_VITALS", {"systolic": 120, "diastolic": 80, "pulse": 72})
        self.assertEqual(valid, {"systolic": 120.0, "diastolic": 80.0, "pulse": 72.0})

        invalid_values = (
            {"systolic": 0, "diastolic": 80, "pulse": 72},
            {"systolic": 120, "diastolic": -1, "pulse": 72},
            {"systolic": 120, "diastolic": 80, "pulse": True},
            {"systolic": "120", "diastolic": 80, "pulse": 72},
            {"systolic": float("inf"), "diastolic": 80, "pulse": 72},
        )
        for value in invalid_values:
            with self.subTest(value=value), self.assertRaises(feature.AppError) as caught:
                feature._validated_value("PRE_VITALS", value)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(caught.exception.payload["code"], "PRE_TREATMENT_VALUE_INVALID")

    def test_sterilization_and_applicable_imaging_require_explicit_confirmation(self):
        cases = (
            ("PRE_STERILIZATION", {"confirmed": False, "cycle_or_tray_id": "CYCLE-1"}),
            ("PRE_STERILIZATION", {"confirmed": True, "cycle_or_tray_id": "  "}),
            ("PRE_IMAGING", {"reviewed": False, "imaging_reference": "XRAY-1"}),
            ("PRE_IMAGING", {"reviewed": True, "imaging_reference": ""}),
        )
        for code, value in cases:
            with self.subTest(code=code, value=value), self.assertRaises(feature.AppError) as caught:
                feature._validated_value(code, value)
            self.assertEqual(caught.exception.status_code, 422)
            self.assertEqual(caught.exception.payload["code"], "PRE_TREATMENT_VALUE_INVALID")

    def test_imaging_attestation_is_server_marked_na_when_procedure_does_not_require_it(self):
        body = feature.Attestation(value={"completed": True}, performed_at=datetime(2026, 7, 17, 2, tzinfo=timezone.utc))
        procedure = {"state": "VERIFIED", "value": {"requires_imaging": False}}
        with patch.object(feature.services, "_connect", transaction(procedure)), patch.object(feature.services, "require_encounter_in"), patch.object(feature.services, "upsert_evidence", return_value={"id": "evidence"}) as upsert, patch.object(feature.services, "append_audit"):
            feature.put_attestation("enc", "PRE_IMAGING", body, Role.ASSISTANT)

        self.assertTrue(upsert.call_args.args[3]["not_applicable"])

    def test_closed_encounter_rejects_attestation_without_writing(self):
        body = feature.Attestation(
            value={"status": "NONE_KNOWN"},
            performed_at=datetime(2026, 7, 17, 2, tzinfo=timezone.utc),
        )
        with patch.object(feature.services, "_connect", transaction(stage="CLOSED")), patch.object(feature.services, "require_encounter_in"), patch.object(feature.services, "upsert_evidence") as upsert, self.assertRaises(feature.AppError) as caught:
            feature.put_attestation("enc", "PRE_ALLERGY", body, Role.ASSISTANT)

        self.assertEqual(caught.exception.payload["code"], "ENCOUNTER_CLOSED")
        self.assertEqual(caught.exception.status_code, 409)
        upsert.assert_not_called()

    def test_closed_encounter_rejects_demo_reset_before_deleting_evidence(self):
        with patch.object(feature.services, "_connect", transaction(stage="CLOSED")), self.assertRaises(feature.AppError) as caught:
            feature._reset_demo_data("enc", "QA")

        self.assertEqual(caught.exception.payload["code"], "ENCOUNTER_CLOSED")
        self.assertEqual(caught.exception.status_code, 409)

    def test_pre_treatment_cannot_be_changed_after_treatment_started(self):
        body = feature.Attestation(
            value={"status": "NONE_KNOWN"},
            performed_at=datetime(2026, 7, 17, 2, tzinfo=timezone.utc),
        )
        with patch.object(feature.services, "_connect", transaction(stage="TREATMENT")), patch.object(feature.services, "require_encounter_in"), self.assertRaises(feature.AppError) as caught:
            feature.put_attestation("enc", "PRE_ALLERGY", body, Role.ASSISTANT)
        self.assertEqual(caught.exception.payload["code"], "PRE_TREATMENT_STAGE_INVALID")

        with patch.object(feature.services, "_connect", transaction(stage="POST_TREATMENT")), self.assertRaises(feature.AppError) as caught:
            feature._reset_demo_data("enc", "QA")
        self.assertEqual(caught.exception.payload["code"], "PRE_TREATMENT_STAGE_INVALID")

    def test_unknown_procedure_keeps_imaging_applicable_and_preserves_attestation(self):
        with patch.object(feature, "_require_encounter"), patch.object(feature, "_read_evidence", return_value=[]), patch.object(feature, "_read_audit", return_value=[]):
            result = feature.get_checklist("enc", Role.ASSISTANT)
        imaging = next(item for item in result["items"] if item["code"] == "PRE_IMAGING")
        self.assertTrue(imaging["applicable"])
        self.assertIsNone(imaging["suggested_obligation_state"])

        body = feature.Attestation(
            value={"reviewed": True, "imaging_reference": "XRAY-001"},
            performed_at=datetime(2026, 7, 17, 2, tzinfo=timezone.utc),
        )
        with patch.object(feature.services, "_connect", transaction()), patch.object(feature.services, "require_encounter_in"), patch.object(feature.services, "upsert_evidence", return_value={"id": "evidence"}) as upsert, patch.object(feature.services, "append_audit"):
            feature.put_attestation("enc", "PRE_IMAGING", body, Role.ASSISTANT)
        self.assertEqual(upsert.call_args.args[3]["reviewed"], True)
        self.assertEqual(upsert.call_args.args[3]["imaging_reference"], "XRAY-001")
        self.assertNotIn("not_applicable", upsert.call_args.args[3])

    def test_attestation_normalizes_positive_offset_to_utc(self):
        body = feature.Attestation(value={"status": "NONE_KNOWN"}, performed_at=datetime(2026, 7, 17, 9, tzinfo=timezone(timedelta(hours=7))))
        with patch.object(feature.services, "_connect", transaction()), patch.object(feature.services, "require_encounter_in"), patch.object(feature.services, "upsert_evidence", return_value={"id": "evidence"}) as upsert, patch.object(feature.services, "append_audit"):
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

    def test_qa_can_reset_the_demo_to_a_blank_imaging_required_scenario(self):
        with patch.object(feature, "_reset_demo_data", return_value=5) as reset, patch.object(feature, "get_checklist", return_value={"items": []}):
            result = feature.reset_demo("enc", Role.QA)

        reset.assert_called_once_with("enc", "QA")
        self.assertEqual(result, {"items": []})


if __name__ == "__main__":
    unittest.main()
