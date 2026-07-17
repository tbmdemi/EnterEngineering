from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ...core.contracts import EvidenceState, Role, TaskStatus
from ...core.errors import AppError
from ...core.services import _connect, append_audit, ensure_task, upsert_evidence
from ...dependencies import require_demo_role


router = APIRouter(tags=["coordination"])
STAFF_ROLES = {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST, Role.QA}


class TaskRequest(BaseModel):
    encounter_id: UUID
    obligation_code: str
    task_type: str
    owner_role: Optional[Role] = None
    due_at: Optional[datetime] = None


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
    if task_type == "REFERRAL" and owner_role not in STAFF_ROLES:
        raise AppError("REFERRAL_OWNER_INVALID", "Referral owner must be a staff role", status_code=422)


def find_conflicts(appointments):
    active = [row for row in appointments if row["status"] != "CANCELLED"]
    anchor = next((row for row in active if row.get("is_anchor")), active[0] if active else None)
    if not anchor:
        return []
    return [
        {"appointment_id": anchor["id"], "conflicts_with": row["id"], "chair": anchor["chair"]}
        for row in active if row["id"] != anchor["id"] and row["chair"] == anchor["chair"]
        and anchor["starts_at"] < row["ends_at"] and anchor["ends_at"] > row["starts_at"]
    ]


def load_appointments(encounter_id):
    with _connect() as connection:
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


@router.get("/api/v1/tasks")
def worklist(owner_role: Role, role=Depends(require_demo_role)):
    _staff(role)
    if role != Role.QA and role != owner_role:
        raise AppError("WORKLIST_ROLE_FORBIDDEN", "A role can only read its own worklist", status_code=403)
    with _connect() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT id, encounter_id, obligation_code, task_type, owner_role, status, due_at, idempotency_key FROM tasks WHERE owner_role = %s ORDER BY due_at NULLS LAST, id",
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
    idempotency_key = f"coord:{request.encounter_id}:{request.task_type.lower()}:{request.obligation_code.lower()}"
    task = ensure_task(request.encounter_id, request.obligation_code, request.task_type, owner.value, request.due_at, idempotency_key)
    if request.task_type == "REFERRAL":
        upsert_evidence(request.encounter_id, "COORD_REFERRAL_OWNER", EvidenceState.VERIFIED.value, {"owner_role": owner.value}, "TASK", str(task["id"]), role.value)
    append_audit(role.value, "TASK_CREATED", "task", task["id"], request.encounter_id, {"task_type": request.task_type, "owner_role": owner.value})
    return task


@router.post("/api/v1/tasks/{task_id}/acknowledge")
def acknowledge(task_id: UUID, role=Depends(require_demo_role)):
    task = _task(task_id)
    authorize_task_mutation(task, role)
    if task["status"] == TaskStatus.COMPLETED.value:
        raise AppError("TASK_ALREADY_COMPLETED", "Completed task cannot be acknowledged", status_code=409)
    with _connect() as connection:
        updated = dict(connection.execute("UPDATE tasks SET status = 'ACKNOWLEDGED' WHERE id = %s RETURNING *", (task_id,)).fetchone())
    if task["task_type"] == "HANDOFF":
        upsert_evidence(task["encounter_id"], "COORD_HANDOFF_ACK", EvidenceState.VERIFIED.value, {"task_id": task_id, "acknowledged_by": role.value}, "TASK", task_id, role.value)
    append_audit(role.value, "TASK_ACKNOWLEDGED", "task", task_id, task["encounter_id"], {})
    return updated


@router.post("/api/v1/tasks/{task_id}/complete")
def complete(task_id: UUID, role=Depends(require_demo_role)):
    task = _task(task_id)
    authorize_task_mutation(task, role)
    validate_completion(task)
    with _connect() as connection:
        updated = dict(connection.execute("UPDATE tasks SET status = 'COMPLETED' WHERE id = %s RETURNING *", (task_id,)).fetchone())
    append_audit(role.value, "TASK_COMPLETED", "task", task_id, task["encounter_id"], {})
    return updated


@router.post("/api/v1/encounters/{encounter_id}/coordination/evaluate")
def evaluate_coordination(encounter_id: UUID, role=Depends(require_demo_role)):
    _staff(role)
    conflicts = find_conflicts(load_appointments(encounter_id))
    upsert_evidence(encounter_id, "COORD_SCHEDULE_CLEAR", EvidenceState.VERIFIED.value, {"clear": not conflicts, "conflicts": conflicts}, "SCHEDULE", None, role.value)
    task = None
    if conflicts:
        task = ensure_task(encounter_id, "COORD_SCHEDULE_CLEAR", "RESOLVE_SCHEDULE_CONFLICT", Role.FRONT_DESK.value, None, f"coord:{encounter_id}:schedule-conflict")
    append_audit(role.value, "COORDINATION_EVALUATED", "encounter", encounter_id, encounter_id, {"conflict_count": len(conflicts)})
    return {"schedule_clear": not conflicts, "conflicts": conflicts, "task": task}
