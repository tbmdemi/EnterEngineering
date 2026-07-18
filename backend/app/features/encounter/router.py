from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.core.contracts import EncounterStage
from backend.app.core.contracts import Role
from backend.app.core.errors import AppError
from backend.app.dependencies import require_demo_role

from .service import advance_stage, get_encounter


router = APIRouter(prefix="/api/v1/encounters", tags=["encounter"])
STAGE_WRITERS = {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST}
STAFF_READERS = {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST, Role.QA}


class StageChange(BaseModel):
    stage: EncounterStage
    version: int


@router.get("/{encounter_id}")
def encounter(encounter_id: UUID, _role=Depends(require_demo_role)):
    if _role not in STAFF_READERS:
        raise AppError("ROLE_FORBIDDEN", "Staff role is required", {"role": _role.value}, 403)
    return get_encounter(encounter_id)


@router.post("/{encounter_id}/stage")
def change_stage(encounter_id: UUID, change: StageChange, _role=Depends(require_demo_role)):
    if _role not in STAGE_WRITERS:
        raise AppError("ROLE_FORBIDDEN", "Role cannot change encounter stage", {"role": _role.value}, 403)
    return advance_stage(encounter_id, change.stage, change.version)
