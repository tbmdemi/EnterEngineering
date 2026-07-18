import json
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from backend.app.core.contracts import Role
from backend.app.core.errors import AppError


class FakeConnection:
    def __init__(self, rows=(), one_rows=()):
        self.rows = iter(rows)
        self.one_rows = iter(one_rows)
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return self

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return next(self.one_rows)


def connection_for(*rows, one_rows=()):
    connection = FakeConnection(rows, one_rows)

    @contextmanager
    def connect():
        yield connection

    return connection, connect


class PostTreatmentChatTest(unittest.TestCase):
    def test_release_is_staff_only_stage_gated_and_atomic(self):
        from backend.app.features.post_treatment_chat import service

        payload = service.ReleaseRequest(
            care_instructions="Chườm lạnh bên ngoài má.",
            recall_at="2026-07-24T02:00:00Z",
            monitor_until="2026-07-20T02:00:00Z",
        )
        with self.assertRaises(AppError) as caught:
            service.release_encounter(service.DEMO_ENCOUNTER_ID, payload, Role.PATIENT)
        self.assertEqual(caught.exception.status_code, 403)

        connection, connect = connection_for(one_rows=[
            {"stage": "POST_TREATMENT"},
            {"id": "e1", "code": "POST_CARE_INSTRUCTIONS"},
            {"id": "e2", "code": "POST_RECALL"},
            {"id": "e3", "code": "POST_COMPLICATION_MONITORING"},
            {"id": "t1", "status": "OPEN"},
        ])
        connect_calls = 0

        @contextmanager
        def counted_connect():
            nonlocal connect_calls
            connect_calls += 1
            yield connection

        with patch.object(service, "_connect", counted_connect):
            result = service.release_encounter(service.DEMO_ENCOUNTER_ID, payload, Role.DENTIST)

        self.assertEqual(connect_calls, 1)
        self.assertEqual(result["task"]["id"], "t1")
        sql = "\n".join(call[0] for call in connection.calls)
        self.assertIn("FOR UPDATE", sql)
        self.assertEqual(sql.count("INSERT INTO evidence_items"), 3)
        self.assertIn("ON CONFLICT (idempotency_key)", sql)
        self.assertIn("released_to_patient_at", sql)
        self.assertIn("INSERT INTO audit_events", sql)
        self.assertNotIn(payload.care_instructions, str(connection.calls[-1]))

    def test_release_rejects_wrong_stage_before_writes(self):
        from backend.app.features.post_treatment_chat import service

        payload = service.ReleaseRequest(care_instructions="Care", recall_at="2026-07-24T02:00:00Z", monitor_until="2026-07-20T02:00:00Z")
        connection, connect = connection_for(one_rows=[{"stage": "TREATMENT"}])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.release_encounter(service.DEMO_ENCOUNTER_ID, payload, Role.DENTIST)
        self.assertEqual(caught.exception.payload["code"], "ENCOUNTER_NOT_RELEASABLE")
        self.assertEqual(len(connection.calls), 1)

    def test_my_record_only_reads_released_verified_evidence_and_has_citations(self):
        from backend.app.features.post_treatment_chat import service

        rows = [{"code": "POST_CARE_INSTRUCTIONS", "value": {"text": "Chườm lạnh bên ngoài má."}}]
        connection, connect = connection_for(*rows)
        with patch.object(service, "_connect", connect), patch.object(service, "append_audit") as audit:
            answer = service.chat(service.ChatRequest(message="Hướng dẫn của tôi là gì?"), Role.PATIENT)

        self.assertEqual(answer.intent, "MY_RECORD")
        self.assertTrue(answer.citations)
        query, params = connection.calls[0]
        self.assertIn("state = 'VERIFIED'", query)
        self.assertIn("released_to_patient_at IS NOT NULL", query)
        self.assertEqual(params, (service.DEMO_ENCOUNTER_ID,))
        self.assertNotIn("message", audit.call_args.args[-1])
        self.assertNotIn("Hướng dẫn", str(audit.call_args))

    def test_unreleased_record_is_denied_without_leaking_content(self):
        from backend.app.features.post_treatment_chat import service

        connection, connect = connection_for()
        with patch.object(service, "_connect", connect), patch.object(service, "append_audit"):
            answer = service.chat(service.ChatRequest(message="Hồ sơ của tôi"), Role.PATIENT)
        self.assertEqual(answer.intent, "MY_RECORD")
        self.assertEqual(answer.citations, [])
        self.assertIn("chưa được phát hành", answer.answer)

    def test_faq_and_symptom_cards_require_citations(self):
        from backend.app.features.post_treatment_chat import service

        with patch.object(service, "append_audit"):
            faq = service.chat(service.ChatRequest(message="Giờ mở cửa phòng khám?"), Role.PATIENT)
            symptom = service.chat(service.ChatRequest(message="Đau nhẹ sau nhổ răng có bình thường không?"), Role.PATIENT)
        self.assertEqual(faq.intent, "CLINIC_FAQ")
        self.assertTrue(faq.citations)
        self.assertEqual(symptom.intent, "SYMPTOM_INFO")
        self.assertTrue(symptom.citations)
        self.assertNotIn("chẩn đoán", symptom.answer.lower())

    def test_red_flag_is_fixed_escalation_and_unknown_abstains(self):
        from backend.app.features.post_treatment_chat import service

        with patch.object(service, "append_audit"):
            red = service.chat(service.ChatRequest(message="Tôi khó thở và sưng lan nhanh"), Role.PATIENT)
            unknown = service.chat(service.ChatRequest(message="Giá bitcoin hôm nay?"), Role.PATIENT)
        self.assertTrue(red.escalation)
        self.assertEqual(red.answer, service.RED_FLAG_ANSWER)
        self.assertIn("không có thông tin đã duyệt", unknown.answer)
        self.assertEqual(unknown.citations, [])

    def test_chat_is_patient_only(self):
        from backend.app.features.post_treatment_chat import service

        with self.assertRaises(AppError) as caught:
            service.chat(service.ChatRequest(message="Giờ mở cửa?"), Role.DENTIST)
        self.assertEqual(caught.exception.status_code, 403)

    def test_approved_cards_fixture_has_versioned_provenance(self):
        from backend.app.features.post_treatment_chat import service

        fixture = Path(service.__file__).with_name("approved_cards.v1.json")
        cards = json.loads(fixture.read_text(encoding="utf-8"))
        self.assertEqual(cards["version"], "dental-cards.v1")
        self.assertTrue(cards["approved_by"])
        for card in cards["cards"]:
            self.assertTrue(card["id"])
            self.assertTrue(card["source"])
        self.assertEqual(service.APPROVED_CARDS["version"], cards["version"])


if __name__ == "__main__":
    unittest.main()
