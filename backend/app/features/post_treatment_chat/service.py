from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from ...core.contracts import Role
from ...core.errors import AppError
from ...core.services import _connect, append_audit, ensure_task, upsert_evidence


DEMO_ENCOUNTER_ID = "00000000-0000-0000-0000-000000000003"
RED_FLAG_ANSWER = "Đây có thể là tình trạng khẩn cấp nha khoa. Hãy gọi cấp cứu địa phương hoặc đến cơ sở cấp cứu ngay; không chờ tư vấn qua chat."


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


FAQ = {
    "giờ": ("Phòng khám mở cửa 08:00–17:00 từ thứ Hai đến thứ Sáu.", "CLINIC_FAQ#hours"),
    "địa chỉ": ("Địa chỉ demo: 123 Nguyễn Huệ, Quận 1.", "CLINIC_FAQ#address"),
}
SYMPTOMS = {
    "đau": ("Đau nhẹ có thể xuất hiện sau điều trị. Làm theo hướng dẫn đã phát hành; nếu đau tăng hoặc kéo dài, hãy liên hệ phòng khám.", "DENTAL_CARD#post-treatment-pain"),
    "sưng": ("Sưng nhẹ có thể xuất hiện sau điều trị. Nếu sưng tăng nhanh, lan rộng hoặc kèm khó thở/nuốt, hãy đi cấp cứu ngay.", "DENTAL_CARD#post-treatment-swelling"),
}


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
    evidence = [upsert_evidence(encounter_id, code, "VERIFIED", value, "FORM", "post-treatment-release", role.value) for code, value in items]
    task = ensure_task(encounter_id, "POST_COMPLICATION_MONITORING", "PATIENT_FOLLOW_UP", "ASSISTANT", payload.monitor_until, f"post-complication:{encounter_id}")
    with _connect() as connection:
        connection.execute(
            "UPDATE evidence_items SET released_to_patient_at = now() WHERE encounter_id = %s AND code = ANY(%s) AND state = 'VERIFIED'",
            (encounter_id, [code for code, _ in items]),
        )
    append_audit(role.value, "POST_TREATMENT_RELEASED", "encounter", encounter_id, encounter_id, {"evidence_codes": [code for code, _ in items], "task_id": str(task["id"])})
    return {"encounter_id": encounter_id, "evidence": evidence, "task": task, "released": True}


def _audit_chat(intent, citations, escalation):
    append_audit("PATIENT", "PORTAL_CHAT_ANSWERED", "encounter", DEMO_ENCOUNTER_ID, DEMO_ENCOUNTER_ID, {
        "intent": intent, "result": "ESCALATED" if escalation else "ANSWERED" if citations else "ABSTAINED", "citation_count": len(citations)
    })


def chat(payload, role):
    _require(role, {Role.PATIENT})
    message = payload.message.casefold()
    red_flags = ("khó thở", "khó nuốt", "sưng lan nhanh", "sưng lan rộng", "chảy máu không kiểm soát", "chấn thương nặng")
    if any(flag in message for flag in red_flags):
        response = ChatResponse(intent="SYMPTOM_INFO", answer=RED_FLAG_ANSWER, citations=["DENTAL_SAFETY_CARD#emergency"], escalation=True)
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
        card = next((value for key, value in FAQ.items() if key in message), None)
        if card:
            response = ChatResponse(intent="CLINIC_FAQ", answer=card[0], citations=[card[1]])
        else:
            card = next((value for key, value in SYMPTOMS.items() if key in message), None)
            response = ChatResponse(intent="SYMPTOM_INFO", answer=card[0], citations=[card[1]]) if card else ChatResponse(intent="SYMPTOM_INFO", answer="Tôi không có thông tin đã duyệt để trả lời câu hỏi này. Hãy liên hệ phòng khám.", citations=[])
    _audit_chat(response.intent, response.citations, response.escalation)
    return response
