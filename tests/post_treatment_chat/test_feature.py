import json
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from backend.app.core.contracts import Role
from backend.app.core.errors import AppError


ROOT = Path(__file__).parents[2]


def future_release_datetimes():
    now = datetime.now(timezone.utc)
    return now + timedelta(days=30), now + timedelta(days=7)


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

        recall_at, monitor_until = future_release_datetimes()
        payload = service.ReleaseRequest(
            care_instructions="Chườm lạnh bên ngoài má.",
            recall_at=recall_at,
            monitor_until=monitor_until,
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
        self.assertIn("due_at = EXCLUDED.due_at", sql)
        self.assertIn("released_to_patient_at", sql)
        self.assertIn("INSERT INTO audit_events", sql)
        self.assertNotIn(payload.care_instructions, str(connection.calls[-1]))
        self.assertEqual(result["summary"]["care_instructions"], payload.care_instructions)
        self.assertEqual(result["follow_up_task"]["id"], "t1")

    def test_release_rejects_wrong_stage_before_writes(self):
        from backend.app.features.post_treatment_chat import service

        recall_at, monitor_until = future_release_datetimes()
        payload = service.ReleaseRequest(care_instructions="Care", recall_at=recall_at, monitor_until=monitor_until)
        connection, connect = connection_for(one_rows=[{"stage": "TREATMENT"}])
        with patch.object(service, "_connect", connect), self.assertRaises(AppError) as caught:
            service.release_encounter(service.DEMO_ENCOUNTER_ID, payload, Role.DENTIST)
        self.assertEqual(caught.exception.payload["code"], "ENCOUNTER_NOT_RELEASABLE")
        self.assertEqual(len(connection.calls), 1)

    def test_my_record_only_reads_released_verified_evidence_and_has_citations(self):
        from backend.app.features.post_treatment_chat import service

        rows = [
            {"id": "released-1", "code": "POST_CARE_INSTRUCTIONS", "value": {"text": "Chườm lạnh bên ngoài má."}},
            {"id": "released-2", "code": "POST_RECALL", "value": {"recall_at": "2030-08-24T02:00:00Z"}},
            {"id": "released-3", "code": "POST_COMPLICATION_MONITORING", "value": {"monitor_until": "2030-08-20T02:00:00Z"}},
        ]
        connection, connect = connection_for(*rows)
        with patch.object(service, "_connect", connect), patch.object(service, "append_audit") as audit:
            answer = service.chat(service.ChatRequest(message="Hướng dẫn của tôi là gì?"), Role.PATIENT)

        self.assertEqual(answer.intent, "MY_RECORD")
        self.assertTrue(answer.citations)
        query, params = connection.calls[0]
        self.assertIn("state = 'VERIFIED'", query)
        self.assertIn("released_to_patient_at IS NOT NULL", query)
        self.assertIn("code = ANY", query)
        self.assertEqual(params, (service.DEMO_ENCOUNTER_ID, list(service.EVIDENCE_CODES)))
        self.assertEqual(len(connection.calls), 1)
        self.assertNotIn("post_treatment_", query)
        self.assertIn("Hướng dẫn chăm sóc:", answer.answer)
        self.assertIn("2030-08-24T02:00:00Z", answer.answer)
        self.assertEqual(answer.citations, [
            "RELEASED_RECORD#released-1",
            "RELEASED_RECORD#released-2",
            "RELEASED_RECORD#released-3",
        ])
        self.assertIsNotNone(answer.record)
        self.assertEqual(answer.record.care_instructions, "Chườm lạnh bên ngoài má.")
        self.assertEqual(answer.record.recall_at, datetime(2030, 8, 24, 2, tzinfo=timezone.utc))
        self.assertEqual(answer.record.monitor_until, datetime(2030, 8, 20, 2, tzinfo=timezone.utc))
        self.assertNotIn("message", audit.call_args.args[-1])
        self.assertNotIn("Hướng dẫn", str(audit.call_args))

    def test_unreleased_record_is_denied_without_leaking_content(self):
        from backend.app.features.post_treatment_chat import service

        connection, connect = connection_for()
        with patch.object(service, "_connect", connect), patch.object(service, "append_audit"):
            answer = service.chat(service.ChatRequest(message="Hồ sơ của tôi"), Role.PATIENT)
        self.assertEqual(answer.intent, "MY_RECORD")
        self.assertEqual(answer.citations, [])
        self.assertIsNone(answer.record)
        self.assertIn("chưa được phát hành", answer.answer)

    def test_faq_and_symptom_cards_require_citations(self):
        from backend.app.features.post_treatment_chat import service

        with patch.object(service, "append_audit"):
            faq = service.chat(service.ChatRequest(message="Giờ mở cửa phòng khám?"), Role.PATIENT)
            symptom = service.chat(service.ChatRequest(message="Đau nhẹ sau nhổ răng có bình thường không?"), Role.PATIENT)
        self.assertEqual(faq.intent, "CLINIC_FAQ")
        self.assertTrue(faq.citations)
        self.assertIsNone(faq.record)
        self.assertEqual(symptom.intent, "SYMPTOM_INFO")
        self.assertTrue(symptom.citations)
        self.assertIsNone(symptom.record)
        self.assertNotIn("chẩn đoán", symptom.answer.lower())

    def test_symptom_question_is_not_misrouted_by_faq_word_collision(self):
        from backend.app.features.post_treatment_chat import service

        with patch.object(service, "append_audit"):
            answer = service.chat(service.ChatRequest(message="Bao giờ hết đau?"), Role.PATIENT)
        self.assertEqual(answer.intent, "SYMPTOM_INFO")
        self.assertNotIn("mở cửa", answer.answer)

    def test_red_flag_is_fixed_escalation_and_unknown_abstains(self):
        from backend.app.features.post_treatment_chat import service

        with patch.object(service, "append_audit"):
            red_flags = (
                "Tôi khó thở",
                "Tôi khó nuốt",
                "Tôi sưng lan nhanh",
                "Tôi sưng tăng nhanh",
                "Tôi chảy máu không kiểm soát",
                "Tôi bị chấn thương nặng",
                "Toi kho tho va sung lan nhanh",
            )
            red_answers = [service.chat(service.ChatRequest(message=message), Role.PATIENT) for message in red_flags]
            unknown = service.chat(service.ChatRequest(message="Giá bitcoin hôm nay?"), Role.PATIENT)
        for red in red_answers:
            self.assertTrue(red.escalation)
            self.assertEqual(red.intent, "SYMPTOM_INFO")
            self.assertEqual(red.answer, service.RED_FLAG_ANSWER)
            self.assertTrue(red.citations)
        self.assertIn("không có thông tin đã duyệt", unknown.answer)
        self.assertEqual(unknown.citations, [])

    def test_chat_audit_has_allowlisted_provenance_without_raw_content(self):
        from backend.app.features.post_treatment_chat import service

        raw_message = "Tôi khó thở và đây là nội dung riêng tư"
        with patch.object(service, "append_audit") as audit:
            service.chat(service.ChatRequest(message=raw_message), Role.PATIENT)

        metadata = audit.call_args.args[-1]
        self.assertEqual(metadata["result"], "URGENT_GUIDANCE_SHOWN")
        self.assertEqual(metadata["citation_ids"], ["dental-cards.v1#emergency"])
        self.assertNotIn("http", str(metadata))
        self.assertNotIn("message", metadata)
        self.assertNotIn("answer", metadata)
        self.assertNotIn(raw_message, str(audit.call_args))

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
        self.assertTrue(cards["approved_at"])
        self.assertTrue(cards["governance_sources"])
        for card in cards["cards"]:
            self.assertTrue(card["id"])
            self.assertTrue(card["source"])
        emergency = next(card for card in cards["cards"] if card.get("escalation"))
        self.assertTrue(emergency["source_url"].startswith("https://www.england.nhs.uk/"))
        for flag in service.REQUIRED_RED_FLAGS:
            self.assertIn(service._normalize_text(flag), {service._normalize_text(keyword) for keyword in emergency["keywords"]})
        self.assertEqual(service.APPROVED_CARDS["version"], cards["version"])

    def test_release_and_chat_inputs_are_trimmed_and_require_aware_datetimes(self):
        from backend.app.features.post_treatment_chat import service

        recall_at, monitor_until = future_release_datetimes()
        plus_seven = timezone(timedelta(hours=7))
        payload = service.ReleaseRequest(
            care_instructions="  Chườm lạnh bên ngoài má.  ",
            recall_at=recall_at.astimezone(plus_seven).isoformat(),
            monitor_until=monitor_until.astimezone(plus_seven).isoformat(),
        )
        self.assertEqual(payload.care_instructions, "Chườm lạnh bên ngoài má.")
        self.assertEqual(payload.recall_at.tzinfo, timezone.utc)
        self.assertEqual(payload.recall_at, recall_at)
        self.assertEqual(payload.monitor_until, monitor_until)
        self.assertEqual(service.ChatRequest(message="  giờ mở cửa?  ").message, "giờ mở cửa?")

        for care, recall in (
            ("   ", recall_at.isoformat()),
            ("Care", recall_at.replace(tzinfo=None).isoformat()),
        ):
            with self.subTest(care=care, recall=recall), self.assertRaises(ValidationError):
                service.ReleaseRequest(care_instructions=care, recall_at=recall, monitor_until=monitor_until)

    def test_release_dates_must_be_strictly_future_without_cross_field_ordering(self):
        from backend.app.features.post_treatment_chat import service

        fixed_now = datetime(2030, 8, 18, 2, tzinfo=timezone.utc)
        future_recall = fixed_now + timedelta(days=1)
        future_monitor = fixed_now + timedelta(days=2)
        with patch.object(service, "_utc_now", return_value=fixed_now):
            payload = service.ReleaseRequest(
                care_instructions="Care",
                recall_at=future_recall,
                monitor_until=future_monitor,
            )
            reverse_order_payload = service.ReleaseRequest(
                care_instructions="Care",
                recall_at=future_monitor,
                monitor_until=future_recall,
            )

            self.assertEqual(payload.recall_at, future_recall)
            self.assertEqual(reverse_order_payload.monitor_until, future_recall)

            for field in ("recall_at", "monitor_until"):
                for invalid_value in (fixed_now, fixed_now - timedelta(microseconds=1)):
                    values = {
                        "care_instructions": "Care",
                        "recall_at": future_recall,
                        "monitor_until": future_monitor,
                    }
                    values[field] = invalid_value
                    with self.subTest(field=field, invalid_value=invalid_value), self.assertRaises(ValidationError) as caught:
                        service.ReleaseRequest(**values)
                    self.assertEqual(caught.exception.errors()[0]["loc"], (field,))

    def test_matching_repeat_release_is_idempotent_and_changed_release_is_rejected(self):
        from backend.app.features.post_treatment_chat import service

        recall_at, monitor_until = future_release_datetimes()
        payload = service.ReleaseRequest(
            care_instructions="Chườm lạnh bên ngoài má.",
            recall_at=recall_at,
            monitor_until=monitor_until,
        )
        existing = [
            {"id": "e1", "code": code, "value": value, "released_to_patient_at": "now", "updated_at": "now"}
            for code, value in service._release_items(payload)
        ]
        connection, connect = connection_for(*existing, one_rows=[
            {"stage": "CLOSED"},
            {"id": "t1", "status": "OPEN", "owner_role": "ASSISTANT", "due_at": payload.monitor_until},
        ])
        with patch.object(service, "_connect", connect):
            result = service.release_encounter(service.DEMO_ENCOUNTER_ID, payload, Role.DENTIST)

        sql = "\n".join(query for query, _params in connection.calls)
        self.assertNotIn("INSERT INTO evidence_items", sql)
        self.assertNotIn("INSERT INTO audit_events", sql)
        self.assertEqual(result["follow_up_task"]["id"], "t1")

        changed = service.ReleaseRequest(
            care_instructions="Nội dung sửa sau khi đã phát hành.",
            recall_at=payload.recall_at,
            monitor_until=payload.monitor_until,
        )
        changed_connection, changed_connect = connection_for(*existing, one_rows=[{"stage": "CLOSED"}])
        with patch.object(service, "_connect", changed_connect), self.assertRaises(AppError) as caught:
            service.release_encounter(service.DEMO_ENCOUNTER_ID, changed, Role.DENTIST)
        self.assertEqual(caught.exception.payload["code"], "RELEASE_ALREADY_EXISTS")
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(len(changed_connection.calls), 2)

    def test_database_enforces_verified_immutable_releases(self):
        schema = (ROOT / "db/init/50_post_treatment_chat.sql").read_text(encoding="utf-8")
        self.assertIn("released_to_patient_at IS NULL OR state = 'VERIFIED'", schema)
        self.assertIn("prevent_released_evidence_item_mutation", schema)
        self.assertIn("BEFORE UPDATE", schema)
        self.assertIn("TG_OP = 'DELETE'", schema)
        self.assertIn("BEFORE DELETE", schema)
        for field in ("state", "value", "source_type", "source_ref", "actor_role", "released_to_patient_at"):
            self.assertIn(f"NEW.{field} IS DISTINCT FROM OLD.{field}", schema)

    def test_frontend_exports_route_and_renders_urgent_and_release_states(self):
        source = (ROOT / "frontend/src/features/post-treatment-chat/index.jsx").read_text(encoding="utf-8")
        self.assertIn('path: "/post-treatment"', source)
        self.assertIn('role="alert"', source)
        self.assertIn("data.escalation", source)
        self.assertIn("data.follow_up_task", source)
        self.assertIn("summary.citations", source)

        router_source = (ROOT / "backend/app/features/post_treatment_chat/router.py").read_text(encoding="utf-8")
        self.assertIn("response_model_exclude_none=True", router_source)

    def test_frontend_reviews_release_and_preserves_patient_safety_guidance(self):
        source = (ROOT / "frontend/src/features/post-treatment-chat/index.jsx").read_text(encoding="utf-8")
        styles = (ROOT / "frontend/src/features/post-treatment-chat/index.css").read_text(encoding="utf-8")

        for expected in (
            "prepareReleaseReview",
            "confirmRelease",
            "Xác nhận và phát hành",
            "parseLocalDateTime",
            "pinnedEscalation",
            "Chat không được theo dõi theo thời gian thực",
            "data.record",
            "response.text()",
            'aria-invalid={Boolean(fieldErrors.recall)}',
            'maxLength={1000}',
            'maxLength={2000}',
            'import "./index.css"',
        ):
            self.assertIn(expected, source)
        self.assertIn(":focus-visible", styles)


if __name__ == "__main__":
    unittest.main()
