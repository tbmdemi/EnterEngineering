import json
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ... import dependencies
from ...core import services
from ...core.contracts import Role
from ...core.errors import AppError


router = APIRouter(prefix="/api/v1/encounters", tags=["pre-treatment"])
CODES = ("PRE_MEDICAL_HISTORY", "PRE_ALLERGY", "PRE_VITALS", "PRE_STERILIZATION", "PRE_IMAGING")
STAFF_ROLES = {Role.ASSISTANT, Role.DENTIST}
READ_ROLES = {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST, Role.QA}
AI_REVIEWS = {
    "PRE_MEDICAL_HISTORY": {
        "state": "DRAFT",
        "suggestion": {"summary": "No relevant medical contraindications noted in the intake record."},
        "citations": [{"ref": "DOC-DEMO-001", "label": "Intake record", "excerpt": "Patient reported no relevant medical conditions or medication changes."}],
    },
    "PRE_ALLERGY": {
        "state": "DRAFT",
        "suggestion": {"status": "NONE_KNOWN"},
        "citations": [{"ref": "DOC-DEMO-002", "label": "Allergy intake", "excerpt": "No known allergies reported."}],
    },
    "PRE_VITALS": {
        "state": "DRAFT",
        "suggestion": {"systolic": 120, "diastolic": 80, "pulse": 72},
        "citations": [{"ref": "DOC-DEMO-003", "label": "Vitals record", "excerpt": "Recorded blood pressure 120/80 mmHg; pulse 72 bpm."}],
    },
    "PRE_STERILIZATION": {
        "state": "DRAFT",
        "suggestion": {"cycle_or_tray_id": "AUTOCLAVE-2026-0718-A"},
        "citations": [{"ref": "DOC-DEMO-004", "label": "Sterilization log", "excerpt": "Tray released from autoclave cycle AUTOCLAVE-2026-0718-A."}],
    },
    "PRE_IMAGING": {
        "state": "DRAFT",
        "suggestion": {"imaging_reference": "XRAY-2026-001"},
        "citations": [{"ref": "DOC-DEMO-005", "label": "Imaging register", "excerpt": "Current encounter imaging reference XRAY-2026-001 is available for review."}],
    },
}


class Attestation(BaseModel):
    value: Dict[str, Any]
    performed_at: datetime


def _read_evidence(encounter_id):
    with services._connect() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT code, state, value, actor_role, updated_at FROM evidence_items WHERE encounter_id = %s AND code = ANY(%s)",
            (encounter_id, list(CODES) + ["PRE_PROCEDURE"]),
        ).fetchall()]


def _require_encounter(encounter_id):
    services.require_encounter(encounter_id)


def _requires_imaging(encounter_id):
    procedure = next((row for row in _read_evidence(encounter_id) if row["code"] == "PRE_PROCEDURE"), None)
    if not procedure or procedure["state"] != "VERIFIED" or "requires_imaging" not in procedure["value"]:
        return None
    value = procedure["value"]["requires_imaging"]
    return value if value is True or value is False else None


def _require_reader(role):
    if role not in READ_ROLES:
        raise AppError("PRE_TREATMENT_ROLE_FORBIDDEN", "Staff role is required", {}, 403)


def _read_audit(encounter_id):
    with services._connect() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT actor_role, action, metadata, created_at FROM audit_events WHERE encounter_id = %s AND action LIKE 'PRE_TREATMENT_%%' ORDER BY created_at DESC",
            (encounter_id,),
        ).fetchall()]


def _reset_demo_data(encounter_id, actor_role):
    with services._connect() as connection:
        if not connection.execute("SELECT 1 FROM encounters WHERE id = %s", (encounter_id,)).fetchone():
            raise AppError("ENCOUNTER_NOT_FOUND", "Encounter was not found", {"encounter_id": str(encounter_id)}, 404)
        cleared = connection.execute(
            "DELETE FROM evidence_items WHERE encounter_id = %s AND code = ANY(%s)",
            (encounter_id, list(CODES)),
        ).rowcount
        connection.execute(
            """INSERT INTO evidence_items
                 (encounter_id, code, state, value, source_type, source_ref, actor_role)
               VALUES (%s, 'PRE_PROCEDURE', 'VERIFIED', '{"requires_imaging":true}'::jsonb, 'DEMO', 'pre-treatment-demo', %s)
               ON CONFLICT (encounter_id, code) DO UPDATE SET
                 state = EXCLUDED.state, value = EXCLUDED.value,
                 source_type = EXCLUDED.source_type, source_ref = EXCLUDED.source_ref,
                 actor_role = EXCLUDED.actor_role, updated_at = now()""",
            (encounter_id, actor_role),
        )
        connection.execute(
            """INSERT INTO audit_events
                 (actor_role, action, object_type, object_id, encounter_id, metadata)
               VALUES (%s, 'PRE_TREATMENT_DEMO_RESET', 'encounter', %s, %s, %s::jsonb)""",
            (actor_role, encounter_id, encounter_id, json.dumps({"cleared_checks": cleared, "requires_imaging": True})),
        )
        return cleared


@router.get("/{encounter_id}/pre-treatment")
def get_checklist(encounter_id: str, _role=Depends(dependencies.require_demo_role)):
    _require_reader(_role)
    _require_encounter(encounter_id)
    evidence = {row["code"]: row for row in _read_evidence(encounter_id)}
    procedure = evidence.get("PRE_PROCEDURE")
    requires_imaging = procedure["value"].get("requires_imaging") if procedure and procedure["state"] == "VERIFIED" else None
    return {"encounter_id": encounter_id, "items": [
        {
            "code": code,
            "applicable": code != "PRE_IMAGING" or requires_imaging is not False,
            "suggested_obligation_state": "NOT_APPLICABLE" if code == "PRE_IMAGING" and requires_imaging is False else None,
            "evidence": evidence.get(code),
            "ai_review": AI_REVIEWS[code],
        }
        for code in CODES
    ], "audit": _read_audit(encounter_id)}


@router.post("/{encounter_id}/pre-treatment/demo-reset")
def reset_demo(encounter_id: str, role=Depends(dependencies.require_demo_role)):
    if role != Role.QA:
        raise AppError("PRE_TREATMENT_RESET_FORBIDDEN", "Only QA can reset the demo scenario", {}, 403)
    _reset_demo_data(encounter_id, role.value)
    return get_checklist(encounter_id, role)


@router.put("/{encounter_id}/pre-treatment/{code}")
def put_attestation(encounter_id: str, code: str, body: Attestation, role=Depends(dependencies.require_demo_role)):
    if code not in CODES:
        raise AppError("PRE_TREATMENT_CODE_INVALID", "Unknown pre-treatment checklist code", {"code": code}, 404)
    if role not in STAFF_ROLES:
        raise AppError("PRE_TREATMENT_ROLE_FORBIDDEN", "Only clinical staff can attest pre-treatment checks", {}, 403)
    if body.performed_at.tzinfo is None or body.performed_at.utcoffset() is None:
        raise AppError("PERFORMED_AT_TIMEZONE_REQUIRED", "performed_at must include a timezone", {}, 422)
    _require_encounter(encounter_id)

    performed_at = body.performed_at.astimezone(timezone.utc).isoformat()
    value = {**body.value, "performed_at": performed_at}
    if "reviewed_source_refs" in body.value:
        refs = body.value["reviewed_source_refs"]
        allowed_refs = {citation["ref"] for citation in AI_REVIEWS[code]["citations"]}
        if not isinstance(refs, list) or any(not isinstance(ref, str) or ref not in allowed_refs for ref in refs):
            raise AppError("PRE_TREATMENT_SOURCE_REF_INVALID", "reviewed_source_refs must use cited fixture references", {"code": code}, 422)
        value["reviewed_source_refs"] = list(dict.fromkeys(refs))
    if code == "PRE_IMAGING" and _requires_imaging(encounter_id) is False:
        value = {"not_applicable": True, "performed_at": performed_at}
    evidence = services.upsert_evidence(encounter_id, code, "VERIFIED", value, "FORM", "pre-treatment", role.value)
    services.append_audit(role.value, "PRE_TREATMENT_ATTESTED", "evidence", evidence["id"], encounter_id, {"code": code, "performed_at": performed_at})
    return evidence
