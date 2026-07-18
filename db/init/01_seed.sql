INSERT INTO patients (id, mrn, full_name, date_of_birth)
VALUES ('00000000-0000-0000-0000-000000000001', 'DENTAL-001', 'Nguyen Minh Anh', '1992-04-12');

INSERT INTO appointments (id, patient_id, starts_at, ends_at, chair, status)
VALUES ('00000000-0000-0000-0000-000000000002', '00000000-0000-0000-0000-000000000001', '2026-07-17 09:00+07', '2026-07-17 09:45+07', 'CHAIR-01', 'CHECKED_IN');

INSERT INTO encounters (id, patient_id, appointment_id, stage)
VALUES ('00000000-0000-0000-0000-000000000003', '00000000-0000-0000-0000-000000000001', '00000000-0000-0000-0000-000000000002', 'CHECK_IN');

INSERT INTO audit_events (actor_role, action, object_type, object_id, encounter_id, metadata)
VALUES ('QA', 'POLICY_SELECTED', 'policy', NULL, '00000000-0000-0000-0000-000000000003', '{"version":"dental-policy.v1"}');
