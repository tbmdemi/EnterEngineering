INSERT INTO evidence_items (encounter_id, code, state, value, source_type, source_ref, actor_role)
VALUES (
  '00000000-0000-0000-0000-000000000003', 'PRE_PROCEDURE', 'VERIFIED',
  '{"name":"routine cleaning","requires_imaging":false}', 'SEED', 'dental-demo', 'QA'
)
ON CONFLICT (encounter_id, code) DO NOTHING;
