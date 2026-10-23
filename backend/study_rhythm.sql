-- Additive and idempotent; the caller owns the startup transaction.
CREATE TABLE IF NOT EXISTS aura_study_rhythm_settings (
 student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
 course_id INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
 enabled BOOLEAN NOT NULL DEFAULT FALSE,
 timezone TEXT NOT NULL DEFAULT 'UTC',
 daily_hour INTEGER NOT NULL DEFAULT 9 CHECK(daily_hour BETWEEN 0 AND 23),
 checked_at TIMESTAMPTZ,
 PRIMARY KEY(student_id,course_id)
);
CREATE TABLE IF NOT EXISTS aura_review_events (
 student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
 course_id INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
 artifact_id UUID NOT NULL REFERENCES aura_study_artifacts(id) ON DELETE CASCADE,
 source_id INTEGER NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
 topic_key TEXT NOT NULL,
 PRIMARY KEY(student_id,course_id,artifact_id,topic_key)
);
CREATE TABLE IF NOT EXISTS aura_review_schedule (
 student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
 course_id INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
 source_id INTEGER NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
 topic_key TEXT NOT NULL, topic TEXT NOT NULL,
 streak INTEGER NOT NULL DEFAULT 0 CHECK(streak BETWEEN 0 AND 5),
 last_observed_at TIMESTAMPTZ NOT NULL,
 due_at TIMESTAMPTZ NOT NULL,
 PRIMARY KEY(student_id,course_id,source_id,topic_key)
);
CREATE INDEX IF NOT EXISTS aura_review_due ON aura_review_schedule(student_id,course_id,due_at);
CREATE TABLE IF NOT EXISTS aura_study_digests (
 id UUID PRIMARY KEY, student_id INTEGER NOT NULL REFERENCES students(student_id) ON DELETE CASCADE,
 course_id INTEGER NOT NULL REFERENCES courses(course_id) ON DELETE CASCADE,
 local_date DATE NOT NULL, payload JSONB NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
 UNIQUE(student_id,course_id,local_date)
);
