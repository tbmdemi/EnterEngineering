from enum import Enum


class Role(str, Enum):
    FRONT_DESK = "FRONT_DESK"
    ASSISTANT = "ASSISTANT"
    DENTIST = "DENTIST"
    PATIENT = "PATIENT"
    QA = "QA"


class EncounterStage(str, Enum):
    CHECK_IN = "CHECK_IN"
    PRE_TREATMENT = "PRE_TREATMENT"
    TREATMENT = "TREATMENT"
    POST_TREATMENT = "POST_TREATMENT"
    CLOSED = "CLOSED"


class EvidenceState(str, Enum):
    DRAFT = "DRAFT"
    VERIFIED = "VERIFIED"


class ObligationState(str, Enum):
    PENDING = "PENDING"
    MISSING = "MISSING"
    UNVERIFIED = "UNVERIFIED"
    SATISFIED = "SATISFIED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class TaskStatus(str, Enum):
    OPEN = "OPEN"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
