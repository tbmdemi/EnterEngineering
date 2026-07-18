import inspect
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
from uuid import UUID


ROOT = Path(__file__).parents[1]


class FoundationContractTest(unittest.TestCase):
    def test_shared_contracts_are_stable(self):
        from backend.app.core.contracts import (
            EncounterStage,
            EvidenceState,
            ObligationState,
            Role,
            TaskStatus,
        )

        self.assertEqual([x.value for x in Role], ["FRONT_DESK", "ASSISTANT", "DENTIST", "PATIENT", "QA"])
        self.assertEqual([x.value for x in EncounterStage], ["CHECK_IN", "PRE_TREATMENT", "TREATMENT", "POST_TREATMENT", "CLOSED"])
        self.assertEqual([x.value for x in EvidenceState], ["DRAFT", "VERIFIED"])
        self.assertEqual([x.value for x in ObligationState], ["PENDING", "MISSING", "UNVERIFIED", "SATISFIED", "NOT_APPLICABLE"])
        self.assertEqual([x.value for x in TaskStatus], ["OPEN", "ACKNOWLEDGED", "COMPLETED", "CANCELLED"])

    def test_core_service_signatures_are_stable(self):
        from backend.app.core.services import append_audit, ensure_task, upsert_evidence

        self.assertEqual(list(inspect.signature(upsert_evidence).parameters), ["encounter_id", "code", "state", "value", "source_type", "source_ref", "actor_role"])
        self.assertEqual(list(inspect.signature(ensure_task).parameters), ["encounter_id", "obligation_code", "task_type", "owner_role", "due_at", "idempotency_key"])
        self.assertEqual(list(inspect.signature(append_audit).parameters), ["actor_role", "action", "object_type", "object_id", "encounter_id", "metadata"])

    def test_demo_role_parser_rejects_missing_and_invalid_roles(self):
        from backend.app.core.errors import AppError
        from backend.app.core.security import parse_demo_role

        for value in (None, "", "ADMIN"):
            with self.subTest(value=value), self.assertRaises(AppError) as caught:
                parse_demo_role(value)
            self.assertEqual(caught.exception.status_code, 401 if not value else 403)
            self.assertEqual(set(caught.exception.payload), {"code", "message", "details"})
        self.assertEqual(parse_demo_role("DENTIST").value, "DENTIST")

    def test_optional_demo_access_key_is_compared_server_side(self):
        from backend.app.core.errors import AppError
        from backend.app.core.security import require_demo_access

        with patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(require_demo_access(None))
        with patch.dict("os.environ", {"DEMO_ACCESS_TOKEN": "server-secret"}, clear=True):
            self.assertIsNone(require_demo_access("server-secret"))
            for value in (None, "wrong"):
                with self.subTest(value=value), self.assertRaises(AppError) as caught:
                    require_demo_access(value)
                self.assertEqual(caught.exception.payload["code"], "DEMO_ACCESS_DENIED")

    def test_core_services_persist_and_return_dicts_idempotently(self):
        from backend.app.core import services

        rows = iter([
            {"id": "evidence-1", "code": "PRE_ALLERGY", "state": "VERIFIED"},
            {"id": "task-1", "status": "OPEN", "idempotency_key": "same-key"},
            {"id": "audit-1", "action": "VERIFIED"},
        ])

        class FakeConnection:
            def __init__(self):
                self.calls = []
            def execute(self, query, params):
                self.calls.append((query, params))
                return self
            def fetchone(self):
                return next(rows)

        connection = FakeConnection()

        @contextmanager
        def fake_connect():
            yield connection

        with patch.object(services, "_connect", fake_connect):
            evidence = services.upsert_evidence("enc", "PRE_ALLERGY", "VERIFIED", {"ok": True}, "FORM", "form-1", "ASSISTANT")
            task = services.ensure_task("enc", "PRE_ALLERGY", "REVIEW", "DENTIST", None, "same-key")
            audit = services.append_audit("DENTIST", "VERIFIED", "evidence", "evidence-1", "enc", {"safe": True})

        self.assertEqual(evidence["id"], "evidence-1")
        self.assertEqual(task["idempotency_key"], "same-key")
        self.assertEqual(audit["action"], "VERIFIED")
        self.assertIn("ON CONFLICT (encounter_id, code)", connection.calls[0][0])
        self.assertIn("ON CONFLICT (idempotency_key)", connection.calls[1][0])
        self.assertIn("INSERT INTO audit_events", connection.calls[2][0])

    def test_react_feature_route_contract_and_registry_are_documented(self):
        registry = (ROOT / "frontend/src/routes.js").read_text(encoding="utf-8")
        self.assertIn("export const featureRoutes", registry)
        convention = "export const route = { path, label, Component }"
        for spec in (ROOT / "docs/modules").glob("*.md"):
            self.assertIn(convention, spec.read_text(encoding="utf-8"), spec.name)

    def test_pre_treatment_is_registered_in_the_demo_shell(self):
        from backend.app.main import app

        paths = {route.path for route in app.routes}
        self.assertIn("/api/v1/encounters/{encounter_id}/pre-treatment", paths)
        self.assertIn("/api/v1/encounters/{encounter_id}/pre-treatment/{code}", paths)

        registry = (ROOT / "frontend/src/routes.js").read_text(encoding="utf-8")
        app_source = (ROOT / "frontend/src/main.jsx").read_text(encoding="utf-8")
        self.assertIn("preTreatmentRoute", registry)
        self.assertIn("window.location.pathname", app_source)

    def test_api_registers_validation_and_unhandled_error_boundaries(self):
        source = (ROOT / "backend/app/main.py").read_text(encoding="utf-8")
        self.assertIn("RequestValidationError", source)
        self.assertIn("@app.exception_handler(Exception)", source)
        self.assertIn('"details"', source)

    def test_database_contains_only_required_foundation_tables_and_seed(self):
        schema = (ROOT / "db/init/00_core.sql").read_text(encoding="utf-8")
        for table in ("patients", "appointments", "encounters", "evidence_items", "obligation_checks", "tasks", "ai_runs", "audit_events"):
            self.assertIn(f"CREATE TABLE {table}", schema)
        seed = (ROOT / "db/init/01_seed.sql").read_text(encoding="utf-8")
        self.assertIn("Nguyen Minh Anh", seed)
        self.assertIn("dental-policy.v1", seed)

    def test_frontend_container_uses_lockfile_and_proxies_api(self):
        dockerfile = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
        config = (ROOT / "frontend/vite.config.js").read_text(encoding="utf-8")
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

        self.assertIn("package-lock.json", dockerfile)
        self.assertIn("npm", dockerfile)
        self.assertIn("ci", dockerfile)
        self.assertIn('"/api"', config)
        self.assertIn("API_PROXY_TARGET", config)
        self.assertIn("API_PROXY_TARGET: http://api:8000", compose)

    def test_compose_runs_idempotent_migrations_before_api(self):
        compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
        migration = (ROOT / "db/migrations/001_integrated_demo.sql").read_text(encoding="utf-8")
        runner = (ROOT / "backend/migrate.py").read_text(encoding="utf-8")
        baseline = (ROOT / "db/migrations/000_baseline.sql").read_text(encoding="utf-8")

        self.assertIn("migrate:", compose)
        self.assertIn("condition: service_completed_successfully", compose)
        self.assertIn("schema_migrations", runner)
        self.assertIn("pg_advisory_lock", runner)
        self.assertIn("CREATE TABLE IF NOT EXISTS encounters", baseline)
        self.assertIn("ADD COLUMN IF NOT EXISTS released_to_patient_at", migration)
        self.assertIn("ON CONFLICT DO NOTHING", migration)

    def test_deployment_assets_define_production_runtime_and_public_health(self):
        from backend.app.main import app

        paths = {route.path for route in app.routes}
        self.assertIn("/api/health/live", paths)
        self.assertIn("/api/health/ready", paths)

        frontend_dockerfile = (ROOT / "frontend/Dockerfile").read_text(encoding="utf-8")
        nginx = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        production_compose = (ROOT / "docker-compose.prod.yml").read_text(encoding="utf-8")
        api_client = (ROOT / "frontend/src/api.js").read_text(encoding="utf-8")

        self.assertIn("FROM nginx:alpine AS production", frontend_dockerfile)
        self.assertIn("try_files $uri $uri/ /index.html", nginx)
        self.assertIn("VITE_API_BASE_URL", api_client)
        self.assertIn("X-Demo-Access-Token", api_client)
        self.assertIn("healthCheckPath: /api/health/ready", render)
        self.assertIn("preDeployCommand: python /app/migrate.py", render)
        self.assertIn("ports: !reset []", production_compose)

    def test_core_services_json_encode_uuid_values(self):
        from backend.app.core import services

        class FakeConnection:
            def execute(self, _query, params):
                self.params = params
                return self

            def fetchone(self):
                return {"id": "evidence-1"}

        @contextmanager
        def fake_connect():
            yield connection

        connection = FakeConnection()
        task_id = UUID("00000000-0000-0000-0000-000000000099")
        with patch.object(services, "_connect", fake_connect):
            services.upsert_evidence("enc", "COORD_HANDOFF_ACK", "VERIFIED", {"task_id": task_id}, "TASK", str(task_id), "ASSISTANT")

        self.assertEqual(connection.params[3], '{"task_id": "00000000-0000-0000-0000-000000000099"}')

    def test_stable_task_reopens_after_it_was_cancelled(self):
        from backend.app.core import services

        class FakeConnection:
            def execute(self, query, _params):
                self.query = query
                return self

            def fetchone(self):
                return {"id": "task-1", "status": "OPEN"}

        connection = FakeConnection()
        @contextmanager
        def fake_connect():
            yield connection

        with patch.object(services, "_connect", fake_connect):
            services.ensure_task("enc", "COORD_SCHEDULE_CLEAR", "RESOLVE_SCHEDULE_CONFLICT", "FRONT_DESK", None, "coord:enc:schedule-conflict")
        self.assertIn("status = CASE WHEN tasks.status = 'CANCELLED' THEN 'OPEN'", connection.query)


if __name__ == "__main__":
    unittest.main()
