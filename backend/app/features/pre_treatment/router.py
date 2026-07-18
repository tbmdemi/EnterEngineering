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
        }
        for code in CODES
    ]}


@router.put("/{encounter_id}/pre-treatment/{code}")
def put_attestation(encounter_id: str, code: str, body: Attestation, role=Depends(dependencies.require_demo_role)):
    if code not in CODES:
        raise AppError("PRE_TREATMENT_CODE_INVALID", "Unknown pre-treatment checklist code", {"code": code}, 404)
    if role not in STAFF_ROLES:
        raise AppError("PRE_TREATMENT_ROLE_FORBIDDEN", "Only clinical staff can attest pre-treatment checks", {}, 403)
    if body.performed_at.tzinfo is None or body.performed_at.utcoffset() is None:
        raise AppError("PERFORMED_AT_TIMEZONE_REQUIRED", "performed_at must include a timezone", {}, 422)

    performed_at = body.performed_at.astimezone(timezone.utc).isoformat()
    value = {**body.value, "performed_at": performed_at}
    if code == "PRE_IMAGING" and _requires_imaging(encounter_id) is False:
        value = {"not_applicable": True, "performed_at": performed_at}
    evidence = services.upsert_evidence(encounter_id, code, "VERIFIED", value, "FORM", "pre-treatment", role.value)
    services.append_audit(role.value, "PRE_TREATMENT_ATTESTED", "evidence", evidence["id"], encounter_id, {"code": code, "performed_at": performed_at})
    return evidence
