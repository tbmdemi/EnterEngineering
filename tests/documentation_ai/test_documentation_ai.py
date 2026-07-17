import os
import unittest
from pathlib import Path
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
        from backend.app.core.contracts import Role
        from backend.app.features.documentation_ai.api import ExtractNoteInput, extract_note

        note = "Reviewed history. Tooth 14 surface O restored. Patient tolerated procedure."
        with patch.dict(os.environ, {}, clear=True), patch(
            "backend.app.features.documentation_ai.api._save_run", return_value="run-1"
        ):
            result = extract_note(ExtractNoteInput(encounter_id="00000000-0000-0000-0000-000000000001", note=note), Role.ASSISTANT)

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
        review = ReviewInput(evidence_code="DOC_TOOTH_SURFACE")
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

    def test_staff_and_review_role_boundaries_return_shared_403_errors(self):
        from backend.app.core.contracts import Role
        from backend.app.core.errors import AppError
        from backend.app.features.documentation_ai.api import _require_role

        for role in (Role.ASSISTANT, Role.DENTIST):
            _require_role(role, Role.ASSISTANT, Role.DENTIST)
        _require_role(Role.DENTIST, Role.DENTIST)
        for role in (Role.PATIENT, Role.FRONT_DESK, Role.QA):
            with self.subTest(role=role), self.assertRaises(AppError) as denied:
                _require_role(role, Role.ASSISTANT, Role.DENTIST)
            self.assertEqual(denied.exception.status_code, 403)
        with self.assertRaises(AppError) as assistant_review:
            _require_role(Role.ASSISTANT, Role.DENTIST)
        self.assertEqual(assistant_review.exception.status_code, 403)

    def test_model_facts_are_whitelisted_and_accept_writes_only_mapped_fields(self):
        from backend.app.core.contracts import Role
        from backend.app.features.documentation_ai.api import Fact, ReviewInput, accept_run

        with self.assertRaises(ValidationError):
            Fact(fact="diagnosis", source_span="Caries diagnosed")
        run = {
            "id": "00000000-0000-0000-0000-000000000010",
            "encounter_id": "00000000-0000-0000-0000-000000000001",
            "status": "UNVERIFIED",
            "output": {"facts": [{"fact": "procedure_documented", "tooth": "14", "surface": "O", "source_span": "Tooth 14 surface O restored."}]},
        }
        with patch("backend.app.features.documentation_ai.api._load_run", return_value=run), patch(
            "backend.app.features.documentation_ai.api._mark_reviewed"
        ), patch("backend.app.features.documentation_ai.api.upsert_evidence", return_value={"id": "evidence-1"}) as upsert, patch(
            "backend.app.features.documentation_ai.api.append_audit"
        ):
            accept_run(run["id"], ReviewInput(evidence_code="DOC_TOOTH_SURFACE"), Role.DENTIST)

        self.assertEqual(upsert.call_args.args[1], "DOC_TOOTH_SURFACE")
        self.assertEqual(upsert.call_args.args[3], {"tooth": "14", "surface": "O", "source_span": "Tooth 14 surface O restored."})

    def test_review_rejects_unknown_or_already_reviewed_runs(self):
        from backend.app.core.contracts import Role
        from backend.app.core.errors import AppError
        from backend.app.features.documentation_ai.api import ReviewInput, accept_run, reject_run

        for status, action in (("ACCEPTED", lambda: accept_run("run-1", ReviewInput(evidence_code="DOC_PROGRESS_NOTE"), Role.DENTIST)), ("REJECTED", lambda: reject_run("run-1", Role.DENTIST))):
            with self.subTest(status=status), patch("backend.app.features.documentation_ai.api._load_run", return_value={"status": status}), self.assertRaises(AppError) as conflict:
                action()
            self.assertEqual(conflict.exception.status_code, 409)
        with patch("backend.app.features.documentation_ai.api._load_run", return_value=None), self.assertRaises(AppError) as missing:
            reject_run("run-1", Role.DENTIST)
        self.assertEqual(missing.exception.status_code, 404)

    def test_react_route_submits_note_and_exposes_human_review_actions(self):
        source = (Path(__file__).parents[2] / "frontend/src/features/documentation-ai/index.jsx").read_text()
        self.assertIn('fetch("/api/v1/ai/extract-note"', source)
        self.assertIn('state === "UNVERIFIED"', source)
        self.assertIn("source_span", source)
        self.assertIn('`/api/v1/ai/runs/${run.ai_run_id}/${action}`', source)


if __name__ == "__main__":
    unittest.main()
