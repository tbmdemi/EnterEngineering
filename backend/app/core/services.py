import json
import os
from contextlib import contextmanager


def _json(value):
    return json.dumps(value, default=str)


@contextmanager
def _connect():
    """Open one short transaction; import stays lazy for contract-only tooling."""
    import psycopg
    from psycopg.rows import dict_row

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        yield connection


def upsert_evidence(encounter_id, code, state, value, source_type, source_ref, actor_role):
    query = """
        INSERT INTO evidence_items
          (encounter_id, code, state, value, source_type, source_ref, actor_role)
        VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s)
        ON CONFLICT (encounter_id, code) DO UPDATE SET
          state = EXCLUDED.state, value = EXCLUDED.value,
          source_type = EXCLUDED.source_type, source_ref = EXCLUDED.source_ref,
          actor_role = EXCLUDED.actor_role, updated_at = now()
        RETURNING *
    """
    with _connect() as connection:
        return dict(connection.execute(query, (encounter_id, code, state, _json(value), source_type, source_ref, actor_role)).fetchone())


def ensure_task(encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key):
    query = """
        INSERT INTO tasks
          (encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (idempotency_key) DO UPDATE SET
          idempotency_key = EXCLUDED.idempotency_key
        RETURNING *
    """
    with _connect() as connection:
        return dict(connection.execute(query, (encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key)).fetchone())


def append_audit(actor_role, action, object_type, object_id, encounter_id, metadata):
    query = """
        INSERT INTO audit_events
          (actor_role, action, object_type, object_id, encounter_id, metadata)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        RETURNING *
    """
    with _connect() as connection:
        return dict(connection.execute(query, (actor_role, action, object_type, object_id, encounter_id, _json(metadata))).fetchone())
