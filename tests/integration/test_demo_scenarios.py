import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "db" / "migrations" / "002_demo_scenarios.sql"
RESET = ROOT / "db" / "demo" / "reset_scenarios.sql"
COMPOSE = ROOT / "docker-compose.yml"
POLICY = ROOT / "backend" / "app" / "features" / "compliance" / "dental-policy.v1.json"

SCENARIOS = {
    "CHECK_IN_BLANK": (
        "10000000-0000-0000-0000-000000000001",
        "20000000-0000-0000-0000-000000000001",
        "30000000-0000-0000-0000-000000000001",
        "CHECK_IN",
        1,
    ),
    "PRE_TREATMENT_INCOMPLETE": (
        "10000000-0000-0000-0000-000000000002",
        "20000000-0000-0000-0000-000000000002",
        "30000000-0000-0000-0000-000000000002",
        "PRE_TREATMENT",
        2,
    ),
    "TREATMENT_PRE_READY": (
        "10000000-0000-0000-0000-000000000003",
        "20000000-0000-0000-0000-000000000003",
        "30000000-0000-0000-0000-000000000003",
        "TREATMENT",
        3,
    ),
    "POST_TREATMENT_BLOCKED": (
        "10000000-0000-0000-0000-000000000004",
        "20000000-0000-0000-0000-000000000004",
        "30000000-0000-0000-0000-000000000004",
        "POST_TREATMENT",
        4,
    ),
    "POST_TREATMENT_READY": (
        "10000000-0000-0000-0000-000000000005",
        "20000000-0000-0000-0000-000000000005",
        "30000000-0000-0000-0000-000000000005",
        "POST_TREATMENT",
        4,
    ),
}


class DemoScenarioMigrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = MIGRATION.read_text(encoding="utf-8")

    def test_migration_is_atomic_and_every_insert_is_idempotent(self):
        self.assertTrue(self.sql.strip().startswith("BEGIN;"))
        self.assertTrue(self.sql.strip().endswith("COMMIT;"))

        inserts = re.findall(r"INSERT\s+INTO\b.*?;", self.sql, re.IGNORECASE | re.DOTALL)
        self.assertGreaterEqual(len(inserts), 6)
        for statement in inserts:
            with self.subTest(table=statement.split()[2]):
                self.assertRegex(statement, r"(?i)ON\s+CONFLICT")

        self.assertIn(
            "md5(scenario_evidence.encounter_id::text || ':' || scenario_evidence.code)::uuid",
            self.sql,
        )

    def test_every_scenario_has_a_patient_appointment_and_encounter(self):
        for name, (patient_id, appointment_id, encounter_id, stage, version) in SCENARIOS.items():
            with self.subTest(scenario=name):
                self.assertIn(
                    f"('{patient_id}', 'DEMO-SCENARIO-{patient_id[-2:]}'",
                    self.sql,
                )
                self.assertIn(f"('{appointment_id}', '{patient_id}'", self.sql)
                self.assertRegex(
                    self.sql,
                    re.escape(
                        f"('{encounter_id}', '{patient_id}', '{appointment_id}', "
                        f"'{stage}', {version}, '2026-07-18 08:00+07')"
                    ),
                )
                self.assertIn(f"'{encounter_id}'::uuid, '{name}'", self.sql)

    def test_patients_are_clearly_synthetic(self):
        patient_insert = re.search(
            r"INSERT INTO patients.*?ON CONFLICT DO NOTHING;",
            self.sql,
            re.DOTALL,
        ).group(0)
        names = re.findall(r"'(Synthetic Patient \d{2})'", patient_insert)
        mrns = re.findall(r"'(DEMO-SCENARIO-\d{2})'", patient_insert)
        self.assertEqual(names, [f"Synthetic Patient {number:02d}" for number in range(1, 6)])
        self.assertEqual(mrns, [f"DEMO-SCENARIO-{number:02d}" for number in range(1, 6)])

    def test_ready_template_covers_every_applicable_policy_obligation(self):
        template = re.search(
            r"full_ready_templates \(code, value\) AS \(\s*VALUES(.*?)\n\),\nlate_scenarios",
            self.sql,
            re.DOTALL,
        ).group(1)
        template_codes = set(re.findall(r"\(\s*'([A-Z][A-Z0-9_]+)'", template))

        policy = json.loads(POLICY.read_text(encoding="utf-8"))
        condition_evidence = {
            "medication_prescribed": "DOC_MEDICATION_PRESCRIBED",
            "imaging_required": "PRE_PROCEDURE",
        }
        expected_codes = {item["code"] for item in policy if "when" not in item}
        expected_codes.update(condition_evidence[item["when"]] for item in policy if "when" in item)
        self.assertEqual(template_codes, expected_codes)
        self.assertIn("'DOC_MEDICATION_PRESCRIBED', '{\"prescribed\":false}'::jsonb", template)
        self.assertIn("'PRE_PROCEDURE', '{\"name\":\"synthetic routine cleaning\",\"requires_imaging\":false}'::jsonb", template)
        self.assertIn('\"reviewed_source_refs\":[\"DOC-DEMO-001\"]', template)
        self.assertIn('\"confirmed\":true,\"cycle_or_tray_id\":\"DEMO-CYCLE-READY\"', template)

    def test_ready_and_blocked_templates_match_evaluator_semantics(self):
        from backend.app.features.compliance.evaluator import derive_context, evaluate

        template = re.search(
            r"full_ready_templates \(code, value\) AS \(\s*VALUES(.*?)\n\),\nlate_scenarios",
            self.sql,
            re.DOTALL,
        ).group(1)
        evidence = {
            code: {"state": "VERIFIED", "value": json.loads(value)}
            for code, value in re.findall(
                r"\(\s*'([A-Z][A-Z0-9_]+)',\s*'(\{.*?\})'::jsonb\)",
                template,
            )
        }

        ready_checks = evaluate(evidence, derive_context(evidence))
        self.assertTrue(ready_checks)
        self.assertTrue(
            all(check["state"] in {"SATISFIED", "NOT_APPLICABLE"} for check in ready_checks),
            ready_checks,
        )

        blocked_evidence = dict(evidence)
        blocked_evidence.pop("POST_RECALL")
        blocked_checks = evaluate(blocked_evidence, derive_context(blocked_evidence))
        self.assertEqual(
            {check["code"] for check in blocked_checks if check["state"] not in {"SATISFIED", "NOT_APPLICABLE"}},
            {"POST_RECALL"},
        )

    def test_scenario_boundaries_are_intentional(self):
        evidence_cte = re.search(
            r"scenario_evidence .*? AS \((.*?)\n\)\nINSERT INTO evidence_items",
            self.sql,
            re.DOTALL,
        ).group(1)
        blank_id = SCENARIOS["CHECK_IN_BLANK"][2]
        incomplete_id = SCENARIOS["PRE_TREATMENT_INCOMPLETE"][2]
        pre_ready_id = SCENARIOS["TREATMENT_PRE_READY"][2]
        blocked_id = SCENARIOS["POST_TREATMENT_BLOCKED"][2]
        ready_id = SCENARIOS["POST_TREATMENT_READY"][2]

        self.assertNotIn(blank_id, evidence_cte)
        self.assertIn(f"'{incomplete_id}'::uuid, 'PRE_ALLERGY', 'DRAFT'", evidence_cte)
        self.assertNotIn(f"'{incomplete_id}'::uuid, 'PRE_VITALS'", evidence_cte)
        self.assertIn(f"'{pre_ready_id}'::uuid, 'DOC_CONSENT_SIGNED', 'VERIFIED'", evidence_cte)
        self.assertIn(f"'{pre_ready_id}'::uuid, 'DOC_TREATMENT_PLAN_SIGNED', 'VERIFIED'", evidence_cte)
        self.assertIn(
            f"'{pre_ready_id}'::uuid, 'PRE_STERILIZATION', 'VERIFIED', '{{\"confirmed\":true",
            evidence_cte,
        )
        self.assertIn(
            "WHERE late.include_recall OR template.code <> 'POST_RECALL'",
            evidence_cte,
        )
        self.assertIn(f"'{blocked_id}'::uuid, false", self.sql)
        self.assertIn(f"'{ready_id}'::uuid, true", self.sql)

    def test_seeded_task_keys_are_unique_and_match_service_contracts(self):
        task_insert = re.search(
            r"INSERT INTO tasks.*?ON CONFLICT \(idempotency_key\) DO NOTHING;",
            self.sql,
            re.DOTALL,
        ).group(0)
        expected_keys = {
            "30000000-0000-0000-0000-000000000004:POST_RECALL:dental-policy.v1",
            "post-complication:30000000-0000-0000-0000-000000000005",
            "coord:30000000-0000-0000-0000-000000000004:handoff:coord_handoff_ack",
            "coord:30000000-0000-0000-0000-000000000005:handoff:coord_handoff_ack",
        }
        keys = {
            value
            for value in re.findall(r"'([^']+)'", task_insert)
            if value.endswith("dental-policy.v1")
            or value.startswith("post-complication:")
            or value.startswith("coord:")
        }
        self.assertEqual(keys, expected_keys)
        self.assertEqual(task_insert.count("dental-policy.v1"), 1)
        self.assertEqual(task_insert.count("post-complication:"), 1)
        self.assertEqual(task_insert.count(":handoff:coord_handoff_ack"), 2)

    def test_scenarios_have_an_explicit_scoped_reset_tool(self):
        reset = RESET.read_text(encoding="utf-8")
        compose = COMPOSE.read_text(encoding="utf-8")

        self.assertTrue(reset.strip().startswith("BEGIN;"))
        self.assertTrue(reset.strip().endswith("COMMIT;"))
        for _name, (patient_id, appointment_id, encounter_id, _stage, _version) in SCENARIOS.items():
            self.assertIn(patient_id, reset)
            self.assertIn(appointment_id, reset)
            self.assertIn(encounter_id, reset)
        self.assertIn('profiles: ["tools"]', compose)
        self.assertIn("/demo/reset_scenarios.sql", compose)
        self.assertIn("/migrations/002_demo_scenarios.sql", compose)


if __name__ == "__main__":
    unittest.main()
