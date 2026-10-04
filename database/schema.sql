CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE students (
    student_id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150)
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

CREATE TABLE sources (
    source_id SERIAL PRIMARY KEY,
    course_id INT REFERENCES courses(course_id),
    source_name VARCHAR(200) NOT NULL,
    source_type VARCHAR(50) NOT NULL,
    page_number INT,
    slide_number INT,
    timestamp_seconds INT,
    metadata JSONB
);

CREATE TABLE questions (
    question_id SERIAL PRIMARY KEY,
    topic_id INT REFERENCES topics(topic_id),
    source_id INT REFERENCES sources(source_id),
    question_text TEXT NOT NULL,
    difficulty VARCHAR(50),
    correct_answer TEXT
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
    is_correct BOOLEAN
);

CREATE TABLE mastery (
    student_id INT REFERENCES students(student_id),
    topic_id INT REFERENCES topics(topic_id),
    mastery_score FLOAT,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (student_id, topic_id)
);

CREATE TABLE chunks (
    chunk_id SERIAL PRIMARY KEY,
    source_id INT REFERENCES sources(source_id),
    topic_id INT REFERENCES topics(topic_id),
    content TEXT NOT NULL,
    page_number INT,
    slide_number INT,
    timestamp_seconds INT,
    metadata JSONB,
    embedding VECTOR(1024)
);