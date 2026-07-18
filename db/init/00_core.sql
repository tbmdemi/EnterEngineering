CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE patients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  mrn text NOT NULL UNIQUE,
  full_name text NOT NULL,
  date_of_birth date NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE appointments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES patients(id),
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  chair text NOT NULL,
  status text NOT NULL,
  CHECK (starts_at < ends_at)
);

CREATE TABLE encounters (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  patient_id uuid NOT NULL REFERENCES patients(id),
  appointment_id uuid REFERENCES appointments(id),
  stage text NOT NULL CHECK (stage IN ('CHECK_IN','PRE_TREATMENT','TREATMENT','POST_TREATMENT','CLOSED')),
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence_items (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  encounter_id uuid NOT NULL REFERENCES encounters(id),
  code text NOT NULL,
  state text NOT NULL CHECK (state IN ('DRAFT','VERIFIED')),
  value jsonb NOT NULL DEFAULT '{}',
  source_type text NOT NULL,
  source_ref text,
  actor_role text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (encounter_id, code)
);

CREATE TABLE obligation_checks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  encounter_id uuid NOT NULL REFERENCES encounters(id),
  code text NOT NULL,
  state text NOT NULL CHECK (state IN ('PENDING','MISSING','UNVERIFIED','SATISFIED','NOT_APPLICABLE')),
  policy_version text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (encounter_id, code, policy_version)
);

CREATE TABLE tasks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  encounter_id uuid NOT NULL REFERENCES encounters(id),
  obligation_code text NOT NULL,
  task_type text NOT NULL,
  owner_role text NOT NULL,
  status text NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','ACKNOWLEDGED','COMPLETED','CANCELLED')),
  due_at timestamptz,
  idempotency_key text NOT NULL UNIQUE
);

CREATE TABLE ai_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  encounter_id uuid NOT NULL REFERENCES encounters(id),
  model_name text NOT NULL,
  status text NOT NULL,
  output jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_role text NOT NULL,
  action text NOT NULL,
  object_type text NOT NULL,
  object_id uuid,
  encounter_id uuid REFERENCES encounters(id),
  correlation_id uuid NOT NULL DEFAULT gen_random_uuid(),
  metadata jsonb NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);
