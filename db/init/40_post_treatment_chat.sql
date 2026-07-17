ALTER TABLE evidence_items ADD COLUMN IF NOT EXISTS released_to_patient_at timestamptz;

CREATE INDEX IF NOT EXISTS evidence_items_patient_release_idx
  ON evidence_items (encounter_id, released_to_patient_at)
  WHERE released_to_patient_at IS NOT NULL;
