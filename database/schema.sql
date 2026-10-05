CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE students (
    student_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) UNIQUE
);

CREATE TABLE courses (
    course_id SERIAL PRIMARY KEY,
    course_name VARCHAR(150) NOT NULL
);

CREATE TABLE topics (
    topic_id SERIAL PRIMARY KEY,
    course_id INT REFERENCES courses(course_id),
    topic_name VARCHAR(150) NOT NULL
);

CREATE TABLE concepts (
    concept_id SERIAL PRIMARY KEY,
    topic_id INT REFERENCES topics(topic_id) ON DELETE CASCADE,
    concept_name VARCHAR(150) NOT NULL
);

CREATE TABLE concept_prerequisites (
    concept_id INT REFERENCES concepts(concept_id) ON DELETE CASCADE,
    prerequisite_id INT REFERENCES concepts(concept_id) ON DELETE CASCADE,
    PRIMARY KEY (concept_id, prerequisite_id)
);

CREATE TABLE sources (
    source_id SERIAL PRIMARY KEY,
    course_id INT REFERENCES courses(course_id),
    source_name VARCHAR(200) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    page_number INT,
    slide_number INT,
    timestamp_seconds INT,
    metadata JSONB,
    file_path TEXT,
    status VARCHAR(30) DEFAULT 'UPLOADED',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chunks (
    chunk_id SERIAL PRIMARY KEY,
    source_id INT REFERENCES sources(source_id),
    topic_id INT REFERENCES topics(topic_id),
    concept_id INT REFERENCES concepts(concept_id),
    content TEXT NOT NULL,
    page_number INT,
    slide_number INT,
    timestamp_seconds INT,
    timestamp_end INT,
    metadata JSONB,
    embedding VECTOR(1024)
);

CREATE TABLE questions (
    question_id SERIAL PRIMARY KEY,
    topic_id INT REFERENCES topics(topic_id),
    source_id INT REFERENCES sources(source_id),
    concept_id INT REFERENCES concepts(concept_id),
    chunk_id INT REFERENCES chunks(chunk_id),
    question_text TEXT NOT NULL,
    difficulty SMALLINT CHECK (difficulty BETWEEN 1 AND 5),
    correct_answer TEXT,
    question_type VARCHAR(20) DEFAULT 'MCQ',
    options JSONB,
    explanation TEXT,
    verified BOOLEAN DEFAULT FALSE,
    embedding VECTOR(1024),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE quiz_attempts (
    attempt_id SERIAL PRIMARY KEY,
    student_id INT REFERENCES students(student_id),
    topic_id INT REFERENCES topics(topic_id),
    score INT,
    attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE answers (
    answer_id SERIAL PRIMARY KEY,
    attempt_id INT REFERENCES quiz_attempts(attempt_id),
    question_id INT REFERENCES questions(question_id),
    student_answer TEXT,
    is_correct BOOLEAN,
    answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE mastery (
    student_id INT REFERENCES students(student_id),
    topic_id INT REFERENCES topics(topic_id),
    mastery_score FLOAT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, topic_id)
);

CREATE TABLE concept_mastery (
    student_id INT REFERENCES students(student_id),
    concept_id INT REFERENCES concepts(concept_id),
    mastery_score FLOAT NOT NULL,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, concept_id)
);

CREATE TABLE mastery_history (
    id SERIAL PRIMARY KEY,
    student_id INT REFERENCES students(student_id),
    concept_id INT REFERENCES concepts(concept_id),
    mastery_score FLOAT NOT NULL,
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chat_sessions (
    session_id SERIAL PRIMARY KEY,
    student_id INT REFERENCES students(student_id),
    course_id INT REFERENCES courses(course_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE chat_messages (
    message_id SERIAL PRIMARY KEY,
    session_id INT REFERENCES chat_sessions(session_id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    sources JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


CREATE TABLE learner_events (
    event_id SERIAL PRIMARY KEY,
    student_id INT REFERENCES students(student_id),
    concept_id INT REFERENCES concepts(concept_id),
    event_type VARCHAR(30) NOT NULL,
    signal FLOAT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX chunks_embedding_idx
ON chunks
USING hnsw (embedding vector_cosine_ops);

CREATE INDEX chunks_source_idx
ON chunks(source_id);

CREATE INDEX chunks_topic_idx
ON chunks(topic_id);

CREATE INDEX sources_course_idx
ON sources(course_id);

CREATE INDEX answers_attempt_idx
ON answers(attempt_id);