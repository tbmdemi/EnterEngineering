import json
import re
import unittest
from pathlib import Path

from backend.app.core.contracts import Role
from backend.app.core.errors import AppError


ROOT = Path(__file__).parents[2]
FEATURE_DIR = ROOT / "backend/app/features/post_treatment_chat"
ROUTER_SOURCE = FEATURE_DIR / "router.py"
SERVICE_SOURCE = FEATURE_DIR / "service.py"
FRONTEND_SOURCE = ROOT / "frontend/src/features/post-treatment-chat/index.jsx"
FRONTEND_STYLES = ROOT / "frontend/src/features/post-treatment-chat/index.css"
SCHEMA = ROOT / "db/init/50_post_treatment_chat.sql"

PROCEDURES = {"EXTRACTION", "ROOT_CANAL", "IMPLANT", "FILLING", "CLEANING"}
JOURNEY_TABLES = {
    "post_treatment_release_versions",
    "post_treatment_release_heads",
    "post_treatment_acknowledgements",
    "post_treatment_checkpoints",
    "post_treatment_checkin_responses",
    "post_treatment_callback_requests",
    "post_treatment_feedback",
}
PERSISTENCE_ENDPOINT_PARTS = {
    "/post-treatment/journey",
    "/post-treatment/acknowledgements",
    "/post-treatment/check-ins",
    "/post-treatment/callback-requests",
    "/post-treatment/amendments",
    "/post-treatment/feedback",
}


def router_contracts(router):
    return {
        (method, route.path)
        for route in router.routes
        for method in route.methods
        if method not in {"HEAD", "OPTIONS"}
    }


class PostTreatmentDatabaseFreeJourneyTest(unittest.TestCase):
    maxDiff = None

    def test_approved_templates_cover_five_procedures_in_two_reviewed_locales(self):
        fixtures = list(FEATURE_DIR.glob("*template*.json"))
        self.assertEqual(
            [fixture.name for fixture in fixtures],
            ["approved_aftercare_templates.v1.json"],
        )

        catalog = json.loads(fixtures[0].read_text(encoding="utf-8"))
        self.assertEqual(catalog["catalog_version"], "aftercare-templates.v1")
        self.assertEqual(catalog["version"], catalog["catalog_version"])
        self.assertTrue(catalog["approved_by"])
        self.assertTrue(catalog["approved_at"])
        self.assertEqual(len(catalog["templates"]), len(PROCEDURES) * 2)

        refs = set()
        locales_by_procedure = {}
        for template in catalog["templates"]:
            with self.subTest(template=template.get("template_ref")):
                for field in (
                    "template_ref",
                    "procedure_code",
                    "locale",
                    "version",
                    "title",
                    "care_instructions",
                    "approved_by",
                    "approved_at",
                    "source",
                ):
                    self.assertTrue(template.get(field), f"missing {field}")
                self.assertEqual(template.get("approval_status"), "APPROVED")
                self.assertIs(template.get("active"), True)
                self.assertTrue(template.get("source_url", "").startswith("https://"))
                self.assertNotIn(template["template_ref"], refs)
                refs.add(template["template_ref"])
                locales_by_procedure.setdefault(
                    template["procedure_code"], set()
                ).add(template["locale"])

        self.assertEqual(set(locales_by_procedure), PROCEDURES)
        for procedure_code, locales in locales_by_procedure.items():
            with self.subTest(procedure_code=procedure_code):
                self.assertEqual(locales, {"vi", "en"})

    def test_static_template_endpoint_is_dentist_only_and_filters_catalog(self):
        from backend.app.features.post_treatment_chat import service

        with self.assertRaises(AppError) as caught:
            service.list_templates(
                Role.PATIENT, locale="vi", procedure_code="EXTRACTION"
            )
        self.assertEqual(caught.exception.status_code, 403)

        catalog = service.list_templates(
            Role.DENTIST, locale="vi", procedure_code="EXTRACTION"
        )
        self.assertEqual(catalog.catalog_version, "aftercare-templates.v1")
        self.assertEqual(len(catalog.templates), 1)
        self.assertEqual(catalog.templates[0].procedure_code, "EXTRACTION")
        self.assertEqual(catalog.templates[0].locale, "vi")
        self.assertTrue(catalog.templates[0].approved_by)
        self.assertTrue(catalog.templates[0].source)
        self.assertRegex(catalog.templates[0].content_hash, r"^[0-9a-f]{64}$")

        from backend.app.features.post_treatment_chat.router import router

        contracts = router_contracts(router)
        self.assertEqual(
            contracts,
            {
                ("GET", "/api/v1/post-treatment/templates"),
                ("POST", "/api/v1/encounters/{encounter_id}/release"),
                ("POST", "/api/v1/portal/chat"),
            },
        )

    def test_schema_adds_no_journey_persistence_and_keeps_release_immutable(self):
        schema = SCHEMA.read_text(encoding="utf-8")

        for table in JOURNEY_TABLES:
            with self.subTest(table=table):
                self.assertNotIn(table, schema)

        self.assertIn("released_to_patient_at IS NULL OR state = 'VERIFIED'", schema)
        self.assertIn("prevent_released_evidence_item_mutation", schema)
        self.assertIn("BEFORE UPDATE", schema)
        self.assertIn("TG_OP = 'DELETE'", schema)
        self.assertIn("BEFORE DELETE", schema)
        for field in (
            "state",
            "value",
            "source_type",
            "source_ref",
            "actor_role",
            "released_to_patient_at",
        ):
            self.assertIn(f"NEW.{field} IS DISTINCT FROM OLD.{field}", schema)

    def test_frontend_journey_features_are_explicitly_session_only(self):
        source = FRONTEND_SOURCE.read_text(encoding="utf-8")
        styles = FRONTEND_STYLES.read_text(encoding="utf-8")

        for marker in (
            "ReleaseStepper",
            "release-stepper",
            "TemplateSelector",
            "template-locale",
            "procedure-code",
            "approved-template",
            "JourneyTimeline",
            "journey-timeline",
            "createSessionCheckIns",
            "SESSION_RED_FLAG_GUIDANCE",
            "session-only-note",
            "acknowledgement-title",
            "check-in-form",
            "check-in-trend",
            "feedback-form",
            "problem-resolved",
            "window.print",
            "chat-transcript",
            "setTranscript([])",
        ):
            with self.subTest(marker=marker):
                self.assertIn(marker, source)

        self.assertIn("const [transcript, setTranscript] = useState([])", source)
        self.assertIn("@media print", styles)
        self.assertIn(".release-stepper", styles)
        self.assertIn(".journey-timeline", styles)
        self.assertIn(".chat-transcript", styles)
        self.assertIn(
            '["INCREASING", "SPREADING_RAPIDLY"].includes(checkInForm.swelling)',
            source,
        )
        self.assertIn("selectedTemplate.sourceUrl", source)
        self.assertIn("Không có yêu cầu thật nào được gửi", source)
        self.assertNotIn("localStorage", source)
        self.assertNotIn("sessionStorage", source)

        session_handlers = (
            ("const acknowledgeRelease =", "const submitCheckIn ="),
            ("const submitCheckIn =", "const submitCallback ="),
            ("const submitCallback =", "const submitFeedback ="),
            ("const submitFeedback =", "const dangerousCheckIn ="),
        )
        for start, end in session_handlers:
            with self.subTest(handler=start):
                block = source[source.index(start) : source.index(end)]
                self.assertNotIn("apiRequest(", block)
                self.assertNotIn("await request(", block)
                self.assertNotIn("fetch(", block)

        for endpoint in PERSISTENCE_ENDPOINT_PARTS:
            with self.subTest(endpoint=endpoint):
                self.assertNotIn(endpoint, source)

        api_paths = set(re.findall(r"/api/v1/[A-Za-z0-9_/${}?=&.-]+", source))
        self.assertEqual(
            api_paths,
            {
                "/api/v1/post-treatment/templates?${query}",
                "/api/v1/encounters/${DEMO_ENCOUNTER_ID}/release",
                "/api/v1/portal/chat",
            },
        )

    def test_legacy_release_and_chat_contracts_remain_compatible(self):
        from backend.app.features.post_treatment_chat import service
        from backend.app.features.post_treatment_chat.router import router

        self.assertEqual(
            set(service.ReleaseRequest.model_fields),
            {"care_instructions", "recall_at", "monitor_until"},
        )
        self.assertFalse(
            {"release_ref", "version_no", "supersedes_release_ref"}
            & set(service.ReleaseResponse.model_fields)
        )
        self.assertEqual(set(service.ChatRequest.model_fields), {"message"})
        self.assertEqual(
            set(service.EVIDENCE_CODES),
            {
                "POST_CARE_INSTRUCTIONS",
                "POST_RECALL",
                "POST_COMPLICATION_MONITORING",
            },
        )

        contracts = router_contracts(router)
        self.assertIn(
            ("POST", "/api/v1/encounters/{encounter_id}/release"), contracts
        )
        self.assertIn(("POST", "/api/v1/portal/chat"), contracts)

        backend_source = "\n".join(
            source_file.read_text(encoding="utf-8")
            for source_file in FEATURE_DIR.glob("*.py")
        )
        router_source = ROUTER_SOURCE.read_text(encoding="utf-8")
        for table in JOURNEY_TABLES:
            self.assertNotIn(table, backend_source)
        self.assertIn("response_model_exclude_none=True", router_source)


if __name__ == "__main__":
    unittest.main()
