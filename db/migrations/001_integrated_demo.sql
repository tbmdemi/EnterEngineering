BEGIN;

INSERT INTO patients (id, mrn, full_name, date_of_birth)
VALUES ('00000000-0000-0000-0000-000000000001', 'DENTAL-001', 'Nguyen Minh Anh', '1992-04-12')
ON CONFLICT DO NOTHING;

INSERT INTO appointments (id, patient_id, starts_at, ends_at, chair, status)
VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', '2026-07-17 09:00+07', '2026-07-17 09:45+07', 'CHAIR-01', 'CHECKED_IN')
ON CONFLICT DO NOTHING;

INSERT INTO encounters (id, patient_id, appointment_id, stage)
VALUES ('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', 'CHECK_IN')
ON CONFLICT DO NOTHING;

INSERT INTO audit_events (actor_role, action, object_type, object_id, encounter_id, metadata)
SELECT 'QA', 'POLICY_SELECTED', 'policy', NULL, '00000000-0000-0000-0000-000000000003', '{"version":"dental-policy.v1"}'::jsonb
WHERE NOT EXISTS (
  SELECT 1 FROM audit_events
  WHERE encounter_id = '00000000-0000-0000-0000-000000000003'
    AND action = 'POLICY_SELECTED'
    AND metadata->>'version' = 'dental-policy.v1'
);

ALTER TABLE evidence_items
  ADD COLUMN IF NOT EXISTS released_to_patient_at timestamptz;

CREATE INDEX IF NOT EXISTS evidence_items_patient_release_idx
  ON evidence_items (encounter_id, released_to_patient_at)
  WHERE released_to_patient_at IS NOT NULL;

INSERT INTO evidence_items (encounter_id, code, state, value, source_type, source_ref, actor_role)
VALUES (
  '00000000-0000-0000-0000-000000000003', 'PRE_PROCEDURE', 'VERIFIED',
  '{"name":"routine cleaning","requires_imaging":false}', 'SEED', 'dental-demo', 'QA'
)
ON CONFLICT (encounter_id, code) DO NOTHING;

INSERT INTO appointments (id, patient_id, starts_at, ends_at, chair, status) VALUES
  ('00000000-0000-0000-0000-000000000040', '00000000-0000-0000-0000-000000000001', '2026-07-17 09:30+07', '2026-07-17 10:15+07', 'CHAIR-01', 'BOOKED'),
  ('00000000-0000-0000-0000-000000000041', '00000000-0000-0000-0000-000000000001', '2026-07-17 09:15+07', '2026-07-17 09:30+07', 'CHAIR-01', 'CANCELLED'),
  ('00000000-0000-0000-0000-000000000045', '00000000-0000-0000-0000-000000000001', '2026-07-17 09:45+07', '2026-07-17 10:15+07', 'CHAIR-01', 'BOOKED')
ON CONFLICT DO NOTHING;

INSERT INTO tasks (id, encounter_id, obligation_code, task_type, owner_role, due_at, idempotency_key) VALUES
  ('00000000-0000-0000-0000-000000000042', '00000000-0000-0000-0000-000000000003', 'COORD_HANDOFF_ACK', 'HANDOFF', 'ASSISTANT', '2026-07-17 10:00+07', 'coord:demo:handoff'),
  ('00000000-0000-0000-0000-000000000043', '00000000-0000-0000-0000-000000000003', 'COORD_REFERRAL_OWNER', 'REFERRAL', 'DENTIST', '2026-07-17 12:00+07', 'coord:demo:referral'),
  ('00000000-0000-0000-0000-000000000044', '00000000-0000-0000-0000-000000000003', 'COORD_SCHEDULE_CLEAR', 'REVIEW_SCHEDULE_CONFLICT', 'FRONT_DESK', '2026-07-17 09:45+07', 'coord:00000000-0000-0000-0000-000000000003:schedule-conflict')
ON CONFLICT DO NOTHING;

COMMIT;
