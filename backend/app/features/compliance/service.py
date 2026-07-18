from ...core.services import _connect, append_audit_in, require_encounter_in
from .evaluator import (
    POLICY_VERSION,
    active_codes_for_stage,
    derive_context,
    desired_task_status,
    evaluate,
    required_codes_for_transition,
    task_key,
)


READY_STATES = {"SATISFIED", "NOT_APPLICABLE"}
# Coordination owns the lifecycle of these tasks. Compliance evaluates their
# evidence but must not create a second generic REVIEW task for the same work.
DOMAIN_TASK_CODES = {"COORD_HANDOFF_ACK", "COORD_REFERRAL_OWNER", "COORD_SCHEDULE_CLEAR"}


def evidence_by_code(connection, encounter_id):
    rows = connection.execute(
        "SELECT code, state, value FROM evidence_items WHERE encounter_id = %s",
        (encounter_id,),
    ).fetchall()
    return {row["code"]: dict(row) for row in rows}


def current_assessment(connection, encounter_id, codes=None):
    evidence = evidence_by_code(connection, encounter_id)
    return evaluate(evidence, derive_context(evidence), codes)


def blockers(checks):
    return [
        {"code": check["code"], "state": check["state"], "owner_role": check["owner_role"]}
        for check in checks
        if check["state"] not in READY_STATES
    ]


def reconcile_assessment(connection, encounter_id, actor_role, codes=None, audit_action="ENCOUNTER_EVALUATED"):
    require_encounter_in(connection, encounter_id)
    checks = current_assessment(connection, encounter_id, codes)
    for check in checks:
        connection.execute(
            """INSERT INTO obligation_checks (encounter_id, code, state, policy_version)
               VALUES (%s, %s, %s, %s)
               ON CONFLICT (encounter_id, code, policy_version) DO UPDATE
               SET state = EXCLUDED.state, updated_at = now()""",
            (encounter_id, check["code"], check["state"], POLICY_VERSION),
        )
        if check["code"] in DOMAIN_TASK_CODES:
            continue
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
                       status = CASE
                         WHEN tasks.status IN ('CANCELLED', 'COMPLETED') THEN 'OPEN'
                         ELSE tasks.status
                       END,
                       updated_at = now(),
                       cancelled_at = CASE WHEN tasks.status IN ('CANCELLED', 'COMPLETED') THEN NULL ELSE tasks.cancelled_at END,
                       completed_at = CASE WHEN tasks.status IN ('CANCELLED', 'COMPLETED') THEN NULL ELSE tasks.completed_at END""",
                (encounter_id, check["code"], check["owner_role"], key),
            )
        else:
            connection.execute(
                """UPDATE tasks SET status = 'CANCELLED', cancelled_at = now(), updated_at = now()
                   WHERE idempotency_key = %s AND status IN ('OPEN', 'ACKNOWLEDGED')""",
                (key,),
            )
    append_audit_in(
        connection,
        actor_role.value if hasattr(actor_role, "value") else actor_role,
        audit_action,
        "encounter",
        encounter_id,
        encounter_id,
        {"policy_version": POLICY_VERSION},
    )
    return checks


def evaluate_encounter(encounter_id, actor_role):
    with _connect() as connection:
        row = connection.execute("SELECT stage FROM encounters WHERE id = %s", (encounter_id,)).fetchone()
        if not row:
            require_encounter_in(connection, encounter_id)
        return reconcile_assessment(
            connection,
            encounter_id,
            actor_role,
            active_codes_for_stage(row["stage"]),
        )


def close_readiness(encounter_id):
    with _connect() as connection:
        require_encounter_in(connection, encounter_id)
        checks = current_assessment(connection, encounter_id)
    return {"ready": not blockers(checks), "policy_version": POLICY_VERSION, "blockers": blockers(checks)}


def transition_readiness(encounter_id, target_stage):
    codes = required_codes_for_transition(target_stage)
    with _connect() as connection:
        require_encounter_in(connection, encounter_id)
        checks = current_assessment(connection, encounter_id, codes)
    missing = blockers(checks)
    return {
        "ready": not missing,
        "target_stage": target_stage,
        "policy_version": POLICY_VERSION,
        "blockers": missing,
    }


def _transition_guard(connection, encounter_id, actor_role, target_stage):
    checks = reconcile_assessment(
        connection,
        encounter_id,
        actor_role,
        required_codes_for_transition(target_stage),
        "ENCOUNTER_TRANSITION_EVALUATED",
    )
    missing = blockers(checks)
    if not missing:
        return None
    append_audit_in(
        connection,
        actor_role.value if hasattr(actor_role, "value") else actor_role,
        "ENCOUNTER_STAGE_BLOCKED",
        "encounter",
        encounter_id,
        encounter_id,
        {
            "policy_version": POLICY_VERSION,
            "target_stage": target_stage,
            "blocker_codes": [item["code"] for item in missing],
        },
    )
    return {
        "code": "STAGE_REQUIREMENTS_NOT_READY",
        "message": "Encounter cannot advance until stage requirements are ready",
        "details": {
            "target_stage": target_stage,
            "policy_version": POLICY_VERSION,
            "blockers": missing,
        },
        "status_code": 409,
    }


def treatment_transition_guard(connection, encounter_id, actor_role):
    return _transition_guard(connection, encounter_id, actor_role, "TREATMENT")


def post_treatment_transition_guard(connection, encounter_id, actor_role):
    return _transition_guard(connection, encounter_id, actor_role, "POST_TREATMENT")


def close_transition_guard(connection, encounter_id, actor_role):
    checks = reconcile_assessment(
        connection,
        encounter_id,
        actor_role,
        required_codes_for_transition("CLOSED"),
        "ENCOUNTER_TRANSITION_EVALUATED",
    )
    missing = blockers(checks)
    if not missing:
        return None
    append_audit_in(
        connection,
        actor_role.value if hasattr(actor_role, "value") else actor_role,
        "ENCOUNTER_CLOSE_BLOCKED",
        "encounter",
        encounter_id,
        encounter_id,
        {"policy_version": POLICY_VERSION, "blocker_codes": [item["code"] for item in missing]},
    )
    return {
        "code": "COMPLIANCE_NOT_READY",
        "message": "Encounter cannot be closed until all compliance obligations are ready",
        "details": {"policy_version": POLICY_VERSION, "blockers": missing},
        "status_code": 409,
    }
