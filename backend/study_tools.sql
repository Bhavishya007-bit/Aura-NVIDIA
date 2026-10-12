-- Run once in pgAdmin's Query Tool for the Aura database. Existing data is preserved.
BEGIN;
CREATE TABLE IF NOT EXISTS aura_study_artifacts (
    id UUID PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(student_id),
    course_id INTEGER NOT NULL REFERENCES courses(course_id),
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    kind TEXT NOT NULL CHECK (kind IN ('notes', 'summary', 'flashcards', 'assessment')),
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS aura_study_owner_source
    ON aura_study_artifacts(student_id, course_id, source_id, created_at DESC);
CREATE TABLE IF NOT EXISTS aura_study_results (
    artifact_id UUID PRIMARY KEY REFERENCES aura_study_artifacts(id),
    student_id INTEGER NOT NULL REFERENCES students(student_id),
    result JSONB NOT NULL,
    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
COMMIT;
