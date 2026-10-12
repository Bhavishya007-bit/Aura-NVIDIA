-- OPTIONAL, MANUAL RECOVERY ONLY. Run after private_workspaces.sql.
-- Set the ORIGINAL uploader's account email and explicitly confirmed source IDs.
-- Empty defaults deliberately prevent accidental bulk assignment.
DO $$
DECLARE
    original_email TEXT := 'REPLACE_WITH_ORIGINAL_ACCOUNT_EMAIL';
    confirmed_source_ids INTEGER[] := ARRAY[]::INTEGER[];
    account_id INTEGER;
    workspace_id INTEGER;
BEGIN
    IF cardinality(confirmed_source_ids) = 0 THEN
        RAISE EXCEPTION 'Set explicitly confirmed source IDs before running this recovery script.';
    END IF;
    SELECT student_id INTO STRICT account_id FROM students WHERE lower(email) = lower(original_email);
    IF EXISTS (SELECT 1 FROM sources WHERE source_id = ANY(confirmed_source_ids)
               AND owner_student_id IS NOT NULL AND owner_student_id <> account_id) THEN
        RAISE EXCEPTION 'A selected material already belongs to another account; nothing was moved.';
    END IF;
    INSERT INTO courses(course_name,owner_student_id) VALUES ('My study materials',account_id)
    ON CONFLICT(owner_student_id) DO UPDATE SET course_name=courses.course_name
    RETURNING course_id INTO workspace_id;
    UPDATE sources SET owner_student_id=account_id,course_id=workspace_id
    WHERE source_id=ANY(confirmed_source_ids) AND (owner_student_id IS NULL OR owner_student_id=account_id);
    UPDATE aura_study_artifacts SET course_id=workspace_id
    WHERE source_id=ANY(confirmed_source_ids) AND student_id=account_id;
END $$;
