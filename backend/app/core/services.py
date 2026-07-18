import json
import os
from contextlib import contextmanager
from contextvars import ContextVar

from .errors import AppError


_active_connection = ContextVar("careguard_active_connection", default=None)


def _json(value):
    return json.dumps(value, default=str)


@contextmanager
def _connect():
    """Open one short transaction; import stays lazy for contract-only tooling."""
    current = _active_connection.get()
    if current is not None:
        yield current
        return
    import psycopg
    from psycopg.rows import dict_row

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required")
    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        token = _active_connection.set(connection)
        try:
            yield connection
        finally:
            _active_connection.reset(token)


def upsert_evidence_in(connection, encounter_id, code, state, value, source_type, source_ref, actor_role):
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
    return dict(connection.execute(query, (encounter_id, code, state, _json(value), source_type, source_ref, actor_role)).fetchone())


def upsert_evidence(encounter_id, code, state, value, source_type, source_ref, actor_role):
    with _connect() as connection:
        return upsert_evidence_in(connection, encounter_id, code, state, value, source_type, source_ref, actor_role)


def require_encounter_in(connection, encounter_id):
    if not connection.execute("SELECT 1 FROM encounters WHERE id = %s", (encounter_id,)).fetchone():
        raise AppError("ENCOUNTER_NOT_FOUND", "Encounter was not found", {"encounter_id": str(encounter_id)}, 404)


def require_encounter(encounter_id):
    with _connect() as connection:
        require_encounter_in(connection, encounter_id)


def ensure_task_in(connection, encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key):
    query = """
        INSERT INTO tasks
          (encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (idempotency_key) DO UPDATE SET
          status = CASE WHEN tasks.status = 'CANCELLED' THEN 'OPEN' ELSE tasks.status END
        RETURNING *
    """
    return dict(connection.execute(query, (encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key)).fetchone())


def ensure_task(encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key):
    with _connect() as connection:
        return ensure_task_in(connection, encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key)


def append_audit_in(connection, actor_role, action, object_type, object_id, encounter_id, metadata):
    query = """
        INSERT INTO audit_events
          (actor_role, action, object_type, object_id, encounter_id, metadata)
        VALUES (%s, %s, %s, %s, %s, %s::jsonb)
        RETURNING *
    """
    return dict(connection.execute(query, (actor_role, action, object_type, object_id, encounter_id, _json(metadata))).fetchone())


def append_audit(actor_role, action, object_type, object_id, encounter_id, metadata):
    with _connect() as connection:
        return append_audit_in(connection, actor_role, action, object_type, object_id, encounter_id, metadata)
