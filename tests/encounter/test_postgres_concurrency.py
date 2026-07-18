import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

from backend.app.core.contracts import Role
from backend.app.core.errors import AppError
from backend.app.features.encounter import service


TEST_DATABASE_URL = os.environ.get("ENCOUNTER_TEST_DATABASE_URL")
if TEST_DATABASE_URL and "connect_timeout=" not in TEST_DATABASE_URL:
    separator = "&" if "?" in TEST_DATABASE_URL else "?"
    TEST_DATABASE_URL = f"{TEST_DATABASE_URL}{separator}connect_timeout=5"


@unittest.skipUnless(TEST_DATABASE_URL, "Set ENCOUNTER_TEST_DATABASE_URL to run PostgreSQL integration tests")
class PostgresEncounterConcurrencyTest(unittest.TestCase):
    def setUp(self):
        import psycopg

        self.psycopg = psycopg
        self.patient_id = uuid4()
        self.encounter_id = uuid4()
        self.original_database_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = TEST_DATABASE_URL
        with psycopg.connect(TEST_DATABASE_URL) as connection:
            connection.execute(
                "INSERT INTO patients (id, mrn, full_name, date_of_birth) VALUES (%s, %s, %s, %s)",
                (self.patient_id, f"TEST-{self.patient_id.hex}", "Concurrency Test", "1990-01-01"),
            )
            connection.execute(
                "INSERT INTO encounters (id, patient_id, stage, version) VALUES (%s, %s, 'CHECK_IN', 1)",
                (self.encounter_id, self.patient_id),
            )

    def tearDown(self):
        with self.psycopg.connect(TEST_DATABASE_URL) as connection:
            connection.execute("DELETE FROM audit_events WHERE encounter_id = %s", (self.encounter_id,))
            connection.execute("DELETE FROM encounters WHERE id = %s", (self.encounter_id,))
            connection.execute("DELETE FROM patients WHERE id = %s", (self.patient_id,))
        if self.original_database_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = self.original_database_url

    def test_two_writers_with_same_version_have_exactly_one_winner(self):
        barrier = Barrier(2)

        def advance():
            barrier.wait()
            try:
                result = service.advance_stage(
                    self.encounter_id,
                    "PRE_TREATMENT",
                    1,
                    Role.DENTIST,
                )
                return "success", result
            except AppError as error:
                return "error", error.payload

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _index: advance(), range(2)))

        successes = [payload for status, payload in results if status == "success"]
        errors = [payload for status, payload in results if status == "error"]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(errors), 1)
        self.assertEqual(successes[0]["stage"], "PRE_TREATMENT")
        self.assertEqual(successes[0]["version"], 2)
        self.assertEqual(errors[0]["code"], "STALE_ENCOUNTER_VERSION")
        self.assertEqual(errors[0]["details"]["current_version"], 2)

        history = service.get_stage_transitions(self.encounter_id)
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["from_stage"], "CHECK_IN")
        self.assertEqual(history[0]["to_stage"], "PRE_TREATMENT")
        self.assertEqual(history[0]["actor_role"], "DENTIST")
