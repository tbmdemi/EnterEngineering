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
        backend = (root / "backend/app/main.py").read_text()
        frontend = (root / "frontend/src/routes.js").read_text()

        self.assertIn("compliance.router", backend)
        self.assertIn("complianceRoute", frontend)

    def test_maps_verified_draft_missing_and_conditional_evidence(self):
        from backend.app.features.compliance.evaluator import evaluate

        result = {item["code"]: item for item in evaluate(
            {
                "DOC_CONSENT_SIGNED": {"state": "VERIFIED"},
                "DOC_PROGRESS_NOTE": {"state": "DRAFT"},
            },
            {"medication_prescribed": False, "imaging_required": False},
        )}

        self.assertEqual(result["DOC_CONSENT_SIGNED"]["state"], "SATISFIED")
        self.assertEqual(result["DOC_PROGRESS_NOTE"]["state"], "UNVERIFIED")
        self.assertEqual(result["PRE_ALLERGY"]["state"], "MISSING")
        self.assertEqual(result["DOC_MEDICATION_DETAILS"]["state"], "NOT_APPLICABLE")
        self.assertEqual(result["PRE_IMAGING"]["state"], "NOT_APPLICABLE")

    def test_policy_covers_all_four_pain_point_groups(self):
        from backend.app.features.compliance.evaluator import POLICY

        codes = {item["code"] for item in POLICY}
        self.assertTrue(any(code.startswith("DOC_") for code in codes))
        self.assertTrue(any(code.startswith("PRE_") for code in codes))
        self.assertTrue(any(code.startswith("POST_") for code in codes))
        self.assertTrue(any(code.startswith("COORD_") for code in codes))
        self.assertEqual(len(codes), len(POLICY))

    def test_task_keys_are_stable_across_repeated_evaluation(self):
        from backend.app.features.compliance.evaluator import task_key

        first = task_key("enc-1", "PRE_ALLERGY")
        second = task_key("enc-1", "PRE_ALLERGY")

        self.assertEqual(first, second)
        self.assertEqual(first, "enc-1:PRE_ALLERGY:dental-policy.v1")


if __name__ == "__main__":
    unittest.main()
