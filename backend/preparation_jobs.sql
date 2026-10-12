CREATE TABLE IF NOT EXISTS aura_preparation_jobs (
    id UUID PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
    course_id INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
    source_id INTEGER REFERENCES sources(source_id) ON DELETE SET NULL,
    filename TEXT NOT NULL,
    staged_path TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued' CHECK (state IN ('queued','processing','ready','failed')),
    stage TEXT NOT NULL DEFAULT 'queued',
    completed INTEGER NOT NULL DEFAULT 0,
    total INTEGER NOT NULL DEFAULT 0,
    result JSONB,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS aura_preparation_jobs_queue ON aura_preparation_jobs(state,created_at);
CREATE INDEX IF NOT EXISTS aura_preparation_jobs_owner ON aura_preparation_jobs(student_id,course_id);
