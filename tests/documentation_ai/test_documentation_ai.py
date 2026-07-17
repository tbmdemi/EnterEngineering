import os
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError


class DocumentationAiTest(unittest.TestCase):
    def test_medication_detail_is_conditional(self):
        from backend.app.features.documentation_ai.api import DocumentationInput

        common = dict(encounter_id="00000000-0000-0000-0000-000000000001", consent_signed=True,
                      treatment_plan_signed=True, progress_note="Completed.", tooth="14", surface="O")
        DocumentationInput(**common, medication_prescribed=False)
        with self.assertRaises(ValidationError):
            DocumentationInput(**common, medication_prescribed=True)
        self.assertEqual(DocumentationInput(**common, medication_prescribed=True, medication_detail="Lidocaine").medication_detail, "Lidocaine")

    def test_documentation_form_persists_expected_evidence(self):
        from backend.app.core.contracts import Role
        from backend.app.features.documentation_ai.api import DocumentationInput, save_documentation

        data = DocumentationInput(encounter_id="00000000-0000-0000-0000-000000000001", consent_signed=True,
                                  treatment_plan_signed=True, progress_note="Completed.", tooth="14", surface="O",
                                  medication_prescribed=True, medication_detail="Lidocaine")
        with patch("backend.app.features.documentation_ai.api.upsert_evidence") as upsert:
            result = save_documentation(data, Role.DENTIST)
        self.assertEqual(upsert.call_count, 6)
        self.assertIn("DOC_MEDICATION_DETAILS", result["evidence_codes"])
        self.assertIn("DOC_MEDICATION_PRESCRIBED", result["evidence_codes"])

    def test_fixture_has_exact_source_span(self):
        from backend.app.core.contracts import Role
        from backend.app.features.documentation_ai.api import ExtractNoteInput, extract_note

        note = "Reviewed history. Tooth 14 surface O restored. Patient tolerated procedure."
        with patch.dict(os.environ, {}, clear=True), patch("backend.app.features.documentation_ai.api._save_run", return_value="run-1"):
            result = extract_note(ExtractNoteInput(encounter_id="00000000-0000-0000-0000-000000000001", note=note), Role.ASSISTANT)
        self.assertEqual(result.state, "UNVERIFIED")
        self.assertEqual(result.facts[0].source_span, "Tooth 14 surface O restored.")
        self.assertIn(result.facts[0].source_span, note)

    def test_role_boundaries_use_shared_403_error(self):
        from backend.app.core.contracts import Role
        from backend.app.core.errors import AppError
        from backend.app.features.documentation_ai.api import _require_role

        for role in (Role.ASSISTANT, Role.DENTIST):
            _require_role(role, Role.ASSISTANT, Role.DENTIST)
        for role in (Role.PATIENT, Role.FRONT_DESK, Role.QA):
            with self.subTest(role=role), self.assertRaises(AppError) as denied:
                _require_role(role, Role.ASSISTANT, Role.DENTIST)
            self.assertEqual(denied.exception.status_code, 403)

    def test_model_fact_types_are_whitelisted(self):
        from backend.app.features.documentation_ai.api import Fact

        with self.assertRaises(ValidationError):
            Fact(fact="diagnosis", source_span="Caries diagnosed")

    def test_accept_uses_one_transaction_for_conditional_update_evidence_and_audit(self):
        from backend.app.core.contracts import Role
        from backend.app.features.documentation_ai.api import ReviewInput, accept_run

        reviewed_run = {"encounter_id": "00000000-0000-0000-0000-000000000001",
                        "output": {"facts": [{"fact": "procedure_documented", "tooth": "14", "surface": "O", "source_span": "Tooth 14 surface O restored."}]}}
        class Connection:
            def __init__(self):
                self.calls, self.rows = [], iter([reviewed_run, {"id": "evidence-1"}, {"id": "audit-1"}])
            def execute(self, query, params):
                self.calls.append((query, params)); return self
            def fetchone(self): return next(self.rows)
        connection, connects = Connection(), 0
        @contextmanager
        def connect():
            nonlocal connects
            connects += 1
            yield connection
        with patch("backend.app.features.documentation_ai.api._connect", connect):
            result = accept_run("00000000-0000-0000-0000-000000000010", ReviewInput(evidence_code="DOC_TOOTH_SURFACE"), Role.DENTIST)
        self.assertEqual(result["state"], "VERIFIED")
        self.assertEqual(connects, 1)
        self.assertIn("status = 'UNVERIFIED'", connection.calls[0][0])
        self.assertIn("INSERT INTO evidence_items", connection.calls[1][0])
        self.assertIn("INSERT INTO audit_events", connection.calls[2][0])
        self.assertEqual(connection.calls[1][1][2], '{"source_span": "Tooth 14 surface O restored.", "tooth": "14", "surface": "O"}')

    def test_conditional_review_distinguishes_missing_from_already_reviewed(self):
        from backend.app.core.contracts import Role
        from backend.app.core.errors import AppError
        from backend.app.features.documentation_ai.api import ReviewInput, accept_run, reject_run

        class Connection:
            def __init__(self, existing):
                self.calls, self.rows = [], iter([None, {"status": "ACCEPTED"} if existing else None])
            def execute(self, query, params): self.calls.append((query, params)); return self
            def fetchone(self): return next(self.rows)
        for existing, action, status, code in (
            (False, lambda: reject_run("00000000-0000-0000-0000-000000000010", Role.DENTIST), 404, "AI_RUN_NOT_FOUND"),
            (True, lambda: accept_run("00000000-0000-0000-0000-000000000010", ReviewInput(evidence_code="DOC_PROGRESS_NOTE"), Role.DENTIST), 409, "AI_RUN_ALREADY_REVIEWED"),
        ):
            connection = Connection(existing)
            @contextmanager
            def connect(): yield connection
            with self.subTest(existing=existing), patch("backend.app.features.documentation_ai.api._connect", connect), self.assertRaises(AppError) as error:
                action()
            self.assertEqual(error.exception.status_code, status)
            self.assertEqual(error.exception.payload["code"], code)
            self.assertEqual(len(connection.calls), 2)
            self.assertIn("SELECT status FROM ai_runs", connection.calls[1][0])

    def test_mid_review_failure_exits_the_same_transaction_with_exception(self):
        from backend.app.core.contracts import Role
        from backend.app.features.documentation_ai.api import ReviewInput, accept_run

        class Connection:
            calls = 0
            def execute(self, _query, _params):
                self.calls += 1
                if self.calls == 3: raise RuntimeError("audit unavailable")
                return self
            def fetchone(self):
                if self.calls == 1:
                    return {"encounter_id": "00000000-0000-0000-0000-000000000001", "output": {"facts": [{"fact": "note_documented", "source_span": "Procedure documented."}]}}
                return {"id": "evidence-1"}
        exited_with = None
        @contextmanager
        def connect():
            nonlocal exited_with
            try: yield Connection()
            except Exception as error:
                exited_with = type(error)
                raise
        with patch("backend.app.features.documentation_ai.api._connect", connect), self.assertRaises(RuntimeError):
            accept_run("00000000-0000-0000-0000-000000000010", ReviewInput(evidence_code="DOC_PROGRESS_NOTE"), Role.DENTIST)
        self.assertIs(exited_with, RuntimeError)

    def test_react_has_documentation_and_ai_review_flows(self):
        source = (Path(__file__).parents[2] / "frontend/src/features/documentation-ai/index.jsx").read_text()
        for text in ('fetch("/api/v1/documentation"', 'fetch("/api/v1/ai/extract-note"', "consent_signed",
                     "treatment_plan_signed", "medication_prescribed", "source_span", 'state === "UNVERIFIED"'):
            self.assertIn(text, source)


if __name__ == "__main__":
    unittest.main()
