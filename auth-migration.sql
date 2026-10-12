-- Run against your existing Aura database only if auth setup is incomplete.
-- Existing student records remain; passwordless records cannot log in.
BEGIN;
ALTER TABLE students ADD COLUMN IF NOT EXISTS password_hash TEXT;
-- This deliberately fails if duplicate emails exist, so they can be resolved
-- explicitly rather than merging or deleting student accounts.
CREATE UNIQUE INDEX IF NOT EXISTS aura_students_email_lower_unique
    ON students (LOWER(email));
COMMIT;
