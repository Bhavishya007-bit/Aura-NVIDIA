-- Additive, rerunnable migration. The calling connection owns the transaction.
CREATE TABLE IF NOT EXISTS aura_topic_mastery (
    student_id INTEGER NOT NULL REFERENCES students(student_id),
    course_id INTEGER NOT NULL REFERENCES courses(course_id),
    topic_key TEXT NOT NULL,
    topic TEXT NOT NULL,
    mastery DOUBLE PRECISION NOT NULL DEFAULT 0.20 CHECK (mastery BETWEEN 0 AND 1),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    correct_count INTEGER NOT NULL DEFAULT 0 CHECK (correct_count BETWEEN 0 AND evidence_count),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (student_id, course_id, topic_key)
);
CREATE TABLE IF NOT EXISTS aura_learning_evidence (
    student_id INTEGER NOT NULL REFERENCES students(student_id),
    course_id INTEGER NOT NULL REFERENCES courses(course_id),
    source_id INTEGER NOT NULL REFERENCES sources(source_id),
    artifact_id UUID NOT NULL REFERENCES aura_study_artifacts(id),
    question_id TEXT NOT NULL,
    topic_key TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('assessment', 'diagnostic', 'conversation')),
    correct BOOLEAN NOT NULL,
    prior_mastery DOUBLE PRECISION NOT NULL CHECK (prior_mastery BETWEEN 0 AND 1),
    posterior_mastery DOUBLE PRECISION NOT NULL CHECK (posterior_mastery BETWEEN 0 AND 1),
    observed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (student_id, course_id, artifact_id, question_id),
    FOREIGN KEY (student_id, course_id, topic_key)
        REFERENCES aura_topic_mastery(student_id, course_id, topic_key)
);
CREATE INDEX IF NOT EXISTS aura_learning_source_topic
    ON aura_learning_evidence(student_id, course_id, source_id, topic_key);
