from fastapi import FastAPI
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import Json
import os
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from pgvector import Vector
from pathlib import Path

env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)
app = FastAPI()
class ChunkEmbeddingRequest(BaseModel):
    source_id: int
    topic_id: int | None = None
    content: str
    page_number: int | None = None
    slide_number: int | None = None
    timestamp_seconds: int | None = None
    metadata: dict | None = None
    embedding: list[float]
class SearchRequest(BaseModel):
    embedding: list[float]
    top_k: int = 5
def get_connection():
    connection = psycopg2.connect(
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT")
    )
    register_vector(connection)

    return connection
@app.get("/")
def home():
    return {
        "message": "Track D backend is running"
    }


@app.get("/test-db")
def test_database():
    try:
        connection = get_connection()
        cursor = connection.cursor()

        cursor.execute("SELECT current_database()")
        result = cursor.fetchone()

        cursor.close()
        connection.close()

        return {
            "database": result[0],
            "status": "connected"
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }
@app.get("/test-tables")
def test_tables():
    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)

    tables = cursor.fetchall()

    cursor.close()
    connection.close()

    return {
        "tables": [table[0] for table in tables]
    }


@app.get("/courses")
def get_courses():
    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT course_id, course_name
        FROM courses
        ORDER BY course_id;
    """)

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    courses = []

    for row in rows:
        courses.append({
            "course_id": row[0],
            "course_name": row[1]
        })

    return {
        "courses": courses
    }


@app.get("/topics/{course_id}")
def get_topics(course_id: int):
    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT topic_id, topic_name
        FROM topics
        WHERE course_id = %s
        ORDER BY topic_id;
    """, (course_id,))

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    topics = []

    for row in rows:
        topics.append({
            "topic_id": row[0],
            "topic_name": row[1]
        })

    return {
        "course_id": course_id,
        "topics": topics
    }


@app.get("/sources/{course_id}")
def get_sources(course_id: int):
    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            source_id,
            source_name,
            source_type,
            page_number,
            slide_number,
            timestamp_seconds,
            metadata
        FROM sources
        WHERE course_id = %s
        ORDER BY source_id;
    """, (course_id,))

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    sources = []

    for row in rows:
        sources.append({
            "source_id": row[0],
            "source_name": row[1],
            "source_type": row[2],
            "page_number": row[3],
            "slide_number": row[4],
            "timestamp_seconds": row[5],
            "metadata": row[6]
        })

    return {
        "course_id": course_id,
        "sources": sources
    }


@app.get("/chunks/{source_id}")
def get_chunks(source_id: int):
    connection = get_connection()

    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            chunk_id,
            topic_id,
            content,
            page_number,
            slide_number,
            timestamp_seconds,
            metadata
        FROM chunks
        WHERE source_id = %s
        ORDER BY chunk_id;
    """, (source_id,))

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    chunks = []

    for row in rows:
        chunks.append({
            "chunk_id": row[0],
            "topic_id": row[1],
            "content": row[2],
            "page_number": row[3],
            "slide_number": row[4],
            "timestamp_seconds": row[5],
            "metadata": row[6]
        })

    return {
        "source_id": source_id,
        "chunks": chunks
    }
@app.post("/search")
def search_chunks(request: SearchRequest):

    if len(request.embedding) != 1024:
        return {
            "status": "error",
            "message": "Embedding must contain exactly 1024 values"
        }

    connection = get_connection()
    cursor = connection.cursor()
    query_vector = Vector(request.embedding)

    cursor.execute("""
    SELECT
        chunk_id,
        source_id,
        topic_id,
        content,
        page_number,
        slide_number,
        timestamp_seconds,
        metadata,
        1 - (embedding <=> %s) AS similarity
    FROM chunks
    WHERE embedding IS NOT NULL
    ORDER BY embedding <=> %s
    LIMIT %s;
""", (
    query_vector,
    query_vector,
    request.top_k
))

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    results = []

    for row in rows:
        results.append({
            "chunk_id": row[0],
            "source_id": row[1],
            "topic_id": row[2],
            "content": row[3],
            "page_number": row[4],
            "slide_number": row[5],
            "timestamp_seconds": row[6],
            "metadata": row[7],
            "similarity": row[8]
        })

    return {
        "results": results
    }
@app.post("/chunks")
def store_chunk(request: ChunkEmbeddingRequest):

    if len(request.embedding) != 1024:
        return {
            "status": "error",
            "message": "Embedding must contain exactly 1024 values"
        }

    connection = get_connection()
    cursor = connection.cursor()

    chunk_vector = Vector(request.embedding)

    cursor.execute("""
        INSERT INTO chunks (
            source_id,
            topic_id,
            content,
            page_number,
            slide_number,
            timestamp_seconds,
            metadata,
            embedding
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING chunk_id;
    """, (
        request.source_id,
        request.topic_id,
        request.content,
        request.page_number,
        request.slide_number,
        request.timestamp_seconds,
        Json(request.metadata or {}),
        chunk_vector
    ))

    chunk_id = cursor.fetchone()[0]

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "stored",
        "chunk_id": chunk_id
    }
@app.get("/students/{student_id}/mastery")
def get_student_mastery(student_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            student_id,
            topic_id,
            mastery_score,
            last_updated
        FROM mastery
        WHERE student_id = %s
        ORDER BY topic_id;
    """, (student_id,))

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    mastery_data = []

    for row in rows:
        mastery_data.append({
            "student_id": row[0],
            "topic_id": row[1],
            "mastery_score": row[2],
            "last_updated": row[3]
        })

    return {
        "student_id": student_id,
        "mastery": mastery_data
    }
class QuizAttemptRequest(BaseModel):
    student_id: int
    topic_id: int
    score: int


@app.post("/quiz/attempt")
def store_quiz_attempt(request: QuizAttemptRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO quiz_attempts (
            student_id,
            topic_id,
            score
        )
        VALUES (%s, %s, %s)
        RETURNING attempt_id, attempted_at;
    """, (
        request.student_id,
        request.topic_id,
        request.score
    ))

    row = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "stored",
        "attempt_id": row[0],
        "attempted_at": row[1]
    }
class QuizAnswerRequest(BaseModel):
    attempt_id: int
    question_id: int
    student_answer: str
    is_correct: bool


@app.post("/quiz/answer")
def store_quiz_answer(request: QuizAnswerRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO answers (
            attempt_id,
            question_id,
            student_answer,
            is_correct
        )
        VALUES (%s, %s, %s, %s);
    """, (
        request.attempt_id,
        request.question_id,
        request.student_answer,
        request.is_correct
    ))

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "stored"
    }
@app.post("/quiz/attempt/{attempt_id}/update-mastery")
def update_mastery(attempt_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    # Get the student's topic and quiz score
    cursor.execute("""
        SELECT student_id, topic_id, score
        FROM quiz_attempts
        WHERE attempt_id = %s;
    """, (attempt_id,))

    attempt = cursor.fetchone()

    if attempt is None:
        cursor.close()
        connection.close()

        return {
            "status": "error",
            "message": "Quiz attempt not found"
        }

    student_id = attempt[0]
    topic_id = attempt[1]
    score = attempt[2]

    # Convert score from 0-100 to 0-1
    current_performance = score / 100.0

    # Check whether mastery already exists
    cursor.execute("""
        SELECT mastery_score
        FROM mastery
        WHERE student_id = %s
          AND topic_id = %s;
    """, (student_id, topic_id))

    existing = cursor.fetchone()

    if existing is None:

        # First attempt: use current performance
        new_mastery = current_performance

        cursor.execute("""
            INSERT INTO mastery (
                student_id,
                topic_id,
                mastery_score,
                last_updated
            )
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP);
        """, (
            student_id,
            topic_id,
            new_mastery
        ))

    else:

        old_mastery = float(existing[0])

        # Combine previous mastery with latest performance
        new_mastery = (0.7 * old_mastery) + (0.3 * current_performance)

        cursor.execute("""
            UPDATE mastery
            SET mastery_score = %s,
                last_updated = CURRENT_TIMESTAMP
            WHERE student_id = %s
              AND topic_id = %s;
        """, (
            new_mastery,
            student_id,
            topic_id
        ))

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "updated",
        "student_id": student_id,
        "topic_id": topic_id,
        "mastery_score": new_mastery
    }
@app.get("/students/{student_id}/weak-topics")
def get_weak_topics(student_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            m.topic_id,
            t.topic_name,
            m.mastery_score
        FROM mastery m
        JOIN topics t
            ON m.topic_id = t.topic_id
        WHERE m.student_id = %s
          AND m.mastery_score < 0.60
        ORDER BY m.mastery_score ASC;
    """, (student_id,))

    rows = cursor.fetchall()

    cursor.close()
    connection.close()

    weak_topics = []

    for row in rows:
        weak_topics.append({
            "topic_id": row[0],
            "topic_name": row[1],
            "mastery_score": row[2]
        })

    return {
        "student_id": student_id,
        "weak_topics": weak_topics
    }