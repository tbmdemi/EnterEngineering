from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ...core.contracts import Role
from ...core.errors import AppError
from ...core.services import _connect, require_encounter_in
from ...dependencies import require_demo_role
from .evaluator import POLICY_VERSION, active_codes_for_stage
from .service import blockers, current_assessment, reconcile_assessment


router = APIRouter(prefix="/api/v1", tags=["compliance"])


def _require_staff(role=Depends(require_demo_role)):
    if role not in {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST, Role.QA}:
        raise AppError("ROLE_FORBIDDEN", "Staff role is required", status_code=403)
    return role


def _require_auditor(role=Depends(require_demo_role)):
    if role not in {Role.DENTIST, Role.QA}:
        raise AppError("ROLE_FORBIDDEN", "Dentist or QA role is required", status_code=403)
    return role


def _require_encounter(connection, encounter_id):
    require_encounter_in(connection, encounter_id)


def _encounter_stage(connection, encounter_id):
    row = connection.execute("SELECT stage FROM encounters WHERE id = %s", (encounter_id,)).fetchone()
    if not row:
        require_encounter_in(connection, encounter_id)
    return row["stage"]


@router.post("/encounters/{encounter_id}/evaluate")
def evaluate_encounter(encounter_id: UUID, role=Depends(_require_staff)):
    with _connect() as connection:
        stage = _encounter_stage(connection, encounter_id)
        if stage == "CLOSED":
            raise AppError("ENCOUNTER_CLOSED", "Closed encounters are read-only", {"encounter_id": str(encounter_id)}, 409)
        active_codes = active_codes_for_stage(stage)
        checks = reconcile_assessment(connection, encounter_id, role, active_codes)
        tasks = connection.execute(
            """SELECT id, obligation_code, owner_role, status, due_at
               FROM tasks WHERE encounter_id = %s AND obligation_code = ANY(%s)
               ORDER BY obligation_code, id""",
            (encounter_id, list(active_codes)),
        ).fetchall() if active_codes else []
    return {
        "encounter_id": encounter_id,
        "stage": stage,
        "policy_version": POLICY_VERSION,
        "checks": checks,
        "tasks": [dict(row) for row in tasks],
    }


@router.get("/encounters/{encounter_id}/readiness")
def readiness(encounter_id: UUID, _role=Depends(_require_staff)):
    with _connect() as connection:
        _require_encounter(connection, encounter_id)
        checks = current_assessment(connection, encounter_id)
        tasks = connection.execute(
            "SELECT id, obligation_code, owner_role, status, due_at FROM tasks WHERE encounter_id = %s ORDER BY obligation_code",
            (encounter_id,),
        ).fetchall()
    missing = blockers(checks)
    return {
        "encounter_id": encounter_id,
        "policy_version": POLICY_VERSION,
        "ready_to_close": not missing,
        "blockers": missing,
        "checks": checks,
        "tasks": [dict(row) for row in tasks],
    }


@router.get("/audit-events")
def audit_events(encounter_id: UUID = Query(...), _role=Depends(_require_auditor)):
    with _connect() as connection:
        _require_encounter(connection, encounter_id)
        rows = connection.execute(
            """SELECT actor_role, action, object_type, object_id, correlation_id, metadata, created_at
               FROM audit_events WHERE encounter_id = %s ORDER BY created_at""",
            (encounter_id,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.get("/dashboard")
def dashboard(_role=Depends(_require_auditor)):
    with _connect() as connection:
        rows = connection.execute(
            """SELECT split_part(code, '_', 1) AS pain_point, state, count(*) AS count
               FROM obligation_checks
               GROUP BY split_part(code, '_', 1), state
               ORDER BY pain_point, state"""
        ).fetchall()
    return {"items": [dict(row) for row in rows]}
