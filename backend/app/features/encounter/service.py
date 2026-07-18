import json

from ...core.contracts import EncounterStage
from ...core.errors import AppError
from ...core.services import _connect


STAGES = list(EncounterStage)
CONTEXT_QUERY = """
    SELECT e.id, e.stage, e.version,
      jsonb_build_object(
        'id', p.id, 'mrn', p.mrn, 'full_name', p.full_name,
        'date_of_birth', p.date_of_birth
      ) AS patient,
      CASE WHEN a.id IS NULL THEN NULL ELSE jsonb_build_object(
        'id', a.id, 'starts_at', a.starts_at, 'ends_at', a.ends_at,
        'chair', a.chair, 'status', a.status
      ) END AS appointment
    FROM encounters e
    JOIN patients p ON p.id = e.patient_id
    LEFT JOIN appointments a ON a.id = e.appointment_id
    WHERE e.id = %s
"""


def _context(connection, encounter_id):
    row = connection.execute(CONTEXT_QUERY, (encounter_id,)).fetchone()
    if not row:
        raise AppError("ENCOUNTER_NOT_FOUND", "Encounter not found", {"encounter_id": str(encounter_id)}, 404)
    return dict(row)


def get_encounter(encounter_id):
    with _connect() as connection:
        return _context(connection, encounter_id)


def advance_stage(encounter_id, stage, version, actor_role):
    target = EncounterStage(stage)
    with _connect() as connection:
        current = _context(connection, encounter_id)
        current_stage = EncounterStage(current["stage"])
        if version != current["version"]:
            raise AppError(
                "STALE_ENCOUNTER_VERSION",
                "Encounter was updated by another request",
                {
                    "expected_version": version,
                    "current_version": current["version"],
                    "current_stage": current_stage.value,
                },
                409,
            )
        if STAGES.index(target) != STAGES.index(current_stage) + 1:
            raise AppError(
                "INVALID_STAGE_TRANSITION",
                "Encounter can only move to the next stage",
                {"current_stage": current_stage.value, "requested_stage": target.value},
                409,
            )
        updated = connection.execute(
            """
            UPDATE encounters SET stage = %s, version = version + 1
            WHERE id = %s AND version = %s
            RETURNING id
            """,
            (target.value, encounter_id, version),
        ).fetchone()
        if not updated:
            refreshed = _context(connection, encounter_id)
            raise AppError(
                "STALE_ENCOUNTER_VERSION",
                "Encounter was updated by another request",
                {
                    "expected_version": version,
                    "current_version": refreshed["version"],
                    "current_stage": refreshed["stage"],
                },
                409,
            )
        connection.execute(
            """
            INSERT INTO audit_events
              (actor_role, action, object_type, object_id, encounter_id, metadata)
            VALUES (%s, 'ENCOUNTER_STAGE_CHANGED', 'encounter', %s, %s, %s::jsonb)
            """,
            (
                actor_role.value if hasattr(actor_role, "value") else actor_role,
                encounter_id,
                encounter_id,
                json.dumps(
                    {
                        "from_stage": current_stage.value,
                        "to_stage": target.value,
                        "from_version": version,
                        "to_version": version + 1,
                    }
                ),
            ),
        )
        return _context(connection, encounter_id)


def get_stage_transitions(encounter_id):
    with _connect() as connection:
        _context(connection, encounter_id)
        rows = connection.execute(
            """
            SELECT id,
              metadata->>'from_stage' AS from_stage,
              metadata->>'to_stage' AS to_stage,
              actor_role,
              (metadata->>'from_version')::integer AS from_version,
              (metadata->>'to_version')::integer AS to_version,
              created_at AS occurred_at
            FROM audit_events
            WHERE encounter_id = %s AND action = 'ENCOUNTER_STAGE_CHANGED'
            ORDER BY created_at, id
            """,
            (encounter_id,),
        ).fetchall()
        return [dict(row) for row in rows]
