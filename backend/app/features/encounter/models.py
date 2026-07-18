from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from ...core.contracts import EncounterStage, Role


class PatientSummary(BaseModel):
    id: UUID
    mrn: str
    full_name: str
    date_of_birth: date


class AppointmentSummary(BaseModel):
    id: UUID
    starts_at: datetime
    ends_at: datetime
    chair: str
    status: str


class ComplianceBlocker(BaseModel):
    code: str
    state: str
    owner_role: Role


class TransitionReadiness(BaseModel):
    ready: bool
    policy_version: str
    blockers: list[ComplianceBlocker]


class EncounterResponse(BaseModel):
    id: UUID
    stage: EncounterStage
    version: int = Field(ge=1)
    patient: PatientSummary
    appointment: AppointmentSummary | None
    next_stage: EncounterStage | None
    can_advance: bool
    readiness: TransitionReadiness | None = None


class StageTransitionResponse(BaseModel):
    id: UUID
    from_stage: EncounterStage
    to_stage: EncounterStage
    actor_role: Role
    from_version: int = Field(ge=1)
    to_version: int = Field(ge=2)
    occurred_at: datetime
