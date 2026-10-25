-- Additive, idempotent Study v2 migration. Startup owns the transaction.
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS kind text;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS material_ids integer[] NOT NULL DEFAULT '{}';
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS params jsonb NOT NULL DEFAULT '{}';
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS requested_count integer NOT NULL DEFAULT 0;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS delivered_count integer NOT NULL DEFAULT 0;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS batches_done integer NOT NULL DEFAULT 0;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS batches_total integer NOT NULL DEFAULT 0;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS error_code text;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS model_tier text;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS prompt_tokens bigint NOT NULL DEFAULT 0;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS cached_tokens bigint NOT NULL DEFAULT 0;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS completion_tokens bigint NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS aura_concept_outlines (
 student_id integer NOT NULL,course_id integer NOT NULL,content_hash text NOT NULL,
 outline jsonb NOT NULL,created_at timestamptz NOT NULL DEFAULT NOW(),PRIMARY KEY(student_id,course_id,content_hash));
CREATE TABLE IF NOT EXISTS aura_study_attempts (
 id uuid PRIMARY KEY,artifact_id uuid NOT NULL REFERENCES aura_study_artifacts(id),student_id integer NOT NULL,
 course_id integer NOT NULL,answers jsonb NOT NULL DEFAULT '{}',position integer NOT NULL DEFAULT 0,
 scoring text NOT NULL DEFAULT 'partial',resume_hash text NOT NULL,revision integer NOT NULL DEFAULT 0,
 result jsonb,created_at timestamptz NOT NULL DEFAULT NOW(),updated_at timestamptz NOT NULL DEFAULT NOW());
CREATE INDEX IF NOT EXISTS aura_attempt_owner ON aura_study_attempts(student_id,course_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS aura_card_reviews (
 artifact_id uuid NOT NULL REFERENCES aura_study_artifacts(id),card_id text NOT NULL,student_id integer NOT NULL,
 course_id integer NOT NULL,due_at timestamptz NOT NULL DEFAULT NOW(),interval_days integer NOT NULL DEFAULT 0,
 ease double precision NOT NULL DEFAULT 2.5,repetitions integer NOT NULL DEFAULT 0,
 updated_at timestamptz NOT NULL DEFAULT NOW(),PRIMARY KEY(artifact_id,card_id));
CREATE TABLE IF NOT EXISTS aura_study_activity (
 id uuid PRIMARY KEY,student_id integer NOT NULL,course_id integer NOT NULL,kind text NOT NULL,
 title text NOT NULL,result jsonb,duration_seconds integer NOT NULL DEFAULT 0,
 created_at timestamptz NOT NULL DEFAULT NOW());
CREATE INDEX IF NOT EXISTS aura_activity_owner ON aura_study_activity(student_id,course_id,created_at DESC);
ALTER TABLE aura_agent_tasks ADD COLUMN IF NOT EXISTS scheduled_for date;
ALTER TABLE aura_agent_tasks ADD COLUMN IF NOT EXISTS completed_at timestamptz;
ALTER TABLE aura_agent_runs ADD COLUMN IF NOT EXISTS archived boolean NOT NULL DEFAULT FALSE;
ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS usage_complete boolean NOT NULL DEFAULT TRUE;
CREATE TABLE IF NOT EXISTS aura_daily_token_budget (
 student_id integer NOT NULL,day date NOT NULL,used_tokens bigint NOT NULL DEFAULT 0,
 reserved_tokens bigint NOT NULL DEFAULT 0,PRIMARY KEY(student_id,day));
CREATE TABLE IF NOT EXISTS aura_generation_metrics (
 job_id uuid NOT NULL,batch integer NOT NULL,metrics jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT NOW(),PRIMARY KEY(job_id,batch));

ALTER TABLE aura_material_preferences ADD COLUMN IF NOT EXISTS deleted boolean NOT NULL DEFAULT FALSE;
