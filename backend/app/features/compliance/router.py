from uuid import UUID

from fastapi import APIRouter, Depends, Query

from ...core.contracts import Role
from ...core.errors import AppError
from ...core.services import _connect
from ...dependencies import require_demo_role
from .evaluator import POLICY_VERSION, derive_context, desired_task_status, evaluate, task_key


router = APIRouter(prefix="/api/v1", tags=["compliance"])


def _require_staff(role=Depends(require_demo_role)):
    if role not in {Role.FRONT_DESK, Role.ASSISTANT, Role.DENTIST, Role.QA}:
        raise AppError("ROLE_FORBIDDEN", "Staff role is required", status_code=403)
    return role


def _require_auditor(role=Depends(require_demo_role)):
    if role not in {Role.DENTIST, Role.QA}:
        raise AppError("ROLE_FORBIDDEN", "Dentist or QA role is required", status_code=403)
    return role


def _evidence(connection, encounter_id):
    rows = connection.execute(
        "SELECT code, state, value FROM evidence_items WHERE encounter_id = %s",
        (encounter_id,),
    ).fetchall()
    return {row["code"]: dict(row) for row in rows}


def _require_encounter(connection, encounter_id):
    if not connection.execute("SELECT 1 FROM encounters WHERE id = %s", (encounter_id,)).fetchone():
        raise AppError("ENCOUNTER_NOT_FOUND", "Encounter was not found", {"encounter_id": str(encounter_id)}, 404)


@router.post("/encounters/{encounter_id}/evaluate")
def evaluate_encounter(encounter_id: UUID, role=Depends(_require_staff)):
    with _connect() as connection:
        _require_encounter(connection, encounter_id)
        evidence = _evidence(connection, encounter_id)
        checks = evaluate(evidence, derive_context(evidence))
        for check in checks:
            connection.execute(
                """INSERT INTO obligation_checks (encounter_id, code, state, policy_version)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (encounter_id, code, policy_version) DO UPDATE
                   SET state = EXCLUDED.state, updated_at = now()""",
                (encounter_id, check["code"], check["state"], POLICY_VERSION),
            )
            key = task_key(encounter_id, check["code"])
            if desired_task_status(check["state"]) == "OPEN":
                connection.execute(
                    """INSERT INTO tasks
                         (encounter_id, obligation_code, task_type, owner_role, idempotency_key, status)
                       VALUES (%s, %s, 'REVIEW', %s, %s, 'OPEN')
                       ON CONFLICT (idempotency_key) DO UPDATE
                       SET encounter_id = EXCLUDED.encounter_id,
                           obligation_code = EXCLUDED.obligation_code,
                           owner_role = EXCLUDED.owner_role,
                           status = 'OPEN'""",
                    (encounter_id, check["code"], check["owner_role"], key),
                )
            else:
                connection.execute(
                    """UPDATE tasks SET status = 'CANCELLED'
                       WHERE idempotency_key = %s AND status IN ('OPEN', 'ACKNOWLEDGED')""",
                    (key,),
                )
        connection.execute(
            """INSERT INTO audit_events
                 (actor_role, action, object_type, object_id, encounter_id, metadata)
               VALUES (%s, 'ENCOUNTER_EVALUATED', 'encounter', %s, %s, %s::jsonb)""",
            (role.value, encounter_id, encounter_id, '{"policy_version":"dental-policy.v1"}'),
        )
    return {"encounter_id": encounter_id, "policy_version": POLICY_VERSION, "checks": checks}


@router.get("/encounters/{encounter_id}/readiness")
def readiness(encounter_id: UUID, _role=Depends(_require_staff)):
    with _connect() as connection:
        _require_encounter(connection, encounter_id)
        checks = connection.execute(
            "SELECT code, state, policy_version, updated_at FROM obligation_checks WHERE encounter_id = %s ORDER BY code",
            (encounter_id,),
        ).fetchall()
        tasks = connection.execute(
            "SELECT id, obligation_code, owner_role, status, due_at FROM tasks WHERE encounter_id = %s ORDER BY obligation_code",
            (encounter_id,),
        ).fetchall()
    return {"encounter_id": encounter_id, "checks": [dict(row) for row in checks], "tasks": [dict(row) for row in tasks]}


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
