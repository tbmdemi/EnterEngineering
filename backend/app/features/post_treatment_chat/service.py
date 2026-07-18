import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from ...core.contracts import Role
from ...core.errors import AppError
from ...core.services import _connect, append_audit
from .templates import TemplateCatalogResponse, list_approved_templates


DEMO_ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003"
EVIDENCE_CODES = (
    "POST_CARE_INSTRUCTIONS",
    "POST_RECALL",
    "POST_COMPLICATION_MONITORING",
)
REQUIRED_RED_FLAGS = (
    "khó thở",
    "khó nuốt",
    "sưng lan nhanh",
    "sưng tăng nhanh",
    "chảy máu không kiểm soát",
    "chấn thương nặng",
)
PATIENT_RECORD_FIELDS = {
    "POST_CARE_INSTRUCTIONS": ("Hướng dẫn chăm sóc", "text", "care_instructions"),
    "POST_RECALL": ("Lịch tái khám", "recall_at", "recall_at"),
    "POST_COMPLICATION_MONITORING": ("Theo dõi biến chứng đến", "monitor_until", "monitor_until"),
}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReleaseRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    care_instructions: str = Field(min_length=1, max_length=2000)
    recall_at: AwareDatetime
    monitor_until: AwareDatetime

    @field_validator("recall_at", "monitor_until")
    @classmethod
    def normalize_utc(cls, value: datetime) -> datetime:
        normalized = value.astimezone(timezone.utc)
        if normalized <= _utc_now():
            raise ValueError("Date and time must be strictly in the future")
        return normalized

class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=1000)


class PatientRecord(BaseModel):
    care_instructions: str | None = None
    recall_at: datetime | None = None
    monitor_until: datetime | None = None


class ChatResponse(BaseModel):
    intent: Literal["MY_RECORD", "CLINIC_FAQ", "SYMPTOM_INFO"]
    answer: str
    citations: list[str]
    escalation: bool = False
    record: PatientRecord | None = None


class ReleasedSummary(BaseModel):
    care_instructions: str
    recall_at: datetime
    monitor_until: datetime
    citations: list[str]


class FollowUpTaskSummary(BaseModel):
    id: str
    status: str
    owner_role: str
    due_at: datetime


class ReleaseResponse(BaseModel):
    encounter_id: str
    released: bool
    summary: ReleasedSummary
    follow_up_task: FollowUpTaskSummary


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.casefold())
    without_marks = "".join(char for char in decomposed if unicodedata.category(char) != "Mn")
    without_marks = without_marks.replace("đ", "d")
    return " ".join(re.sub(r"[^\w]+", " ", without_marks).split())


def _has_keyword(normalized_message: str, keywords: list[str] | tuple[str, ...]) -> bool:
    padded_message = f" {normalized_message} "
    return any(f" {_normalize_text(keyword)} " in padded_message for keyword in keywords)


def _load_approved_cards() -> dict:
    fixture = Path(__file__).with_name("approved_cards.v1.json")
    data = json.loads(fixture.read_text(encoding="utf-8"))
    if not all(isinstance(data.get(field), str) and data[field].strip() for field in ("version", "approved_by", "approved_at")):
        raise RuntimeError("Approved dental cards require version and approval provenance")

    cards = data.get("cards")
    if not isinstance(cards, list) or not cards:
        raise RuntimeError("Approved dental cards must contain at least one card")

    card_ids = set()
    allowed_intents = {"CLINIC_FAQ", "SYMPTOM_INFO"}
    for card in cards:
        required_strings = ("id", "intent", "answer", "source")
        if not isinstance(card, dict) or not all(isinstance(card.get(field), str) and card[field].strip() for field in required_strings):
            raise RuntimeError("Every approved dental card requires id, intent, answer and source")
        if card["id"] in card_ids or card["intent"] not in allowed_intents:
            raise RuntimeError("Approved dental card ids must be unique and intents must be allowlisted")
        if not isinstance(card.get("keywords"), list) or not card["keywords"] or not all(isinstance(keyword, str) and keyword.strip() for keyword in card["keywords"]):
            raise RuntimeError("Every approved dental card requires keywords")
        card_ids.add(card["id"])

    emergency_cards = [card for card in cards if card.get("escalation") is True]
    if len(emergency_cards) != 1 or emergency_cards[0]["intent"] != "SYMPTOM_INFO":
        raise RuntimeError("Approved dental cards require exactly one symptom escalation card")
    emergency_keywords = {_normalize_text(keyword) for keyword in emergency_cards[0]["keywords"]}
    missing_flags = [flag for flag in REQUIRED_RED_FLAGS if _normalize_text(flag) not in emergency_keywords]
    if missing_flags:
        raise RuntimeError("The emergency card is missing required red-flag coverage")
    return data


APPROVED_CARDS = _load_approved_cards()
RED_FLAG_ANSWER = next(card["answer"] for card in APPROVED_CARDS["cards"] if card.get("escalation"))


def _citation(card: dict) -> str:
    source = card["source"]
    if card.get("source_url"):
        source = f"{source} — {card['source_url']}"
    return f"{APPROVED_CARDS['version']}#{card['id']}: {source}"


def _require(role, allowed):
    if role not in allowed:
        raise AppError("ROLE_FORBIDDEN", "Role is not allowed for this action", status_code=403)


def _release_items(payload: ReleaseRequest):
    return (
        ("POST_CARE_INSTRUCTIONS", {"text": payload.care_instructions}),
        ("POST_RECALL", {"recall_at": payload.recall_at.isoformat()}),
        ("POST_COMPLICATION_MONITORING", {"monitor_until": payload.monitor_until.isoformat()}),
    )


def _release_result(encounter_id: str, payload: ReleaseRequest, evidence: list[dict], task: dict):
    citations = [
        f"RELEASED_RECORD#{item.get('id') or item['code']}"
        for item in evidence
        if item.get("code") in EVIDENCE_CODES
    ]
    safe_task = {
        "id": str(task["id"]),
        "status": task.get("status", "OPEN"),
        "owner_role": task.get("owner_role", "ASSISTANT"),
        "due_at": task.get("due_at") or payload.monitor_until,
    }
    return {
        "encounter_id": encounter_id,
        "released": True,
        "summary": {
            "care_instructions": payload.care_instructions,
            "recall_at": payload.recall_at,
            "monitor_until": payload.monitor_until,
            "citations": citations,
        },
        "follow_up_task": safe_task,
        # Kept for the internal feature handoff; the API response model filters these rows.
        "evidence": evidence,
        "task": task,
    }


def release_encounter(encounter_id, payload, role):
    _require(role, {Role.DENTIST})
    if encounter_id != DEMO_ENCOUNTER_ID:
        raise AppError("ENCOUNTER_NOT_FOUND", "Encounter was not found", status_code=404)

    items = _release_items(payload)
    expected_values = dict(items)
    task_key = f"post-complication:{encounter_id}"
    with _connect() as connection:
        encounter = connection.execute("SELECT stage FROM encounters WHERE id = %s FOR UPDATE", (encounter_id,)).fetchone()
        if not encounter:
            raise AppError("ENCOUNTER_NOT_FOUND", "Encounter was not found", status_code=404)
        if encounter["stage"] not in {"POST_TREATMENT", "CLOSED"}:
            raise AppError("ENCOUNTER_NOT_RELEASABLE", "Encounter must be post-treatment before release", {"stage": encounter["stage"]}, 409)

        existing = [dict(row) for row in connection.execute(
            """SELECT id, code, value, released_to_patient_at, updated_at
               FROM evidence_items
               WHERE encounter_id = %s AND code = ANY(%s) AND released_to_patient_at IS NOT NULL""",
            (encounter_id, list(EVIDENCE_CODES)),
        ).fetchall()]
        if existing:
            existing_values = {row["code"]: row["value"] for row in existing}
            if set(existing_values) != set(expected_values) or any(existing_values[code] != expected_values[code] for code in EVIDENCE_CODES):
                raise AppError(
                    "RELEASE_ALREADY_EXISTS",
                    "Released post-treatment content is immutable and cannot be overwritten",
                    {"evidence_codes": sorted(existing_values)},
                    409,
                )
            task = connection.execute("SELECT * FROM tasks WHERE idempotency_key = %s", (task_key,)).fetchone()
            if not task:
                raise AppError("RELEASE_STATE_INVALID", "Released content is missing its follow-up task", status_code=409)
            return _release_result(encounter_id, payload, existing, dict(task))

        evidence = []
        for code, value in items:
            evidence.append(dict(connection.execute(
                """INSERT INTO evidence_items (encounter_id, code, state, value, source_type, source_ref, actor_role, released_to_patient_at)
                   VALUES (%s, %s, 'VERIFIED', %s::jsonb, 'FORM', 'post-treatment-release', %s, now())
                   ON CONFLICT (encounter_id, code) DO UPDATE SET state = 'VERIFIED', value = EXCLUDED.value,
                     source_type = EXCLUDED.source_type, source_ref = EXCLUDED.source_ref, actor_role = EXCLUDED.actor_role,
                     released_to_patient_at = now(), updated_at = now() RETURNING *""",
                (encounter_id, code, json.dumps(value, ensure_ascii=False), role.value),
            ).fetchone()))
        task = dict(connection.execute(
            """INSERT INTO tasks (encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key)
               VALUES (%s, 'POST_COMPLICATION_MONITORING', 'PATIENT_FOLLOW_UP', 'ASSISTANT', %s, %s)
               ON CONFLICT (idempotency_key) DO UPDATE SET due_at = EXCLUDED.due_at, owner_role = EXCLUDED.owner_role
               RETURNING *""",
            (encounter_id, payload.monitor_until, task_key),
        ).fetchone())
        connection.execute(
            """INSERT INTO audit_events (actor_role, action, object_type, object_id, encounter_id, metadata)
               VALUES (%s, 'POST_TREATMENT_RELEASED', 'encounter', %s, %s, %s::jsonb)""",
            (role.value, encounter_id, encounter_id, json.dumps({"evidence_codes": list(EVIDENCE_CODES), "task_id": str(task["id"])})),
        )
    return _release_result(encounter_id, payload, evidence, task)


def _audit_chat(intent, citations, escalation):
    citation_ids = [citation.partition(":")[0] for citation in citations]
    append_audit("PATIENT", "PORTAL_CHAT_ANSWERED", "encounter", DEMO_ENCOUNTER_ID, DEMO_ENCOUNTER_ID, {
        "intent": intent,
        "result": "URGENT_GUIDANCE_SHOWN" if escalation else "ANSWERED" if citations else "ABSTAINED",
        "citation_count": len(citation_ids),
        "citation_ids": citation_ids,
    })


def _record_response() -> ChatResponse:
    with _connect() as connection:
        rows = connection.execute(
            """SELECT id, code, value, updated_at
               FROM evidence_items
               WHERE encounter_id = %s
                 AND code = ANY(%s)
                 AND state = 'VERIFIED'
                 AND released_to_patient_at IS NOT NULL
               ORDER BY code""",
            (DEMO_ENCOUNTER_ID, list(EVIDENCE_CODES)),
        ).fetchall()

    parts = []
    citations = []
    record_values = {}
    for row in rows:
        field = PATIENT_RECORD_FIELDS.get(row["code"])
        value = row.get("value")
        if not field or not isinstance(value, dict):
            continue
        label, value_key, record_key = field
        display_value = value.get(value_key)
        if not isinstance(display_value, str) or not display_value.strip():
            continue
        parts.append(f"{label}: {display_value}")
        citations.append(f"RELEASED_RECORD#{row.get('id') or row['code']}")
        record_values[record_key] = display_value

    if not parts:
        return ChatResponse(intent="MY_RECORD", answer="Hồ sơ sau điều trị chưa được phát hành cho bệnh nhân.", citations=[])
    return ChatResponse(
        intent="MY_RECORD",
        answer="; ".join(parts),
        citations=citations,
        record=PatientRecord(**record_values),
    )


def chat(payload, role):
    _require(role, {Role.PATIENT})
    normalized_message = _normalize_text(payload.message)
    cards = APPROVED_CARDS["cards"]
    emergency = next(card for card in cards if card.get("escalation"))

    if _has_keyword(normalized_message, emergency["keywords"]):
        response = ChatResponse(intent="SYMPTOM_INFO", answer=emergency["answer"], citations=[_citation(emergency)], escalation=True)
    elif _has_keyword(normalized_message, ("hồ sơ", "hướng dẫn của tôi", "lịch tái khám", "my record")):
        response = _record_response()
    else:
        symptom = next(
            (
                card
                for card in cards
                if card["intent"] == "SYMPTOM_INFO"
                and not card.get("escalation")
                and _has_keyword(normalized_message, card["keywords"])
            ),
            None,
        )
        faq = next(
            (
                card
                for card in cards
                if card["intent"] == "CLINIC_FAQ" and _has_keyword(normalized_message, card["keywords"])
            ),
            None,
        )
        if symptom:
            response = ChatResponse(intent="SYMPTOM_INFO", answer=symptom["answer"], citations=[_citation(symptom)])
        elif faq:
            response = ChatResponse(intent="CLINIC_FAQ", answer=faq["answer"], citations=[_citation(faq)])
        else:
            response = ChatResponse(intent="SYMPTOM_INFO", answer="Tôi không có thông tin đã duyệt để trả lời câu hỏi này. Hãy liên hệ phòng khám.", citations=[])

    _audit_chat(response.intent, response.citations, response.escalation)
    return response


def list_templates(role, locale: str | None = None, procedure_code: str | None = None) -> TemplateCatalogResponse:
    _require(role, {Role.DENTIST})
    return list_approved_templates(locale=locale, procedure_code=procedure_code)
