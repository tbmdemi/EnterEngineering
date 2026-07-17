import os
import unittest
from unittest.mock import patch

from pydantic import ValidationError


class DocumentationAiTest(unittest.TestCase):
    def test_medication_details_are_required_only_when_medication_is_used(self):
        from backend.app.features.documentation_ai.api import DocumentationInput

        common = dict(
            encounter_id="00000000-0000-0000-0000-000000000001",
            consent_signed=True,
            treatment_plan_signed=True,
            progress_note="Composite restoration completed.",
            tooth="14",
            surface="O",
        )
        DocumentationInput(**common, medication_used=False)
        with self.assertRaises(ValidationError):
            DocumentationInput(**common, medication_used=True)
        self.assertEqual(
            DocumentationInput(**common, medication_used=True, medication_detail="Lidocaine 2%, 1.8 mL").medication_detail,
            "Lidocaine 2%, 1.8 mL",
        )

    def test_missing_provider_config_uses_fixture_with_exact_source_span(self):
        from backend.app.features.documentation_ai.api import ExtractNoteInput, extract_note

        note = "Reviewed history. Tooth 14 surface O restored. Patient tolerated procedure."
        with patch.dict(os.environ, {}, clear=True), patch(
            "backend.app.features.documentation_ai.api._save_run", return_value="run-1"
        ):
            result = extract_note(ExtractNoteInput(encounter_id="00000000-0000-0000-0000-000000000001", note=note))

        self.assertEqual(result.state, "UNVERIFIED")
        self.assertEqual(result.ai_run_id, "run-1")
        self.assertEqual(result.facts[0].tooth, "14")
        self.assertEqual(result.facts[0].surface, "O")
        self.assertEqual(result.facts[0].source_span, "Tooth 14 surface O restored.")
        self.assertIn(result.facts[0].source_span, note)

    def test_accept_is_the_only_review_action_that_writes_verified_evidence(self):
        from backend.app.core.contracts import Role
        from backend.app.features.documentation_ai.api import ReviewInput, accept_run, reject_run

        run = {
            "id": "00000000-0000-0000-0000-000000000010",
            "encounter_id": "00000000-0000-0000-0000-000000000001",
            "status": "UNVERIFIED",
            "output": {"facts": [{"fact": "procedure_documented", "tooth": "14", "surface": "O", "source_span": "Tooth 14 surface O restored."}]},
        }
        review = ReviewInput(evidence_code="DOC_PROGRESS_NOTE")
        with patch("backend.app.features.documentation_ai.api._load_run", return_value=run), patch(
            "backend.app.features.documentation_ai.api._mark_reviewed"
        ), patch("backend.app.features.documentation_ai.api.upsert_evidence") as upsert, patch(
            "backend.app.features.documentation_ai.api.append_audit"
        ) as audit:
            accepted = accept_run(run["id"], review, Role.DENTIST)
            rejected = reject_run(run["id"], Role.DENTIST)

        self.assertEqual(accepted["state"], "VERIFIED")
        self.assertEqual(rejected["state"], "REJECTED")
        upsert.assert_called_once()
        self.assertEqual(upsert.call_args.args[2], "VERIFIED")
        self.assertEqual(audit.call_count, 2)


if __name__ == "__main__":
    unittest.main()
