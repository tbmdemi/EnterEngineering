from datetime import datetime
from enum import Enum
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator

from ...core.contracts import EvidenceState, Role, TaskStatus
from ...core.errors import AppError
from ...core.services import (
    _connect,
    append_audit_in,
    ensure_task_in,
    upsert_evidence_in,
)
from ...dependencies import require_demo_role


router = APIRouter(tags=["coordination"])
WORKLIST_ROLES = {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST}
STAFF_ROLES = WORKLIST_ROLES | {Role.QA}
ACTIVE_APPOINTMENT_STATUSES = {"PENDING", "BOOKED", "ARRIVED", "CHECKED_IN"}
CANCELLABLE_APPOINTMENT_STATUSES = {"PENDING", "BOOKED", "ARRIVED"}
POST_TREATMENT_FOLLOW_UP_TASK_TYPE = "PATIENT_FOLLOW_UP"
POST_TREATMENT_FOLLOW_UP_OBLIGATION = "POST_COMPLICATION_MONITORING"


class TaskRequest(BaseModel):
    encounter_id: UUID
    obligation_code: str
    task_type: Literal["HANDOFF", "REFERRAL"]
    owner_role: Optional[Role] = None
    due_at: Optional[datetime] = None


class ScheduleResolutionReason(str, Enum):
    DUPLICATE_BOOKING = "DUPLICATE_BOOKING"
    PATIENT_REQUESTED_CANCELLATION = "PATIENT_REQUESTED_CANCELLATION"
    REBOOKED_TO_ANOTHER_SLOT = "REBOOKED_TO_ANOTHER_SLOT"
    CREATED_IN_ERROR = "CREATED_IN_ERROR"


class ResolveScheduleRequest(BaseModel):
    appointment_id: UUID
    expected_status: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z][A-Z0-9_]*$")
    reason: ScheduleResolutionReason

    @field_validator("expected_status", mode="before")
    @classmethod
    def normalize_expected_status(cls, value):
        return value.strip().upper() if isinstance(value, str) else value


def _staff(role):
    if role not in STAFF_ROLES:
        raise AppError("ROLE_FORBIDDEN", "Staff role is required", status_code=403)


def is_released_follow_up_task(task):
    """Identify the one operational task that remains actionable after close."""
    return bool(task) and (
        task.get("task_type") == POST_TREATMENT_FOLLOW_UP_TASK_TYPE
        and task.get("obligation_code") == POST_TREATMENT_FOLLOW_UP_OBLIGATION
        and task.get("idempotency_key") == f"post-complication:{task.get('encounter_id')}"
    )


def require_mutable_encounter_in(connection, encounter_id, closed_task=None):
    """Lock the encounter so it cannot close during a coordination mutation."""
    row = connection.execute(
        "SELECT id, stage FROM encounters WHERE id = %s FOR UPDATE",
        (encounter_id,),
    ).fetchone()
    if not row:
        raise AppError(
            "ENCOUNTER_NOT_FOUND",
            "Encounter was not found",
            {"encounter_id": str(encounter_id)},
            404,
        )
    encounter = dict(row)
    if encounter["stage"] == "CLOSED" and not is_released_follow_up_task(closed_task):
        raise AppError(
            "ENCOUNTER_CLOSED",
            "Closed encounters cannot be changed",
            {"encounter_id": str(encounter_id)},
            409,
        )
    return encounter


def lock_task_for_mutation_in(connection, task_id):
    """Lock encounter before task to match every coordination write lock order."""
    reference = connection.execute(
        """SELECT encounter_id, obligation_code, task_type, idempotency_key
           FROM tasks WHERE id = %s""",
        (task_id,),
    ).fetchone()
    if not reference:
        raise AppError("TASK_NOT_FOUND", "Task was not found", status_code=404)
    encounter = require_mutable_encounter_in(
        connection,
        reference["encounter_id"],
        closed_task=dict(reference),
    )
    row = connection.execute(
        "SELECT * FROM tasks WHERE id = %s FOR UPDATE",
        (task_id,),
    ).fetchone()
    if not row:
        raise AppError("TASK_NOT_FOUND", "Task was not found", status_code=404)
    task = dict(row)
    # Re-check the locked row: the unlocked reference is used only to preserve
    # the global encounter-before-task lock order.
    if encounter and encounter["stage"] == "CLOSED" and not is_released_follow_up_task(task):
        raise AppError(
            "ENCOUNTER_CLOSED",
            "Closed encounters cannot be changed",
            {"encounter_id": str(task["encounter_id"])},
            409,
        )
    return task


def authorize_task_mutation(task, role):
    _staff(role)
    if task["owner_role"] != role.value:
        raise AppError("TASK_OWNER_REQUIRED", "Only the task owner can update it", status_code=403)


def validate_completion(task):
    if task["task_type"] == "HANDOFF" and task["status"] != TaskStatus.ACKNOWLEDGED.value:
        raise AppError("ACKNOWLEDGMENT_REQUIRED", "Handoff must be acknowledged before completion", status_code=409)


def validate_task_request(task_type, owner_role):
    if task_type == "REFERRAL" and owner_role is None:
        raise AppError("REFERRAL_OWNER_REQUIRED", "Referral requires an owner", status_code=422)
    if owner_role is not None and owner_role not in WORKLIST_ROLES:
        code = "REFERRAL_OWNER_INVALID" if task_type == "REFERRAL" else "TASK_OWNER_INVALID"
        raise AppError(code, "Task owner must have a coordination worklist", status_code=422)


def find_conflicts(appointments):
    anchor = next((row for row in appointments if row.get("is_anchor")), appointments[0] if appointments else None)
    if not anchor or anchor["status"] not in ACTIVE_APPOINTMENT_STATUSES:
        return []
    return [
        {
            "appointment_id": str(anchor["id"]),
            "conflicts_with": str(row["id"]),
            "appointment_status": row["status"],
            "chair": anchor["chair"],
            "starts_at": row["starts_at"].isoformat(),
            "ends_at": row["ends_at"].isoformat(),
        }
        for row in appointments if row["status"] in ACTIVE_APPOINTMENT_STATUSES
        and row["id"] != anchor["id"] and row["chair"] == anchor["chair"]
        and anchor["starts_at"] < row["ends_at"] and anchor["ends_at"] > row["starts_at"]
    ]


def _load_appointments_in(connection, encounter_id):
    return [dict(row) for row in connection.execute("""
            WITH anchor AS (
              SELECT a.* FROM appointments a
              JOIN encounters e ON e.appointment_id = a.id
              WHERE e.id = %s
            )
            SELECT a.id, a.chair, a.starts_at, a.ends_at, a.status, (a.id = anchor.id) AS is_anchor
            FROM anchor JOIN appointments a ON a.chair = anchor.chair
            WHERE a.id = anchor.id OR (
              a.status IN ('PENDING', 'BOOKED', 'ARRIVED', 'CHECKED_IN')
              AND a.starts_at < anchor.ends_at AND a.ends_at > anchor.starts_at
            )
            ORDER BY is_anchor DESC, a.starts_at, a.id
            FOR UPDATE OF a
        """, (encounter_id,)).fetchall()]


def load_appointments(encounter_id):
    with _connect() as connection:
        return _load_appointments_in(connection, encounter_id)


@router.get("/api/v1/tasks")
def worklist(owner_role: Role, role=Depends(require_demo_role)):
    _staff(role)
    if owner_role not in WORKLIST_ROLES:
        raise AppError("WORKLIST_ROLE_INVALID", "Coordination worklists are limited to care team roles", status_code=422)
    if role != Role.QA and role != owner_role:
        raise AppError("WORKLIST_ROLE_FORBIDDEN", "A role can only read its own worklist", status_code=403)
    with _connect() as connection:
        return [dict(row) for row in connection.execute(
            """
            SELECT t.id, t.encounter_id, t.obligation_code, t.task_type, t.owner_role,
                   t.status, t.due_at, t.idempotency_key,
                   a.starts_at AS appointment_starts_at, a.ends_at AS appointment_ends_at, a.chair
            FROM tasks t
            JOIN encounters e ON e.id = t.encounter_id
            LEFT JOIN appointments a ON a.id = e.appointment_id
            WHERE t.owner_role = %s AND t.status IN ('OPEN', 'ACKNOWLEDGED')
            ORDER BY t.due_at NULLS LAST, t.id
            """,
            (owner_role.value,),
        ).fetchall()]


def _task(task_id):
    with _connect() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id = %s", (task_id,)).fetchone()
    if not row:
        raise AppError("TASK_NOT_FOUND", "Task was not found", status_code=404)
    return dict(row)


@router.post("/api/v1/coordination/tasks")
def create_task(request: TaskRequest, role=Depends(require_demo_role)):
    _staff(role)
    validate_task_request(request.task_type, request.owner_role)
    owner = request.owner_role or role
    validate_task_request(request.task_type, owner)
    idempotency_key = f"coord:{request.encounter_id}:{request.task_type.lower()}:{request.obligation_code.lower()}"
    with _connect() as connection:
        require_mutable_encounter_in(connection, request.encounter_id)
        task = ensure_task_in(
            connection,
            request.encounter_id, request.obligation_code, request.task_type,
            owner.value, request.due_at, idempotency_key,
        )
        if request.task_type == "REFERRAL":
            upsert_evidence_in(
                connection,
                request.encounter_id, "COORD_REFERRAL_OWNER", EvidenceState.VERIFIED.value,
                {"owner_role": owner.value}, "TASK", str(task["id"]), role.value,
            )
        append_audit_in(
            connection,
            role.value, "TASK_CREATED", "task", task["id"], request.encounter_id,
            {"task_type": request.task_type, "owner_role": owner.value},
        )
    return task


@router.post("/api/v1/tasks/{task_id}/acknowledge")
def acknowledge(task_id: UUID, role=Depends(require_demo_role)):
    _staff(role)
    with _connect() as connection:
        task = lock_task_for_mutation_in(connection, task_id)
        authorize_task_mutation(task, role)
        follow_up = is_released_follow_up_task(task)
        if task["task_type"] != "HANDOFF" and not follow_up:
            raise AppError(
                "TASK_ACKNOWLEDGMENT_NOT_REQUIRED",
                "Only handoff and released patient follow-up tasks can be acknowledged",
                status_code=409,
            )
        if task["status"] == TaskStatus.ACKNOWLEDGED.value:
            return task
        if task["status"] == TaskStatus.COMPLETED.value:
            raise AppError("TASK_ALREADY_COMPLETED", "Completed task cannot be acknowledged", status_code=409)
        if task["status"] == TaskStatus.CANCELLED.value:
            raise AppError("TASK_CANCELLED", "Cancelled task cannot be acknowledged", status_code=409)
        updated = dict(connection.execute(
            """UPDATE tasks
               SET status = 'ACKNOWLEDGED', acknowledged_at = now(), updated_at = now()
               WHERE id = %s AND status = 'OPEN' RETURNING *""",
            (task_id,),
        ).fetchone())
        if task["task_type"] == "HANDOFF":
            upsert_evidence_in(
                connection,
                task["encounter_id"], "COORD_HANDOFF_ACK", EvidenceState.VERIFIED.value,
                {"task_id": str(task_id), "acknowledged_by": role.value}, "TASK", str(task_id), role.value,
            )
        append_audit_in(
            connection, role.value, "TASK_ACKNOWLEDGED", "task", task_id, task["encounter_id"],
            {"task_type": task["task_type"], "from_status": "OPEN", "to_status": "ACKNOWLEDGED"},
        )
    return updated


@router.post("/api/v1/tasks/{task_id}/complete")
def complete(task_id: UUID, role=Depends(require_demo_role)):
    _staff(role)
    with _connect() as connection:
        task = lock_task_for_mutation_in(connection, task_id)
        authorize_task_mutation(task, role)
        if task["status"] == TaskStatus.COMPLETED.value:
            return task
        if task["status"] == TaskStatus.CANCELLED.value:
            raise AppError("TASK_CANCELLED", "Cancelled task cannot be completed", status_code=409)
        validate_completion(task)
        updated = dict(connection.execute(
            """UPDATE tasks
               SET status = 'COMPLETED', completed_at = now(), updated_at = now()
               WHERE id = %s AND status = %s RETURNING *""",
            (task_id, task["status"]),
        ).fetchone())
        if task["task_type"] == "REFERRAL":
            upsert_evidence_in(
                connection,
                task["encounter_id"], "COORD_REFERRAL_OWNER", EvidenceState.VERIFIED.value,
                {"owner_role": task["owner_role"], "task_id": str(task_id)}, "TASK", str(task_id), role.value,
            )
        append_audit_in(
            connection, role.value, "TASK_COMPLETED", "task", task_id, task["encounter_id"],
            {"task_type": task["task_type"], "from_status": task["status"], "to_status": "COMPLETED"},
        )
    return updated


@router.post("/api/v1/encounters/{encounter_id}/coordination/evaluate")
def evaluate_coordination(encounter_id: UUID, role=Depends(require_demo_role)):
    _staff(role)
    with _connect() as connection:
        require_mutable_encounter_in(connection, encounter_id)
        conflicts = find_conflicts(_load_appointments_in(connection, encounter_id))
        upsert_evidence_in(
            connection,
            encounter_id, "COORD_SCHEDULE_CLEAR", EvidenceState.VERIFIED.value,
            {"clear": not conflicts, "conflicts": conflicts}, "SCHEDULE", None, role.value,
        )
        task = None
        if conflicts:
            task = ensure_task_in(
                connection,
                encounter_id, "COORD_SCHEDULE_CLEAR", "REVIEW_SCHEDULE_CONFLICT",
                Role.FRONT_DESK.value, None, f"coord:{encounter_id}:schedule-conflict",
            )
        else:
            connection.execute(
                """UPDATE tasks SET status = 'CANCELLED', cancelled_at = now(), updated_at = now()
                   WHERE idempotency_key = %s AND status IN ('OPEN', 'ACKNOWLEDGED')""",
                (f"coord:{encounter_id}:schedule-conflict",),
            )
        append_audit_in(
            connection,
            role.value, "COORDINATION_EVALUATED", "encounter", encounter_id, encounter_id,
            {"conflict_count": len(conflicts)},
        )
    return {"schedule_clear": not conflicts, "conflicts": conflicts, "task": task}


@router.post("/api/v1/encounters/{encounter_id}/coordination/resolve-schedule")
def resolve_schedule_conflict(encounter_id: UUID, request: ResolveScheduleRequest, role=Depends(require_demo_role)):
    if role != Role.FRONT_DESK:
        raise AppError("ROLE_FORBIDDEN", "Only front desk can resolve schedule conflicts", status_code=403)
    with _connect() as connection:
        require_mutable_encounter_in(connection, encounter_id)
        appointments = _load_appointments_in(connection, encounter_id)
        conflicts = find_conflicts(appointments)
        conflict = next(
            (item for item in conflicts if item["conflicts_with"] == str(request.appointment_id)),
            None,
        )
        if conflict is None:
            raise AppError(
                "SCHEDULE_CONFLICT_NOT_FOUND",
                "Appointment is not an active conflict for this encounter",
                {"appointment_id": str(request.appointment_id)},
                409,
            )
        if conflict["appointment_status"] != request.expected_status:
            raise AppError(
                "APPOINTMENT_STATE_CONFLICT",
                "Appointment status changed; evaluate the schedule again",
                {
                    "appointment_id": str(request.appointment_id),
                    "expected_status": request.expected_status,
                    "actual_status": conflict["appointment_status"],
                },
                409,
            )
        if conflict["appointment_status"] not in CANCELLABLE_APPOINTMENT_STATUSES:
            raise AppError(
                "APPOINTMENT_NOT_CANCELLABLE",
                "Checked-in or later appointments cannot be cancelled as schedule conflicts",
                {
                    "appointment_id": str(request.appointment_id),
                    "status": conflict["appointment_status"],
                },
                409,
            )
        updated = connection.execute(
            """UPDATE appointments AS target
               SET status = 'CANCELLED', version = target.version + 1
               FROM encounters AS e
               JOIN appointments AS anchor ON anchor.id = e.appointment_id
               WHERE e.id = %s
                 AND target.id = %s
                 AND target.id <> anchor.id
                 AND target.status = %s
                 AND target.status IN ('PENDING', 'BOOKED', 'ARRIVED')
                 AND anchor.status IN ('PENDING', 'BOOKED', 'ARRIVED', 'CHECKED_IN')
                 AND target.chair = anchor.chair
                 AND target.starts_at < anchor.ends_at
                 AND target.ends_at > anchor.starts_at
               RETURNING target.id, target.status""",
            (encounter_id, request.appointment_id, request.expected_status),
        ).fetchone()
        if not updated:
            refreshed = find_conflicts(_load_appointments_in(connection, encounter_id))
            current = next(
                (item for item in refreshed if item["conflicts_with"] == str(request.appointment_id)),
                None,
            )
            if current is None:
                raise AppError(
                    "SCHEDULE_CONFLICT_NOT_FOUND",
                    "Appointment is no longer an active conflict for this encounter",
                    {"appointment_id": str(request.appointment_id)},
                    409,
                )
            raise AppError(
                "APPOINTMENT_STATE_CONFLICT",
                "Appointment status changed; evaluate the schedule again",
                {
                    "appointment_id": str(request.appointment_id),
                    "expected_status": request.expected_status,
                    "actual_status": current["appointment_status"],
                },
                409,
            )
        remaining = find_conflicts(_load_appointments_in(connection, encounter_id))
        upsert_evidence_in(
            connection, encounter_id, "COORD_SCHEDULE_CLEAR", EvidenceState.VERIFIED.value,
            {"clear": not remaining, "conflicts": remaining}, "SCHEDULE", None, role.value,
        )
        if not remaining:
            connection.execute(
                """UPDATE tasks SET status = 'CANCELLED', cancelled_at = now(), updated_at = now()
                   WHERE idempotency_key = %s AND status IN ('OPEN', 'ACKNOWLEDGED')""",
                (f"coord:{encounter_id}:schedule-conflict",),
            )
        append_audit_in(
            connection, role.value, "SCHEDULE_CONFLICT_RESOLVED", "appointment", request.appointment_id,
            encounter_id,
            {
                "reason": request.reason.value,
                "from_status": request.expected_status,
                "to_status": "CANCELLED",
                "remaining_conflicts": len(remaining),
            },
        )
    return {"schedule_clear": not remaining, "conflicts": remaining}
