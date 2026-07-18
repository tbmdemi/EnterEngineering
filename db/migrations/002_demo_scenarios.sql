BEGIN;

-- Stable, explicitly synthetic fixtures for switching between UI workflow states.
-- Scenario encounter IDs:
--   CHECK_IN_BLANK             30000000-0000-0000-0000-000000000001
--   PRE_TREATMENT_INCOMPLETE   30000000-0000-0000-0000-000000000002
--   TREATMENT_PRE_READY        30000000-0000-0000-0000-000000000003
--   POST_TREATMENT_BLOCKED     30000000-0000-0000-0000-000000000004
--   POST_TREATMENT_READY       30000000-0000-0000-0000-000000000005

INSERT INTO patients (id, mrn, full_name, date_of_birth, created_at) VALUES
  ('10000000-0000-0000-0000-000000000001', 'DEMO-SCENARIO-01', 'Synthetic Patient 01', '1990-01-01', '2026-07-18 08:00+07'),
  ('10000000-0000-0000-0000-000000000002', 'DEMO-SCENARIO-02', 'Synthetic Patient 02', '1990-01-02', '2026-07-18 08:00+07'),
  ('10000000-0000-0000-0000-000000000003', 'DEMO-SCENARIO-03', 'Synthetic Patient 03', '1990-01-03', '2026-07-18 08:00+07'),
  ('10000000-0000-0000-0000-000000000004', 'DEMO-SCENARIO-04', 'Synthetic Patient 04', '1990-01-04', '2026-07-18 08:00+07'),
  ('10000000-0000-0000-0000-000000000005', 'DEMO-SCENARIO-05', 'Synthetic Patient 05', '1990-01-05', '2026-07-18 08:00+07')
ON CONFLICT DO NOTHING;

INSERT INTO appointments (id, patient_id, starts_at, ends_at, chair, status) VALUES
  ('20000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '2026-07-21 08:00+07', '2026-07-21 08:45+07', 'DEMO-CHAIR-01', 'CHECKED_IN'),
  ('20000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', '2026-07-21 09:00+07', '2026-07-21 09:45+07', 'DEMO-CHAIR-02', 'CHECKED_IN'),
  ('20000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000003', '2026-07-21 10:00+07', '2026-07-21 10:45+07', 'DEMO-CHAIR-03', 'CHECKED_IN'),
  ('20000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000004', '2026-07-21 11:00+07', '2026-07-21 11:45+07', 'DEMO-CHAIR-04', 'CHECKED_IN'),
  ('20000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000005', '2026-07-21 13:00+07', '2026-07-21 13:45+07', 'DEMO-CHAIR-05', 'CHECKED_IN')
ON CONFLICT DO NOTHING;

-- Versions match the number of forward transitions needed to reach each stage.
INSERT INTO encounters (id, patient_id, appointment_id, stage, version, created_at) VALUES
  ('30000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000001', '20000000-0000-0000-0000-000000000001', 'CHECK_IN', 1, '2026-07-18 08:00+07'),
  ('30000000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000002', '20000000-0000-0000-0000-000000000002', 'PRE_TREATMENT', 2, '2026-07-18 08:00+07'),
  ('30000000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000003', '20000000-0000-0000-0000-000000000003', 'TREATMENT', 3, '2026-07-18 08:00+07'),
  ('30000000-0000-0000-0000-000000000004', '10000000-0000-0000-0000-000000000004', '20000000-0000-0000-0000-000000000004', 'POST_TREATMENT', 4, '2026-07-18 08:00+07'),
  ('30000000-0000-0000-0000-000000000005', '10000000-0000-0000-0000-000000000005', '20000000-0000-0000-0000-000000000005', 'POST_TREATMENT', 4, '2026-07-18 08:00+07')
ON CONFLICT DO NOTHING;

-- The two post-treatment fixtures share a complete evidence template. The
-- blocked fixture deliberately omits only POST_RECALL, so its blocker is easy
-- to understand. Conditional obligations are made NOT_APPLICABLE by their
-- verified context evidence (no medication prescribed, no imaging required).
WITH full_ready_templates (code, value) AS (
  VALUES
    ('DOC_CONSENT_SIGNED', '{"signed":true}'::jsonb),
    ('DOC_TREATMENT_PLAN_SIGNED', '{"signed":true}'::jsonb),
    ('DOC_PROGRESS_NOTE', '{"note":"Synthetic routine preventive care documented for UI demonstration."}'::jsonb),
    ('DOC_MEDICATION_PRESCRIBED', '{"prescribed":false}'::jsonb),
    ('DOC_TOOTH_SURFACE', '{"tooth":"11","surface":"F"}'::jsonb),
    ('PRE_PROCEDURE', '{"name":"synthetic routine cleaning","requires_imaging":false}'::jsonb),
    ('PRE_MEDICAL_HISTORY', '{"summary":"Synthetic history reviewed; no contraindications declared.","reviewed_source_refs":["DOC-DEMO-001"],"performed_at":"2026-07-18T08:15:00+07:00"}'::jsonb),
    ('PRE_ALLERGY', '{"status":"NONE_KNOWN","performed_at":"2026-07-18T08:16:00+07:00"}'::jsonb),
    ('PRE_VITALS', '{"systolic":120,"diastolic":80,"pulse":72,"performed_at":"2026-07-18T08:17:00+07:00"}'::jsonb),
    ('PRE_STERILIZATION', '{"confirmed":true,"cycle_or_tray_id":"DEMO-CYCLE-READY","performed_at":"2026-07-18T08:18:00+07:00"}'::jsonb),
    ('POST_CARE_INSTRUCTIONS', '{"text":"Synthetic after-care instructions for UI demonstration only."}'::jsonb),
    ('POST_RECALL', '{"recall_at":"2026-08-21T09:00:00+07:00"}'::jsonb),
    ('POST_COMPLICATION_MONITORING', '{"monitor_until":"2026-07-28T09:00:00+07:00"}'::jsonb),
    ('COORD_HANDOFF_ACK', '{"task_id":"populated-per-scenario","acknowledged_by":"ASSISTANT"}'::jsonb),
    ('COORD_REFERRAL_OWNER', '{"owner_role":"DENTIST"}'::jsonb),
    ('COORD_SCHEDULE_CLEAR', '{"clear":true,"conflicts":[]}'::jsonb)
),
late_scenarios (encounter_id, include_recall, released_at, handoff_task_id) AS (
  VALUES
    ('30000000-0000-0000-0000-000000000004'::uuid, false, '2026-07-18 09:00+07'::timestamptz, '50000000-0000-0000-0000-000000000104'::uuid),
    ('30000000-0000-0000-0000-000000000005'::uuid, true,  '2026-07-18 09:00+07'::timestamptz, '50000000-0000-0000-0000-000000000105'::uuid)
),
scenario_evidence (encounter_id, code, state, value, released_to_patient_at) AS (
  VALUES
    -- PRE_TREATMENT_INCOMPLETE: one verified check, one unreviewed draft,
    -- while vitals and sterilization remain absent.
    ('30000000-0000-0000-0000-000000000002'::uuid, 'PRE_PROCEDURE', 'VERIFIED', '{"name":"synthetic routine cleaning","requires_imaging":false}'::jsonb, NULL::timestamptz),
    ('30000000-0000-0000-0000-000000000002'::uuid, 'PRE_MEDICAL_HISTORY', 'VERIFIED', '{"summary":"Synthetic history reviewed.","reviewed_source_refs":["DOC-DEMO-001"],"performed_at":"2026-07-18T08:15:00+07:00"}'::jsonb, NULL::timestamptz),
    ('30000000-0000-0000-0000-000000000002'::uuid, 'PRE_ALLERGY', 'DRAFT', '{"status":"NONE_KNOWN"}'::jsonb, NULL::timestamptz),

    -- TREATMENT_PRE_READY: consent, plan and every applicable PRE_* check are
    -- verified; imaging is not applicable because PRE_PROCEDURE says false.
    ('30000000-0000-0000-0000-000000000003'::uuid, 'DOC_CONSENT_SIGNED', 'VERIFIED', '{"signed":true}'::jsonb, NULL::timestamptz),
    ('30000000-0000-0000-0000-000000000003'::uuid, 'DOC_TREATMENT_PLAN_SIGNED', 'VERIFIED', '{"signed":true}'::jsonb, NULL::timestamptz),
    ('30000000-0000-0000-0000-000000000003'::uuid, 'PRE_PROCEDURE', 'VERIFIED', '{"name":"synthetic routine cleaning","requires_imaging":false}'::jsonb, NULL::timestamptz),
    ('30000000-0000-0000-0000-000000000003'::uuid, 'PRE_MEDICAL_HISTORY', 'VERIFIED', '{"summary":"Synthetic history reviewed; no contraindications declared.","reviewed_source_refs":["DOC-DEMO-001"],"performed_at":"2026-07-18T08:15:00+07:00"}'::jsonb, NULL::timestamptz),
    ('30000000-0000-0000-0000-000000000003'::uuid, 'PRE_ALLERGY', 'VERIFIED', '{"status":"NONE_KNOWN","performed_at":"2026-07-18T08:16:00+07:00"}'::jsonb, NULL::timestamptz),
    ('30000000-0000-0000-0000-000000000003'::uuid, 'PRE_VITALS', 'VERIFIED', '{"systolic":120,"diastolic":80,"pulse":72,"performed_at":"2026-07-18T08:17:00+07:00"}'::jsonb, NULL::timestamptz),
    ('30000000-0000-0000-0000-000000000003'::uuid, 'PRE_STERILIZATION', 'VERIFIED', '{"confirmed":true,"cycle_or_tray_id":"DEMO-CYCLE-PRE-READY","performed_at":"2026-07-18T08:18:00+07:00"}'::jsonb, NULL::timestamptz)
  UNION ALL
  SELECT
    late.encounter_id,
    template.code,
    'VERIFIED',
    CASE
      WHEN template.code = 'COORD_HANDOFF_ACK' THEN jsonb_build_object(
        'task_id', late.handoff_task_id::text,
        'acknowledged_by', 'ASSISTANT'
      )
      ELSE template.value
    END,
    CASE
      WHEN template.code LIKE 'POST_%' THEN late.released_at
      ELSE NULL::timestamptz
    END
  FROM late_scenarios AS late
  CROSS JOIN full_ready_templates AS template
  WHERE late.include_recall OR template.code <> 'POST_RECALL'
)
INSERT INTO evidence_items
  (id, encounter_id, code, state, value, source_type, source_ref, actor_role,
   released_to_patient_at, updated_at)
SELECT
  md5(scenario_evidence.encounter_id::text || ':' || scenario_evidence.code)::uuid,
  scenario_evidence.encounter_id,
  scenario_evidence.code,
  scenario_evidence.state,
  scenario_evidence.value,
  'SEED',
  'demo-scenarios.v1',
  'QA',
  scenario_evidence.released_to_patient_at,
  '2026-07-18 09:00+07'::timestamptz
FROM scenario_evidence
ON CONFLICT (encounter_id, code) DO NOTHING;

-- Include one actionable blocker and one completed follow-up to exercise task
-- states. Keys match the owning services and are globally unique.
INSERT INTO tasks
  (id, encounter_id, obligation_code, task_type, owner_role, status, due_at, idempotency_key)
VALUES
  ('50000000-0000-0000-0000-000000000004', '30000000-0000-0000-0000-000000000004', 'POST_RECALL', 'REVIEW', 'FRONT_DESK', 'OPEN', '2026-07-22 17:00+07', '30000000-0000-0000-0000-000000000004:POST_RECALL:dental-policy.v1'),
  ('50000000-0000-0000-0000-000000000005', '30000000-0000-0000-0000-000000000005', 'POST_COMPLICATION_MONITORING', 'PATIENT_FOLLOW_UP', 'ASSISTANT', 'COMPLETED', '2026-07-28 09:00+07', 'post-complication:30000000-0000-0000-0000-000000000005'),
  ('50000000-0000-0000-0000-000000000104', '30000000-0000-0000-0000-000000000004', 'COORD_HANDOFF_ACK', 'HANDOFF', 'ASSISTANT', 'COMPLETED', '2026-07-21 11:30+07', 'coord:30000000-0000-0000-0000-000000000004:handoff:coord_handoff_ack'),
  ('50000000-0000-0000-0000-000000000105', '30000000-0000-0000-0000-000000000005', 'COORD_HANDOFF_ACK', 'HANDOFF', 'ASSISTANT', 'COMPLETED', '2026-07-21 13:30+07', 'coord:30000000-0000-0000-0000-000000000005:handoff:coord_handoff_ack')
ON CONFLICT (idempotency_key) DO NOTHING;

-- Deterministic audit IDs keep this append-only table idempotent too.
WITH scenarios (encounter_id, scenario_name) AS (
  VALUES
    ('30000000-0000-0000-0000-000000000001'::uuid, 'CHECK_IN_BLANK'),
    ('30000000-0000-0000-0000-000000000002'::uuid, 'PRE_TREATMENT_INCOMPLETE'),
    ('30000000-0000-0000-0000-000000000003'::uuid, 'TREATMENT_PRE_READY'),
    ('30000000-0000-0000-0000-000000000004'::uuid, 'POST_TREATMENT_BLOCKED'),
    ('30000000-0000-0000-0000-000000000005'::uuid, 'POST_TREATMENT_READY')
)
INSERT INTO audit_events
  (id, actor_role, action, object_type, object_id, encounter_id,
   correlation_id, metadata, created_at)
SELECT
  md5('demo-scenario-audit:' || scenarios.encounter_id::text)::uuid,
  'QA',
  'DEMO_SCENARIO_SEEDED',
  'encounter',
  scenarios.encounter_id,
  scenarios.encounter_id,
  md5('demo-scenario-correlation:' || scenarios.encounter_id::text)::uuid,
  jsonb_build_object('scenario', scenarios.scenario_name, 'synthetic', true),
  '2026-07-18 09:00+07'::timestamptz
FROM scenarios
ON CONFLICT (id) DO NOTHING;

COMMIT;
