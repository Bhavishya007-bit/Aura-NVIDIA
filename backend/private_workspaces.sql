-- Run ONCE in pgAdmin Query Tool for your existing local Aura database.
-- Do not guess ownership of old shared records. They remain stored and unassigned.
BEGIN;
ALTER TABLE courses ADD COLUMN IF NOT EXISTS owner_student_id INTEGER REFERENCES students(student_id);
ALTER TABLE sources ADD COLUMN IF NOT EXISTS owner_student_id INTEGER REFERENCES students(student_id);
CREATE UNIQUE INDEX IF NOT EXISTS aura_private_course_owner ON courses(owner_student_id);
CREATE INDEX IF NOT EXISTS aura_source_owner_course ON sources(owner_student_id,course_id);
CREATE UNIQUE INDEX IF NOT EXISTS aura_course_identity_owner ON courses(course_id,owner_student_id);
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='aura_source_course_owner_fk' AND conrelid='sources'::regclass) THEN
        ALTER TABLE sources ADD CONSTRAINT aura_source_course_owner_fk
            FOREIGN KEY(course_id,owner_student_id) REFERENCES courses(course_id,owner_student_id);
    END IF;
END $$;
-- Advance local SERIAL sequences past any manually imported IDs.
SELECT setval(pg_get_serial_sequence('courses','course_id'),GREATEST(COALESCE((SELECT MAX(course_id) FROM courses),0)+1,1),FALSE);
SELECT setval(pg_get_serial_sequence('sources','source_id'),GREATEST(COALESCE((SELECT MAX(source_id) FROM sources),0)+1,1),FALSE);
COMMIT;
