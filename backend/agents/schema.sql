CREATE TABLE IF NOT EXISTS aura_memory_settings (
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY(student_id,course_id)
);
CREATE TABLE IF NOT EXISTS aura_memories (
    id UUID PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('preference','decision','event','task_progress','learner_fact')),
    dedup_key TEXT NOT NULL,
    record JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(student_id,course_id,kind,dedup_key)
);
CREATE INDEX IF NOT EXISTS aura_memory_owner ON aura_memories(student_id,course_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS aura_agent_tasks (
    id UUID PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    details TEXT NOT NULL DEFAULT '',
    dedup_key TEXT NOT NULL,
    done BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(student_id,course_id,dedup_key)
);
CREATE TABLE IF NOT EXISTS aura_agent_runs (
    id UUID PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    source_id INTEGER REFERENCES sources(source_id) ON DELETE SET NULL,
    request JSONB NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued' CHECK(state IN ('queued','running','completed','cancelled','budget_exhausted','timed_out','failed','interrupted')),
    steps JSONB NOT NULL DEFAULT '[]',
    tokens_used INTEGER NOT NULL DEFAULT 0,
    result JSONB,
    error_code TEXT,
    worker_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS aura_runs_owner ON aura_agent_runs(student_id,course_id,created_at DESC);
CREATE INDEX IF NOT EXISTS aura_runs_queue ON aura_agent_runs(state,created_at);
ALTER TABLE aura_agent_tasks ADD COLUMN IF NOT EXISTS scheduled_for date;
ALTER TABLE aura_agent_tasks ADD COLUMN IF NOT EXISTS completed_at timestamptz;
ALTER TABLE aura_agent_runs ADD COLUMN IF NOT EXISTS archived boolean NOT NULL DEFAULT FALSE;
