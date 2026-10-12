-- READ ONLY: run locally in pgAdmin if you want to identify old unassigned uploads.
SELECT student_id, name, email FROM students ORDER BY student_id;
SELECT source_id, source_name, course_id, created_at
FROM sources WHERE owner_student_id IS NULL ORDER BY source_id;
