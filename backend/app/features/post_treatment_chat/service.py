import json
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from ...core.contracts import Role
from ...core.errors import AppError
from ...core.services import _connect, append_audit


DEMO_ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003"


class ReleaseRequest(BaseModel):
    care_instructions: str = Field(min_length=1, max_length=2000)
    recall_at: datetime
    monitor_until: datetime


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)


class ChatResponse(BaseModel):
    intent: Literal["MY_RECORD", "CLINIC_FAQ", "SYMPTOM_INFO"]
    answer: str
    citations: list[str]
    escalation: bool = False


APPROVED_CARDS = json.loads(Path(__file__).with_name("approved_cards.v1.json").read_text())
RED_FLAG_ANSWER = next(card["answer"] for card in APPROVED_CARDS["cards"] if card.get("escalation"))


def _citation(card):
    return f"{APPROVED_CARDS['version']}#{card['id']}: {card['source']}"


def _require(role, allowed):
    if role not in allowed:
        raise AppError("ROLE_FORBIDDEN", "Role is not allowed for this action", status_code=403)


def release_encounter(encounter_id, payload, role):
    _require(role, {Role.DENTIST})
    if encounter_id != DEMO_ENCOUNTER_ID:
        raise AppError("ENCOUNTER_NOT_FOUND", "Encounter was not found", status_code=404)

    items = (
        ("POST_CARE_INSTRUCTIONS", {"text": payload.care_instructions}),
        ("POST_RECALL", {"recall_at": payload.recall_at.isoformat()}),
        ("POST_COMPLICATION_MONITORING", {"monitor_until": payload.monitor_until.isoformat()}),
    )
    with _connect() as connection:
        encounter = connection.execute("SELECT stage FROM encounters WHERE id = %s FOR UPDATE", (encounter_id,)).fetchone()
        if not encounter:
            raise AppError("ENCOUNTER_NOT_FOUND", "Encounter was not found", status_code=404)
        if encounter["stage"] not in {"POST_TREATMENT", "CLOSED"}:
            raise AppError("ENCOUNTER_NOT_RELEASABLE", "Encounter must be post-treatment before release", {"stage": encounter["stage"]}, 409)
        evidence = []
        for code, value in items:
            evidence.append(dict(connection.execute(
                """INSERT INTO evidence_items (encounter_id, code, state, value, source_type, source_ref, actor_role, released_to_patient_at)
                   VALUES (%s, %s, 'VERIFIED', %s::jsonb, 'FORM', 'post-treatment-release', %s, now())
                   ON CONFLICT (encounter_id, code) DO UPDATE SET state = 'VERIFIED', value = EXCLUDED.value,
                     source_type = EXCLUDED.source_type, source_ref = EXCLUDED.source_ref, actor_role = EXCLUDED.actor_role,
                     released_to_patient_at = now(), updated_at = now() RETURNING *""",
                (encounter_id, code, json.dumps(value), role.value),
            ).fetchone()))
        task = dict(connection.execute(
            """INSERT INTO tasks (encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key)
               VALUES (%s, 'POST_COMPLICATION_MONITORING', 'PATIENT_FOLLOW_UP', 'ASSISTANT', %s, %s)
               ON CONFLICT (idempotency_key) DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key RETURNING *""",
            (encounter_id, payload.monitor_until, f"post-complication:{encounter_id}"),
        ).fetchone())
        connection.execute(
            """INSERT INTO audit_events (actor_role, action, object_type, object_id, encounter_id, metadata)
               VALUES (%s, 'POST_TREATMENT_RELEASED', 'encounter', %s, %s, %s::jsonb)""",
            (role.value, encounter_id, encounter_id, json.dumps({"evidence_codes": [code for code, _ in items], "task_id": str(task["id"])})),
        )
    return {"encounter_id": encounter_id, "evidence": evidence, "task": task, "released": True}


def _audit_chat(intent, citations, escalation):
    append_audit("PATIENT", "PORTAL_CHAT_ANSWERED", "encounter", DEMO_ENCOUNTER_ID, DEMO_ENCOUNTER_ID, {
        "intent": intent, "result": "ESCALATED" if escalation else "ANSWERED" if citations else "ABSTAINED", "citation_count": len(citations)
    })


def chat(payload, role):
    _require(role, {Role.PATIENT})
    message = payload.message.casefold()
    cards = APPROVED_CARDS["cards"]
    emergency = next(card for card in cards if card.get("escalation"))
    if any(flag in message for flag in emergency["keywords"]):
        response = ChatResponse(intent="SYMPTOM_INFO", answer=emergency["answer"], citations=[_citation(emergency)], escalation=True)
    elif any(term in message for term in ("hồ sơ", "hướng dẫn của tôi", "lịch tái khám", "my record")):
        with _connect() as connection:
            rows = connection.execute(
                "SELECT code, value FROM evidence_items WHERE encounter_id = %s AND state = 'VERIFIED' AND released_to_patient_at IS NOT NULL ORDER BY code",
                (DEMO_ENCOUNTER_ID,),
            ).fetchall()
        if rows:
            parts = [str(row["value"].get("text") or row["value"].get("recall_at") or row["value"].get("monitor_until")) for row in rows]
            response = ChatResponse(intent="MY_RECORD", answer="; ".join(parts), citations=[f"RELEASED_RECORD#{row['code']}" for row in rows])
        else:
            response = ChatResponse(intent="MY_RECORD", answer="Hồ sơ sau điều trị chưa được phát hành cho bệnh nhân.", citations=[])
    else:
        card = next((card for card in cards if card["intent"] == "CLINIC_FAQ" and any(key in message for key in card["keywords"])), None)
        if card:
            response = ChatResponse(intent="CLINIC_FAQ", answer=card["answer"], citations=[_citation(card)])
        else:
            card = next((card for card in cards if card["intent"] == "SYMPTOM_INFO" and not card.get("escalation") and any(key in message for key in card["keywords"])), None)
            response = ChatResponse(intent="SYMPTOM_INFO", answer=card["answer"], citations=[_citation(card)]) if card else ChatResponse(intent="SYMPTOM_INFO", answer="Tôi không có thông tin đã duyệt để trả lời câu hỏi này. Hãy liên hệ phòng khám.", citations=[])
    _audit_chat(response.intent, response.citations, response.escalation)
    return response
