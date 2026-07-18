from ...core.services import _connect, append_audit_in, require_encounter_in
from .evaluator import POLICY_VERSION, derive_context, desired_task_status, evaluate, task_key


READY_STATES = {"SATISFIED", "NOT_APPLICABLE"}


def evidence_by_code(connection, encounter_id):
    rows = connection.execute(
        "SELECT code, state, value FROM evidence_items WHERE encounter_id = %s",
        (encounter_id,),
    ).fetchall()
    return {row["code"]: dict(row) for row in rows}


def current_assessment(connection, encounter_id):
    evidence = evidence_by_code(connection, encounter_id)
    return evaluate(evidence, derive_context(evidence))


def blockers(checks):
    return [
        {"code": check["code"], "state": check["state"], "owner_role": check["owner_role"]}
        for check in checks
        if check["state"] not in READY_STATES
    ]


def reconcile_assessment(connection, encounter_id, actor_role):
    require_encounter_in(connection, encounter_id)
    checks = current_assessment(connection, encounter_id)
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
                       status = CASE
                         WHEN tasks.status IN ('CANCELLED', 'COMPLETED') THEN 'OPEN'
                         ELSE tasks.status
                       END""",
                (encounter_id, check["code"], check["owner_role"], key),
            )
        else:
            connection.execute(
                """UPDATE tasks SET status = 'CANCELLED'
                   WHERE idempotency_key = %s AND status IN ('OPEN', 'ACKNOWLEDGED')""",
                (key,),
            )
    append_audit_in(
        connection,
        actor_role.value if hasattr(actor_role, "value") else actor_role,
        "ENCOUNTER_EVALUATED",
        "encounter",
        encounter_id,
        encounter_id,
        {"policy_version": POLICY_VERSION},
    )
    return checks


def evaluate_encounter(encounter_id, actor_role):
    with _connect() as connection:
        return reconcile_assessment(connection, encounter_id, actor_role)


def close_readiness(encounter_id):
    with _connect() as connection:
        require_encounter_in(connection, encounter_id)
        checks = current_assessment(connection, encounter_id)
    return {"ready": not blockers(checks), "policy_version": POLICY_VERSION, "blockers": blockers(checks)}


def close_transition_guard(connection, encounter_id, actor_role):
    checks = reconcile_assessment(connection, encounter_id, actor_role)
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
