from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ...core.services import _connect, append_audit, ensure_task
from ...dependencies import require_demo_role
from .evaluator import POLICY_VERSION, evaluate, task_key


router = APIRouter(prefix="/api/v1", tags=["compliance"])


class EvaluationRequest(BaseModel):
    medication_prescribed: bool = False
    imaging_required: bool = False


def _evidence(encounter_id):
    with _connect() as connection:
        rows = connection.execute(
            "SELECT code, state, value FROM evidence_items WHERE encounter_id = %s",
            (encounter_id,),
        ).fetchall()
    return {row["code"]: dict(row) for row in rows}


@router.post("/encounters/{encounter_id}/evaluate")
def evaluate_encounter(encounter_id: UUID, request: EvaluationRequest, role=Depends(require_demo_role)):
    checks = evaluate(_evidence(encounter_id), request.model_dump())
    with _connect() as connection:
        for check in checks:
            connection.execute(
                """INSERT INTO obligation_checks (encounter_id, code, state, policy_version)
                   VALUES (%s, %s, %s, %s)
                   ON CONFLICT (encounter_id, code, policy_version) DO UPDATE
                   SET state = EXCLUDED.state, updated_at = now()""",
                (encounter_id, check["code"], check["state"], POLICY_VERSION),
            )
    for check in checks:
        if check["state"] in {"MISSING", "UNVERIFIED"}:
            ensure_task(encounter_id, check["code"], "REVIEW", check["owner_role"], None, task_key(encounter_id, check["code"]))
    append_audit(role.value, "ENCOUNTER_EVALUATED", "encounter", encounter_id, encounter_id, {"policy_version": POLICY_VERSION})
    return {"encounter_id": encounter_id, "policy_version": POLICY_VERSION, "checks": checks}


@router.get("/encounters/{encounter_id}/readiness")
def readiness(encounter_id: UUID, _role=Depends(require_demo_role)):
    with _connect() as connection:
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
def audit_events(encounter_id: UUID = Query(...), _role=Depends(require_demo_role)):
    with _connect() as connection:
        rows = connection.execute(
            """SELECT actor_role, action, object_type, object_id, correlation_id, metadata, created_at
               FROM audit_events WHERE encounter_id = %s ORDER BY created_at""",
            (encounter_id,),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@router.get("/dashboard")
def dashboard(_role=Depends(require_demo_role)):
    with _connect() as connection:
        rows = connection.execute(
            """SELECT split_part(code, '_', 1) AS pain_point, state, count(*) AS count
               FROM obligation_checks GROUP BY pain_point, state ORDER BY pain_point, state"""
        ).fetchall()
    return {"items": [dict(row) for row in rows]}
