import unittest
from contextlib import contextmanager
from unittest.mock import patch

from backend.app.core.contracts import Role
from backend.app.core.errors import AppError


class FakeConnection:
    def __init__(self, rows=()):
        self.rows = iter(rows)
        self.calls = []

    def execute(self, query, params=()):
        self.calls.append((query, params))
        return self

    def fetchall(self):
        return list(self.rows)


def connection_for(*rows):
    connection = FakeConnection(rows)

    @contextmanager
    def connect():
        yield connection

    return connection, connect


class PostTreatmentChatTest(unittest.TestCase):
    def test_release_is_staff_only_and_creates_idempotent_follow_up(self):
        from backend.app.features.post_treatment_chat import service

        payload = service.ReleaseRequest(
            care_instructions="Chườm lạnh bên ngoài má.",
            recall_at="2026-07-24T02:00:00Z",
            monitor_until="2026-07-20T02:00:00Z",
        )
        with self.assertRaises(AppError) as caught:
            service.release_encounter(service.DEMO_ENCOUNTER_ID, payload, Role.PATIENT)
        self.assertEqual(caught.exception.status_code, 403)

        evidence = {"id": "e1"}
        with patch.object(service, "upsert_evidence", return_value=evidence) as upsert, \
             patch.object(service, "ensure_task", return_value={"id": "t1", "status": "OPEN"}) as ensure, \
             patch.object(service, "append_audit") as audit:
            connection, connect = connection_for()
            with patch.object(service, "_connect", connect):
                result = service.release_encounter(service.DEMO_ENCOUNTER_ID, payload, Role.DENTIST)

        self.assertEqual(upsert.call_count, 3)
        self.assertEqual(ensure.call_args.args[-1], f"post-complication:{service.DEMO_ENCOUNTER_ID}")
        self.assertEqual(result["task"]["id"], "t1")
        self.assertNotIn("care_instructions", audit.call_args.args[-1])
        self.assertIn("released_to_patient_at", connection.calls[0][0])

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


if __name__ == "__main__":
    unittest.main()
