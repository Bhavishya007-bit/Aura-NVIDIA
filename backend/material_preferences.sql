-- Run once in the Aura database using pgAdmin Query Tool (F5).
-- Adds per-student archive preferences. No existing content is deleted.
BEGIN;
CREATE TABLE IF NOT EXISTS aura_material_preferences (
    student_id INTEGER NOT NULL REFERENCES students(student_id),
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (student_id, source_id)
);
COMMIT;
