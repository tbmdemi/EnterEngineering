import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from ...core.contracts import Role
from ...core.errors import AppError
from ...core.services import _connect, append_audit


DEMO_ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003"
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    care_instructions: NonEmptyText = Field(max_length=2000)
    recall_at: AwareDatetime
    monitor_until: AwareDatetime

    @field_validator("recall_at", "monitor_until")
    @classmethod
    def normalize_datetime(cls, value: datetime) -> datetime:
        # Canonical UTC values make equivalent offsets semantically idempotent.
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_release_window(self):
        now = datetime.now(timezone.utc)
        if self.recall_at <= now:
            raise ValueError("recall_at must be in the future")
        if self.monitor_until <= now:
            raise ValueError("monitor_until must be in the future")
        if self.monitor_until > self.recall_at:
            raise ValueError("monitor_until must be on or before recall_at")
        return self


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: NonEmptyText = Field(max_length=1000)
    encounter_id: UUID


class ChatResponse(BaseModel):
    intent: Literal["MY_RECORD", "CLINIC_FAQ", "SYMPTOM_INFO"]
    answer: str
    citations: list[str]
    escalation: bool = False


APPROVED_CARDS = json.loads(Path(__file__).with_name("approved_cards.v1.json").read_text(encoding="utf-8"))
RED_FLAG_ANSWER = next(card["answer"] for card in APPROVED_CARDS["cards"] if card.get("escalation"))


def _citation(card):
    return f"{APPROVED_CARDS['version']}#{card['id']}: {card['source']}"


def _require(role, allowed):
    if role not in allowed:
        raise AppError("ROLE_FORBIDDEN", "Role is not allowed for this action", status_code=403)


def _parse_aware_datetime(value):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _same_release_value(code, existing_value, requested_value):
    if not isinstance(existing_value, dict):
        return False
    if code == "POST_CARE_INSTRUCTIONS":
        return existing_value.get("text") == requested_value["text"]
    field = "recall_at" if code == "POST_RECALL" else "monitor_until"
    existing_at = _parse_aware_datetime(existing_value.get(field))
    requested_at = _parse_aware_datetime(requested_value[field])
    return existing_at is not None and existing_at == requested_at


def release_encounter(encounter_id, payload, role):
    _require(role, {Role.DENTIST})
    items = (
        ("POST_CARE_INSTRUCTIONS", {"text": payload.care_instructions}),
        ("POST_RECALL", {"recall_at": payload.recall_at.isoformat()}),
        ("POST_COMPLICATION_MONITORING", {"monitor_until": payload.monitor_until.isoformat()}),
    )
    with _connect() as connection:
        encounter = connection.execute("SELECT stage FROM encounters WHERE id = %s FOR UPDATE", (encounter_id,)).fetchone()
        if not encounter:
            raise AppError("ENCOUNTER_NOT_FOUND", "Encounter was not found", status_code=404)
        if encounter["stage"] == "CLOSED":
            raise AppError("ENCOUNTER_CLOSED", "Closed encounters are read-only", {"encounter_id": str(encounter_id)}, 409)
        if encounter["stage"] != "POST_TREATMENT":
            raise AppError("ENCOUNTER_NOT_RELEASABLE", "Encounter must be post-treatment before release", {"stage": encounter["stage"]}, 409)
        existing_rows = connection.execute(
            """SELECT * FROM evidence_items
               WHERE encounter_id = %s AND code = ANY(%s)
                 AND state = 'VERIFIED' AND released_to_patient_at IS NOT NULL""",
            (encounter_id, [code for code, _value in items]),
        ).fetchall()
        existing = {row["code"]: dict(row) for row in existing_rows}
        if all(
            code in existing and _same_release_value(code, existing[code]["value"], value)
            for code, value in items
        ):
            current_task = connection.execute(
                "SELECT * FROM tasks WHERE idempotency_key = %s",
                (f"post-complication:{encounter_id}",),
            ).fetchone()
            if current_task and _parse_aware_datetime(current_task["due_at"]) == payload.monitor_until:
                return {
                    "encounter_id": encounter_id,
                    "evidence": [existing[code] for code, _value in items],
                    "task": dict(current_task),
                    "released": True,
                    "idempotent_replay": True,
                }
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
               ON CONFLICT (idempotency_key) DO UPDATE SET
                 due_at = EXCLUDED.due_at,
                 status = CASE
                   WHEN tasks.due_at IS DISTINCT FROM EXCLUDED.due_at
                     AND tasks.status IN ('COMPLETED', 'CANCELLED') THEN 'OPEN'
                   ELSE tasks.status
                 END,
                 updated_at = now(),
                 completed_at = CASE
                   WHEN tasks.due_at IS DISTINCT FROM EXCLUDED.due_at THEN NULL
                   ELSE tasks.completed_at
                 END,
                 cancelled_at = CASE
                   WHEN tasks.due_at IS DISTINCT FROM EXCLUDED.due_at THEN NULL
                   ELSE tasks.cancelled_at
                 END
               RETURNING *""",
            (encounter_id, payload.monitor_until, f"post-complication:{encounter_id}"),
        ).fetchone())
        connection.execute(
            """INSERT INTO audit_events (actor_role, action, object_type, object_id, encounter_id, metadata)
               VALUES (%s, 'POST_TREATMENT_RELEASED', 'encounter', %s, %s, %s::jsonb)""",
            (role.value, encounter_id, encounter_id, json.dumps({"evidence_codes": [code for code, _ in items], "task_id": str(task["id"])})),
        )
    return {"encounter_id": encounter_id, "evidence": evidence, "task": task, "released": True, "idempotent_replay": False}


def _audit_chat(encounter_id, intent, citations, escalation):
    append_audit("PATIENT", "PORTAL_CHAT_ANSWERED", "encounter", encounter_id, encounter_id, {
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
                (str(payload.encounter_id),),
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
    _audit_chat(payload.encounter_id, response.intent, response.citations, response.escalation)
    return response
