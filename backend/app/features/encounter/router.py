from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.app.core.contracts import EncounterStage
from backend.app.dependencies import require_demo_role

from .service import advance_stage, get_encounter


router = APIRouter(prefix="/api/v1/encounters", tags=["encounter"])


class StageChange(BaseModel):
    stage: EncounterStage
    version: int


@router.get("/{encounter_id}")
def encounter(encounter_id: UUID, _role=Depends(require_demo_role)):
    return get_encounter(encounter_id)


@router.post("/{encounter_id}/stage")
def change_stage(encounter_id: UUID, change: StageChange, _role=Depends(require_demo_role)):
    return advance_stage(encounter_id, change.stage, change.version)
