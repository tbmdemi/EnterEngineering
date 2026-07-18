from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...core.contracts import EncounterStage
from ...core.contracts import Role
from ...core.errors import AppError
from ...dependencies import require_demo_role

from .service import advance_stage, get_encounter
from .service import get_stage_transitions
from .models import EncounterResponse, StageTransitionResponse


router = APIRouter(prefix="/api/v1/encounters", tags=["encounter"])
STAGE_WRITERS = {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST}
STAFF_READERS = {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST, Role.QA}


class StageChange(BaseModel):
    stage: EncounterStage
    version: int = Field(ge=1)


def _response(context, role):
    current_index = list(EncounterStage).index(EncounterStage(context["stage"]))
    next_stage = list(EncounterStage)[current_index + 1] if current_index + 1 < len(EncounterStage) else None
    return {
        **context,
        "next_stage": next_stage,
        "can_advance": role in STAGE_WRITERS and next_stage is not None,
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
    if _role not in STAGE_WRITERS:
        raise AppError("ROLE_FORBIDDEN", "Role cannot change encounter stage", {"role": _role.value}, 403)
    return _response(advance_stage(encounter_id, change.stage, change.version, _role), _role)
