from datetime import datetime
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...core.contracts import EvidenceState, Role, TaskStatus
from ...core.errors import AppError
from ...core.services import (
    _connect,
    append_audit,
    append_audit_in,
    ensure_task,
    require_encounter,
    require_encounter_in,
    upsert_evidence,
    upsert_evidence_in,
)
from ...dependencies import require_demo_role


router = APIRouter(tags=["coordination"])
WORKLIST_ROLES = {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST}
STAFF_ROLES = WORKLIST_ROLES | {Role.QA}


class TaskRequest(BaseModel):
    encounter_id: UUID
    obligation_code: str
    task_type: Literal["HANDOFF", "REFERRAL"]
    owner_role: Optional[Role] = None
    due_at: Optional[datetime] = None


class ResolveScheduleRequest(BaseModel):
    appointment_id: UUID


def _staff(role):
    if role not in STAFF_ROLES:
        raise AppError("ROLE_FORBIDDEN", "Staff role is required", status_code=403)


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
    if not anchor or anchor["status"] == "CANCELLED":
        return []
    return [
        {
            "appointment_id": str(anchor["id"]),
            "conflicts_with": str(row["id"]),
            "chair": anchor["chair"],
            "starts_at": row["starts_at"].isoformat(),
            "ends_at": row["ends_at"].isoformat(),
        }
        for row in appointments if row["status"] != "CANCELLED"
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
            WHERE a.id = anchor.id OR (a.status <> 'CANCELLED' AND a.starts_at < anchor.ends_at AND a.ends_at > anchor.starts_at)
            ORDER BY is_anchor DESC, a.starts_at, a.id
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
        require_encounter(request.encounter_id)
        task = ensure_task(
            request.encounter_id, request.obligation_code, request.task_type,
            owner.value, request.due_at, idempotency_key,
        )
        if request.task_type == "REFERRAL":
            upsert_evidence(
                request.encounter_id, "COORD_REFERRAL_OWNER", EvidenceState.VERIFIED.value,
                {"owner_role": owner.value}, "TASK", str(task["id"]), role.value,
            )
        append_audit(
            role.value, "TASK_CREATED", "task", task["id"], request.encounter_id,
            {"task_type": request.task_type, "owner_role": owner.value},
        )
    return task


@router.post("/api/v1/tasks/{task_id}/acknowledge")
def acknowledge(task_id: UUID, role=Depends(require_demo_role)):
    with _connect() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id = %s FOR UPDATE", (task_id,)).fetchone()
        if not row:
            raise AppError("TASK_NOT_FOUND", "Task was not found", status_code=404)
        task = dict(row)
        authorize_task_mutation(task, role)
        if task["task_type"] != "HANDOFF":
            raise AppError("TASK_ACKNOWLEDGMENT_NOT_REQUIRED", "Only handoff tasks can be acknowledged", status_code=409)
        if task["status"] == TaskStatus.ACKNOWLEDGED.value:
            return task
        if task["status"] == TaskStatus.COMPLETED.value:
            raise AppError("TASK_ALREADY_COMPLETED", "Completed task cannot be acknowledged", status_code=409)
        if task["status"] == TaskStatus.CANCELLED.value:
            raise AppError("TASK_CANCELLED", "Cancelled task cannot be acknowledged", status_code=409)
        updated = dict(connection.execute("UPDATE tasks SET status = 'ACKNOWLEDGED' WHERE id = %s RETURNING *", (task_id,)).fetchone())
        upsert_evidence(
            task["encounter_id"], "COORD_HANDOFF_ACK", EvidenceState.VERIFIED.value,
            {"task_id": str(task_id), "acknowledged_by": role.value}, "TASK", str(task_id), role.value,
        )
        append_audit(role.value, "TASK_ACKNOWLEDGED", "task", task_id, task["encounter_id"], {})
    return updated


@router.post("/api/v1/tasks/{task_id}/complete")
def complete(task_id: UUID, role=Depends(require_demo_role)):
    with _connect() as connection:
        row = connection.execute("SELECT * FROM tasks WHERE id = %s FOR UPDATE", (task_id,)).fetchone()
        if not row:
            raise AppError("TASK_NOT_FOUND", "Task was not found", status_code=404)
        task = dict(row)
        authorize_task_mutation(task, role)
        if task["status"] == TaskStatus.COMPLETED.value:
            return task
        if task["status"] == TaskStatus.CANCELLED.value:
            raise AppError("TASK_CANCELLED", "Cancelled task cannot be completed", status_code=409)
        validate_completion(task)
        updated = dict(connection.execute("UPDATE tasks SET status = 'COMPLETED' WHERE id = %s RETURNING *", (task_id,)).fetchone())
        if task["task_type"] == "REFERRAL":
            upsert_evidence(
                task["encounter_id"], "COORD_REFERRAL_OWNER", EvidenceState.VERIFIED.value,
                {"owner_role": task["owner_role"], "task_id": str(task_id)}, "TASK", str(task_id), role.value,
            )
        append_audit(role.value, "TASK_COMPLETED", "task", task_id, task["encounter_id"], {})
    return updated


@router.post("/api/v1/encounters/{encounter_id}/coordination/evaluate")
def evaluate_coordination(encounter_id: UUID, role=Depends(require_demo_role)):
    _staff(role)
    with _connect() as connection:
        require_encounter(encounter_id)
        conflicts = find_conflicts(load_appointments(encounter_id))
        upsert_evidence(
            encounter_id, "COORD_SCHEDULE_CLEAR", EvidenceState.VERIFIED.value,
            {"clear": not conflicts, "conflicts": conflicts}, "SCHEDULE", None, role.value,
        )
        task = None
        if conflicts:
            task = ensure_task(
                encounter_id, "COORD_SCHEDULE_CLEAR", "REVIEW_SCHEDULE_CONFLICT",
                Role.FRONT_DESK.value, None, f"coord:{encounter_id}:schedule-conflict",
            )
        else:
            connection.execute(
                """UPDATE tasks SET status = 'CANCELLED'
                   WHERE idempotency_key = %s AND status IN ('OPEN', 'ACKNOWLEDGED')""",
                (f"coord:{encounter_id}:schedule-conflict",),
            )
        append_audit(
            role.value, "COORDINATION_EVALUATED", "encounter", encounter_id, encounter_id,
            {"conflict_count": len(conflicts)},
        )
    return {"schedule_clear": not conflicts, "conflicts": conflicts, "task": task}


@router.post("/api/v1/encounters/{encounter_id}/coordination/resolve-schedule")
def resolve_schedule_conflict(encounter_id: UUID, request: ResolveScheduleRequest, role=Depends(require_demo_role)):
    if role != Role.FRONT_DESK:
        raise AppError("ROLE_FORBIDDEN", "Only front desk can resolve schedule conflicts", status_code=403)
    with _connect() as connection:
        require_encounter_in(connection, encounter_id)
        appointments = _load_appointments_in(connection, encounter_id)
        conflict_ids = {str(item["conflicts_with"]) for item in find_conflicts(appointments)}
        if str(request.appointment_id) not in conflict_ids:
            raise AppError(
                "SCHEDULE_CONFLICT_NOT_FOUND",
                "Appointment is not an active conflict for this encounter",
                {"appointment_id": str(request.appointment_id)},
                409,
            )
        connection.execute(
            "UPDATE appointments SET status = 'CANCELLED' WHERE id = %s",
            (request.appointment_id,),
        )
        remaining = find_conflicts(_load_appointments_in(connection, encounter_id))
        upsert_evidence_in(
            connection, encounter_id, "COORD_SCHEDULE_CLEAR", EvidenceState.VERIFIED.value,
            {"clear": not remaining, "conflicts": remaining}, "SCHEDULE", None, role.value,
        )
        if not remaining:
            connection.execute(
                """UPDATE tasks SET status = 'CANCELLED'
                   WHERE idempotency_key = %s AND status IN ('OPEN', 'ACKNOWLEDGED')""",
                (f"coord:{encounter_id}:schedule-conflict",),
            )
        append_audit_in(
            connection, role.value, "SCHEDULE_CONFLICT_RESOLVED", "appointment", request.appointment_id,
            encounter_id, {"remaining_conflicts": len(remaining)},
        )
    return {"schedule_clear": not remaining, "conflicts": remaining}
