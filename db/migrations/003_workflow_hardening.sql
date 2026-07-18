BEGIN;

ALTER TABLE appointments
  ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'appointments_status_allowed'
      AND conrelid = 'appointments'::regclass
  ) THEN
    ALTER TABLE appointments
      ADD CONSTRAINT appointments_status_allowed
      CHECK (status IN ('PENDING', 'BOOKED', 'ARRIVED', 'CHECKED_IN', 'FULFILLED', 'CANCELLED', 'NO_SHOW'));
  END IF;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS encounters_one_per_appointment_idx
  ON encounters (appointment_id)
  WHERE appointment_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS appointments_id_patient_idx
  ON appointments (id, patient_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'encounters_appointment_patient_match'
      AND conrelid = 'encounters'::regclass
  ) THEN
    ALTER TABLE encounters
      ADD CONSTRAINT encounters_appointment_patient_match
      FOREIGN KEY (appointment_id, patient_id)
      REFERENCES appointments (id, patient_id);
  END IF;
END $$;

ALTER TABLE tasks
  ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS acknowledged_at timestamptz,
  ADD COLUMN IF NOT EXISTS completed_at timestamptz,
  ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;

UPDATE tasks
SET acknowledged_at = COALESCE(acknowledged_at, updated_at)
WHERE status = 'ACKNOWLEDGED' AND acknowledged_at IS NULL;

UPDATE tasks
SET completed_at = COALESCE(completed_at, updated_at)
WHERE status = 'COMPLETED' AND completed_at IS NULL;

UPDATE tasks
SET cancelled_at = COALESCE(cancelled_at, updated_at)
WHERE status = 'CANCELLED' AND cancelled_at IS NULL;

COMMIT;
