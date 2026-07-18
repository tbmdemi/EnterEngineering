import unittest
from pathlib import Path


class ComplianceEvaluatorTest(unittest.TestCase):
    def test_compliance_authorization_denies_patient(self):
        from backend.app.core.contracts import Role
        from backend.app.core.errors import AppError
        from backend.app.features.compliance.router import _require_auditor, _require_staff

        for guard in (_require_staff, _require_auditor):
            with self.assertRaises(AppError) as caught:
                guard(Role.PATIENT)
            self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(_require_staff(Role.DENTIST), Role.DENTIST)
        self.assertEqual(_require_auditor(Role.QA), Role.QA)

    def test_compliance_routes_are_registered(self):
        root = Path(__file__).parents[2]
        backend = (root / "backend/app/main.py").read_text(encoding="utf-8")
        frontend = (root / "frontend/src/routes.js").read_text(encoding="utf-8")

        self.assertIn("compliance.router", backend)
        self.assertIn("complianceRoute", frontend)

    def test_unknown_encounter_is_rejected_before_compliance_write(self):
        from contextlib import contextmanager
        from unittest.mock import patch
        from backend.app.core.contracts import Role
        from backend.app.core.errors import AppError
        import importlib
        router = importlib.import_module("backend.app.features.compliance.router")

        class Connection:
            def execute(self, _query, _params): return self
            def fetchone(self): return None
        @contextmanager
        def connect(): yield Connection()
        with patch.object(router, "_connect", connect), self.assertRaises(AppError) as caught:
            router.evaluate_encounter("00000000-0000-0000-0000-000000000404", Role.DENTIST)
        self.assertEqual(caught.exception.status_code, 404)

    def test_compliance_ui_exposes_evaluate_readiness_audit_and_dashboard(self):
        root = Path(__file__).parents[2]
        source = (root / "frontend/src/features/compliance/index.jsx").read_text(encoding="utf-8")
        for endpoint in ("/evaluate", "/readiness", "/audit-events", "/dashboard"):
            self.assertIn(endpoint, source)

    def test_app_shell_renders_the_active_feature_route(self):
        root = Path(__file__).parents[2]
        source = (root / "frontend/src/main.jsx").read_text(encoding="utf-8")

        self.assertIn("window.location.pathname", source)
        self.assertIn("ActiveFeature = activeRoute.Component", source)
        self.assertIn("<ActiveFeature />", source)

    def test_maps_verified_draft_missing_and_conditional_evidence(self):
        from backend.app.features.compliance.evaluator import derive_context, evaluate

        evidence = {
            "DOC_CONSENT_SIGNED": {"state": "VERIFIED", "value": {"signed": True}},
            "DOC_PROGRESS_NOTE": {"state": "DRAFT", "value": {}},
            "DOC_MEDICATION_PRESCRIBED": {"state": "VERIFIED", "value": {"prescribed": False}},
            "PRE_PROCEDURE": {"state": "VERIFIED", "value": {"requires_imaging": False}},
        }
        result = {item["code"]: item for item in evaluate(evidence, derive_context(evidence))}

        self.assertEqual(result["DOC_CONSENT_SIGNED"]["state"], "SATISFIED")
        self.assertEqual(result["DOC_PROGRESS_NOTE"]["state"], "UNVERIFIED")
        self.assertEqual(result["PRE_ALLERGY"]["state"], "MISSING")
        self.assertEqual(result["DOC_MEDICATION_DETAILS"]["state"], "NOT_APPLICABLE")
        self.assertEqual(result["PRE_IMAGING"]["state"], "NOT_APPLICABLE")

    def test_verified_label_does_not_satisfy_structurally_invalid_evidence(self):
        from backend.app.features.compliance.evaluator import evaluate

        evidence = {
            "DOC_CONSENT_SIGNED": {"state": "VERIFIED", "value": {"signed": False}},
            "PRE_ALLERGY": {"state": "VERIFIED", "value": {}},
            "PRE_VITALS": {"state": "VERIFIED", "value": {"systolic": 0, "diastolic": 80, "pulse": 72}},
            "PRE_STERILIZATION": {"state": "VERIFIED", "value": {"confirmed": True}},
        }
        result = {item["code"]: item for item in evaluate(evidence)}

        for code in evidence:
            self.assertEqual(result[code]["state"], "UNVERIFIED", code)

    def test_unknown_conditional_context_stays_missing(self):
        from backend.app.features.compliance.evaluator import derive_context, evaluate

        evidence = {
            "DOC_MEDICATION_DETAILS": {"state": "VERIFIED", "value": {"detail": "Synthetic medication"}},
            "PRE_IMAGING": {"state": "VERIFIED", "value": {"reviewed": True, "imaging_reference": "XRAY-1", "performed_at": "2026-07-18T01:00:00Z"}},
        }
        result = {item["code"]: item for item in evaluate(evidence, derive_context(evidence))}

        self.assertEqual(result["DOC_MEDICATION_DETAILS"]["state"], "MISSING")
        self.assertEqual(result["PRE_IMAGING"]["state"], "MISSING")

    def test_failed_schedule_check_is_missing_not_satisfied(self):
        from backend.app.features.compliance.evaluator import evaluate

        result = {item["code"]: item for item in evaluate({
            "COORD_SCHEDULE_CLEAR": {"state": "VERIFIED", "value": {"clear": False}},
        })}

        self.assertEqual(result["COORD_SCHEDULE_CLEAR"]["state"], "MISSING")

    def test_task_reconciliation_reopens_and_cancels_with_same_key(self):
        from backend.app.features.compliance.evaluator import desired_task_status, task_key

        key = task_key("enc-1", "PRE_ALLERGY")
        self.assertEqual(desired_task_status("PENDING"), "OPEN")
        self.assertEqual(desired_task_status("MISSING"), "OPEN")
        self.assertEqual(desired_task_status("UNVERIFIED"), "OPEN")
        self.assertEqual(desired_task_status("SATISFIED"), "CANCELLED")
        self.assertEqual(desired_task_status("NOT_APPLICABLE"), "CANCELLED")
        self.assertEqual(key, task_key("enc-1", "PRE_ALLERGY"))

    def test_policy_covers_all_four_pain_point_groups(self):
        from backend.app.features.compliance.evaluator import POLICY

        codes = {item["code"] for item in POLICY}
        self.assertTrue(any(code.startswith("DOC_") for code in codes))
        self.assertTrue(any(code.startswith("PRE_") for code in codes))
        self.assertTrue(any(code.startswith("POST_") for code in codes))
        self.assertTrue(any(code.startswith("COORD_") for code in codes))
        self.assertEqual(len(codes), len(POLICY))

    def test_obligations_are_scoped_to_the_clinical_stage(self):
        from backend.app.features.compliance.evaluator import (
            POLICY_CODES,
            active_codes_for_stage,
            required_codes_for_transition,
        )

        self.assertEqual(active_codes_for_stage("CHECK_IN"), set())
        self.assertIn("PRE_ALLERGY", active_codes_for_stage("PRE_TREATMENT"))
        self.assertNotIn("POST_RECALL", active_codes_for_stage("PRE_TREATMENT"))
        self.assertIn("DOC_PROGRESS_NOTE", active_codes_for_stage("TREATMENT"))
        self.assertEqual(active_codes_for_stage("POST_TREATMENT"), POLICY_CODES)
        self.assertIn("DOC_CONSENT_SIGNED", required_codes_for_transition("TREATMENT"))
        self.assertNotIn("DOC_PROGRESS_NOTE", required_codes_for_transition("TREATMENT"))
        self.assertIn("DOC_PROGRESS_NOTE", required_codes_for_transition("POST_TREATMENT"))
        self.assertEqual(required_codes_for_transition("CLOSED"), POLICY_CODES)

    def test_partial_evaluation_does_not_create_future_stage_findings(self):
        from backend.app.features.compliance.evaluator import evaluate, required_codes_for_transition

        checks = evaluate({}, codes=required_codes_for_transition("TREATMENT"))
        codes = {item["code"] for item in checks}

        self.assertIn("PRE_ALLERGY", codes)
        self.assertIn("DOC_CONSENT_SIGNED", codes)
        self.assertNotIn("POST_RECALL", codes)
        self.assertTrue(all(item["state"] == "MISSING" for item in checks))

    def test_task_keys_are_stable_across_repeated_evaluation(self):
        from backend.app.features.compliance.evaluator import task_key

        first = task_key("enc-1", "PRE_ALLERGY")
        second = task_key("enc-1", "PRE_ALLERGY")

        self.assertEqual(first, second)
        self.assertEqual(first, "enc-1:PRE_ALLERGY:dental-policy.v1")

    def test_close_readiness_blocks_every_non_ready_obligation(self):
        from backend.app.features.compliance.service import blockers

        checks = [
            {"code": "PRE_ALLERGY", "state": "SATISFIED", "owner_role": "ASSISTANT"},
            {"code": "PRE_IMAGING", "state": "NOT_APPLICABLE", "owner_role": "DENTIST"},
            {"code": "POST_RECALL", "state": "MISSING", "owner_role": "FRONT_DESK"},
            {"code": "DOC_PROGRESS_NOTE", "state": "UNVERIFIED", "owner_role": "DENTIST"},
        ]

        self.assertEqual(
            [item["code"] for item in blockers(checks)],
            ["POST_RECALL", "DOC_PROGRESS_NOTE"],
        )

    def test_shared_demo_context_replaces_feature_hard_coded_roles(self):
        root = Path(__file__).parents[2]
        context = (root / "frontend/src/demo-context.jsx").read_text(encoding="utf-8")
        self.assertIn("URLSearchParams", context)
        self.assertIn("careguard.demoRole", context)
        self.assertIn("careguard.encounterId", context)
        for path in (
            "documentation-ai/index.jsx",
            "pre-treatment/index.jsx",
            "coordination/index.jsx",
            "post-treatment-chat/index.jsx",
            "compliance/index.jsx",
        ):
            source = (root / "frontend/src/features" / path).read_text(encoding="utf-8")
            self.assertIn("useDemoContext", source, path)


if __name__ == "__main__":
    unittest.main()
