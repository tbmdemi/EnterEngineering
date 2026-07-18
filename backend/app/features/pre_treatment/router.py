import json
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StringConstraints, ValidationError, model_validator

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


class ProcedureDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requires_imaging: StrictBool
    performed_at: datetime


NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveReading = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class _AttestationValue(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    reviewed_source_refs: list[NonEmptyText] | None = None


class MedicalHistoryValue(_AttestationValue):
    summary: NonEmptyText
    reviewed_source_refs: list[NonEmptyText] = Field(min_length=1)


class AllergyValue(_AttestationValue):
    status: Literal["NONE_KNOWN", "PRESENT"]
    allergen: NonEmptyText | None = None

    @model_validator(mode="after")
    def require_present_allergen(self):
        if self.status == "PRESENT" and self.allergen is None:
            raise ValueError("allergen is required when status is PRESENT")
        return self


class VitalsValue(_AttestationValue):
    systolic: PositiveReading
    diastolic: PositiveReading
    pulse: PositiveReading


class SterilizationValue(_AttestationValue):
    confirmed: bool
    cycle_or_tray_id: NonEmptyText

    @model_validator(mode="after")
    def require_confirmation(self):
        if self.confirmed is not True:
            raise ValueError("confirmed must be true")
        return self


class ImagingValue(_AttestationValue):
    reviewed: bool
    imaging_reference: NonEmptyText

    @model_validator(mode="after")
    def require_review(self):
        if self.reviewed is not True:
            raise ValueError("reviewed must be true")
        return self


VALUE_MODELS = {
    "PRE_MEDICAL_HISTORY": MedicalHistoryValue,
    "PRE_ALLERGY": AllergyValue,
    "PRE_VITALS": VitalsValue,
    "PRE_STERILIZATION": SterilizationValue,
    "PRE_IMAGING": ImagingValue,
}


def _validated_value(code, raw_value):
    candidate = dict(raw_value)
    if "reviewed_source_refs" in candidate:
        refs = candidate["reviewed_source_refs"]
        allowed_refs = {citation["ref"] for citation in AI_REVIEWS[code]["citations"]}
        if not isinstance(refs, list) or any(type(ref) is not str or ref not in allowed_refs for ref in refs):
            raise AppError(
                "PRE_TREATMENT_SOURCE_REF_INVALID",
                "reviewed_source_refs must use cited fixture references",
                {"code": code},
                422,
            )
        candidate["reviewed_source_refs"] = list(dict.fromkeys(refs))
    try:
        return VALUE_MODELS[code].model_validate(candidate).model_dump(exclude_none=True)
    except ValidationError as error:
        fields = sorted({".".join(str(part) for part in item["loc"]) or "value" for item in error.errors()})
        raise AppError(
            "PRE_TREATMENT_VALUE_INVALID",
            "Pre-treatment attestation value is invalid",
            {"code": code, "fields": fields},
            422,
        ) from error


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


def _performed_at_utc(value):
    if value.tzinfo is None or value.utcoffset() is None:
        raise AppError("PERFORMED_AT_TIMEZONE_REQUIRED", "performed_at must include a timezone", {}, 422)
    return value.astimezone(timezone.utc).isoformat()


def _lock_mutable_pre_treatment_encounter(connection, encounter_id):
    services.require_encounter_in(connection, encounter_id)
    encounter = connection.execute(
        "SELECT stage FROM encounters WHERE id = %s FOR UPDATE",
        (encounter_id,),
    ).fetchone()
    if encounter["stage"] == "CLOSED":
        raise AppError(
            "ENCOUNTER_CLOSED",
            "Closed encounters cannot be modified",
            {"encounter_id": str(encounter_id), "stage": "CLOSED"},
            409,
        )
    if encounter["stage"] not in {"CHECK_IN", "PRE_TREATMENT"}:
        raise AppError(
            "PRE_TREATMENT_STAGE_INVALID",
            "Pre-treatment data cannot change after treatment has started",
            {"encounter_id": str(encounter_id), "stage": encounter["stage"]},
            409,
        )
    return encounter


def _read_audit(encounter_id):
    with services._connect() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT actor_role, action, metadata, created_at FROM audit_events WHERE encounter_id = %s AND action LIKE 'PRE_TREATMENT_%%' ORDER BY created_at DESC",
            (encounter_id,),
        ).fetchall()]


def _reset_demo_data(encounter_id, actor_role):
    with services._connect() as connection:
        encounter = connection.execute(
            "SELECT stage FROM encounters WHERE id = %s FOR UPDATE",
            (encounter_id,),
        ).fetchone()
        if not encounter:
            raise AppError("ENCOUNTER_NOT_FOUND", "Encounter was not found", {"encounter_id": str(encounter_id)}, 404)
        if encounter["stage"] == "CLOSED":
            raise AppError(
                "ENCOUNTER_CLOSED",
                "Closed encounters cannot be modified",
                {"encounter_id": str(encounter_id), "stage": "CLOSED"},
                409,
            )
        if encounter["stage"] not in {"CHECK_IN", "PRE_TREATMENT"}:
            raise AppError(
                "PRE_TREATMENT_STAGE_INVALID",
                "Pre-treatment data cannot be reset after treatment has started",
                {"encounter_id": str(encounter_id), "stage": encounter["stage"]},
                409,
            )
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
    return {
        "encounter_id": encounter_id,
        "procedure": {
            "requires_imaging": requires_imaging,
            "evidence": procedure,
        },
        "items": [
        {
            "code": code,
            "applicable": code != "PRE_IMAGING" or requires_imaging is not False,
            "suggested_obligation_state": "NOT_APPLICABLE" if code == "PRE_IMAGING" and requires_imaging is False else None,
            "evidence": evidence.get(code),
            "ai_review": AI_REVIEWS[code],
        }
        for code in CODES
        ],
        "audit": _read_audit(encounter_id),
    }


@router.post("/{encounter_id}/pre-treatment/demo-reset")
def reset_demo(encounter_id: str, role=Depends(dependencies.require_demo_role)):
    if role != Role.QA:
        raise AppError("PRE_TREATMENT_RESET_FORBIDDEN", "Only QA can reset the demo scenario", {}, 403)
    _reset_demo_data(encounter_id, role.value)
    return get_checklist(encounter_id, role)


@router.put("/{encounter_id}/pre-treatment/procedure")
def put_procedure_declaration(
    encounter_id: str,
    body: ProcedureDeclaration,
    role=Depends(dependencies.require_demo_role),
):
    if role not in STAFF_ROLES:
        raise AppError(
            "PRE_TREATMENT_ROLE_FORBIDDEN",
            "Only clinical staff can declare procedure imaging requirements",
            {},
            403,
        )
    performed_at = _performed_at_utc(body.performed_at)
    with services._connect() as connection:
        _lock_mutable_pre_treatment_encounter(connection, encounter_id)
        existing = connection.execute(
            """SELECT state, value
               FROM evidence_items
               WHERE encounter_id = %s AND code = 'PRE_PROCEDURE'
               FOR UPDATE""",
            (encounter_id,),
        ).fetchone()
        previous = None
        if existing and existing["state"] == "VERIFIED":
            candidate = existing["value"].get("requires_imaging")
            previous = candidate if candidate is True or candidate is False else None
        if previous is not None and previous is not body.requires_imaging:
            connection.execute(
                "DELETE FROM evidence_items WHERE encounter_id = %s AND code = 'PRE_IMAGING'",
                (encounter_id,),
            )
        evidence = services.upsert_evidence(
            encounter_id,
            "PRE_PROCEDURE",
            "VERIFIED",
            {"requires_imaging": body.requires_imaging, "performed_at": performed_at},
            "FORM",
            "pre-treatment-procedure",
            role.value,
        )
        services.append_audit(
            role.value,
            "PRE_TREATMENT_PROCEDURE_DECLARED",
            "evidence",
            evidence["id"],
            encounter_id,
            {
                "previous_requires_imaging": previous,
                "requires_imaging": body.requires_imaging,
                "performed_at": performed_at,
                "imaging_attestation_invalidated": previous is not None and previous is not body.requires_imaging,
            },
        )
    return evidence


@router.put("/{encounter_id}/pre-treatment/{code}")
def put_attestation(encounter_id: str, code: str, body: Attestation, role=Depends(dependencies.require_demo_role)):
    if code not in CODES:
        raise AppError("PRE_TREATMENT_CODE_INVALID", "Unknown pre-treatment checklist code", {"code": code}, 404)
    if role not in STAFF_ROLES:
        raise AppError("PRE_TREATMENT_ROLE_FORBIDDEN", "Only clinical staff can attest pre-treatment checks", {}, 403)
    performed_at = _performed_at_utc(body.performed_at)
    with services._connect() as connection:
        _lock_mutable_pre_treatment_encounter(connection, encounter_id)
        value = None
        if code == "PRE_IMAGING":
            procedure = connection.execute(
                "SELECT state, value FROM evidence_items WHERE encounter_id = %s AND code = 'PRE_PROCEDURE'",
                (encounter_id,),
            ).fetchone()
            requires_imaging = None
            if procedure and procedure["state"] == "VERIFIED":
                candidate = procedure["value"].get("requires_imaging")
                requires_imaging = candidate if candidate is True or candidate is False else None
            if requires_imaging is False:
                value = {"not_applicable": True, "performed_at": performed_at}
        if value is None:
            value = {**_validated_value(code, body.value), "performed_at": performed_at}
        evidence = services.upsert_evidence(
            encounter_id, code, "VERIFIED", value, "FORM", "pre-treatment", role.value
        )
        services.append_audit(
            role.value,
            "PRE_TREATMENT_ATTESTED",
            "evidence",
            evidence["id"],
            encounter_id,
            {"code": code, "performed_at": performed_at},
        )
    return evidence
