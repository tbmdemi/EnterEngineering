"""Stable integration seam; persistence is wired by the integration module."""


def upsert_evidence(encounter_id, code, state, value, source_type, source_ref, actor_role):
    raise NotImplementedError("integration module must bind persistence")


def ensure_task(encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key):
    raise NotImplementedError("integration module must bind persistence")


def append_audit(actor_role, action, object_type, object_id, encounter_id, metadata):
    raise NotImplementedError("integration module must bind persistence")
