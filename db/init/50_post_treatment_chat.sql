ALTER TABLE evidence_items ADD COLUMN IF NOT EXISTS released_to_patient_at timestamptz;

CREATE INDEX IF NOT EXISTS evidence_items_patient_release_idx
  ON evidence_items (encounter_id, released_to_patient_at)
  WHERE released_to_patient_at IS NOT NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'evidence_items_release_requires_verified_check'
      AND conrelid = 'evidence_items'::regclass
  ) THEN
    ALTER TABLE evidence_items
      ADD CONSTRAINT evidence_items_release_requires_verified_check
      CHECK (released_to_patient_at IS NULL OR state = 'VERIFIED');
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION prevent_released_evidence_item_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF OLD.released_to_patient_at IS NOT NULL THEN
      RAISE EXCEPTION 'released evidence item % cannot be deleted', OLD.id
        USING ERRCODE = '23514';
    END IF;

    RETURN OLD;
  END IF;

  IF OLD.released_to_patient_at IS NOT NULL
     AND (
       NEW.state IS DISTINCT FROM OLD.state
       OR NEW.value IS DISTINCT FROM OLD.value
       OR NEW.source_type IS DISTINCT FROM OLD.source_type
       OR NEW.source_ref IS DISTINCT FROM OLD.source_ref
       OR NEW.actor_role IS DISTINCT FROM OLD.actor_role
       OR NEW.released_to_patient_at IS DISTINCT FROM OLD.released_to_patient_at
     ) THEN
    RAISE EXCEPTION 'released evidence item % cannot be modified', OLD.id
      USING ERRCODE = '23514';
  END IF;

  RETURN NEW;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'evidence_items_prevent_released_delete_trigger'
      AND tgrelid = 'evidence_items'::regclass
      AND NOT tgisinternal
  ) THEN
    EXECUTE $trigger$
      CREATE TRIGGER evidence_items_prevent_released_delete_trigger
      BEFORE DELETE
      ON evidence_items
      FOR EACH ROW
      EXECUTE FUNCTION prevent_released_evidence_item_mutation()
    $trigger$;
  END IF;
END;
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_trigger
    WHERE tgname = 'evidence_items_prevent_released_mutation_trigger'
      AND tgrelid = 'evidence_items'::regclass
      AND NOT tgisinternal
  ) THEN
    EXECUTE $trigger$
      CREATE TRIGGER evidence_items_prevent_released_mutation_trigger
      BEFORE UPDATE OF state, value, source_type, source_ref, actor_role, released_to_patient_at
      ON evidence_items
      FOR EACH ROW
      EXECUTE FUNCTION prevent_released_evidence_item_mutation()
    $trigger$;
  END IF;
END;
$$;
