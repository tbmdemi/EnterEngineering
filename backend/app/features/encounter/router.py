from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...core.contracts import EncounterStage
from ...core.contracts import Role
from ...core.errors import AppError
from ...dependencies import require_demo_role
from ..compliance.service import (
    close_transition_guard,
    post_treatment_transition_guard,
    transition_readiness,
    treatment_transition_guard,
)

from .service import advance_stage, check_in_transition_guard, get_encounter
from .service import get_stage_transitions
from .models import EncounterResponse, StageTransitionResponse


router = APIRouter(prefix="/api/v1/encounters", tags=["encounter"])
STAGE_WRITERS_BY_TARGET = {
    EncounterStage.PRE_TREATMENT: {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST},
    EncounterStage.TREATMENT: {Role.DENTIST},
    EncounterStage.POST_TREATMENT: {Role.DENTIST},
    EncounterStage.CLOSED: {Role.DENTIST},
}
STAFF_READERS = {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST, Role.QA}
TRANSITION_GUARDS = {
    EncounterStage.PRE_TREATMENT: check_in_transition_guard,
    EncounterStage.TREATMENT: treatment_transition_guard,
    EncounterStage.POST_TREATMENT: post_treatment_transition_guard,
    EncounterStage.CLOSED: close_transition_guard,
}


class StageChange(BaseModel):
    stage: EncounterStage
    version: int = Field(ge=1)


def _response(context, role):
    current_index = list(EncounterStage).index(EncounterStage(context["stage"]))
    next_stage = list(EncounterStage)[current_index + 1] if current_index + 1 < len(EncounterStage) else None
    if next_stage == EncounterStage.PRE_TREATMENT:
        checked_in = bool(context.get("appointment") and context["appointment"].get("status") == "CHECKED_IN")
        readiness = {
            "ready": checked_in,
            "target_stage": next_stage,
            "policy_version": "appointment-workflow.v1",
            "blockers": [] if checked_in else [{
                "code": "APPOINTMENT_CHECKED_IN",
                "state": "MISSING",
                "owner_role": Role.FRONT_DESK,
            }],
        }
    elif next_stage is not None:
        readiness = transition_readiness(context["id"], next_stage.value)
    else:
        readiness = None
    allowed_roles = STAGE_WRITERS_BY_TARGET.get(next_stage, set())
    return {
        **context,
        "next_stage": next_stage,
        "can_advance": role in allowed_roles and next_stage is not None and readiness["ready"],
        "readiness": readiness,
    }


@router.get("/{encounter_id}", response_model=EncounterResponse)
def encounter(encounter_id: UUID, _role=Depends(require_demo_role)):
    if _role not in STAFF_READERS:
        raise AppError("ROLE_FORBIDDEN", "Staff role is required", {"role": _role.value}, 403)
    return _response(get_encounter(encounter_id), _role)


@router.get("/{encounter_id}/transitions", response_model=list[StageTransitionResponse])
def transitions(encounter_id: UUID, _role=Depends(require_demo_role)):
    if _role not in STAFF_READERS:
        raise AppError("ROLE_FORBIDDEN", "Staff role is required", {"role": _role.value}, 403)
    return get_stage_transitions(encounter_id)


@router.post("/{encounter_id}/stage", response_model=EncounterResponse)
def change_stage(encounter_id: UUID, change: StageChange, _role=Depends(require_demo_role)):
    guard = TRANSITION_GUARDS.get(change.stage)
    if guard is None:
        raise AppError(
            "INVALID_STAGE_TRANSITION",
            "Encounter can only advance to its next workflow stage",
            {"target_stage": change.stage.value},
            409,
        )
    if _role not in STAGE_WRITERS_BY_TARGET.get(change.stage, set()):
        raise AppError("ROLE_FORBIDDEN", "Role cannot change encounter stage", {"role": _role.value}, 403)
    context = advance_stage(
        encounter_id,
        change.stage,
        change.version,
        _role,
        guard,
    )
    return _response(context, _role)
