from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
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
    course_id: int | None = None
    topic_id: int | None = None
class StudentRequest(BaseModel):
    name: str
    email: str    
class CourseRequest(BaseModel):
    course_name: str
class TopicRequest(BaseModel):
    course_id: int
    topic_name: str
class ConceptRequest(BaseModel):
    topic_id: int
    concept_name: str
class SourceRequest(BaseModel):
    course_id: int
    source_name: str
    source_type: str
    file_path: str | None = None
class SourceStatusRequest(BaseModel):
    status: str
class BatchChunksRequest(BaseModel):
    chunks: list[ChunkEmbeddingRequest]
class QuestionRequest(BaseModel):
    topic_id: int
    source_id: int
    concept_id: int | None = None
    chunk_id: int | None = None
    question_text: str
    difficulty: int
    correct_answer: str
    question_type: str = "MCQ"
    options: dict | None = None
    explanation: str | None = None
    verified: bool = False
    embedding: list[float] | None = None
class ConceptMasteryRequest(BaseModel):
    concept_id: int
    mastery_score: float
class ChatSessionRequest(BaseModel):
    student_id: int
    course_id: int
class ChatMessageRequest(BaseModel):
    session_id: int
    role: str
    content: str
    sources: list | None = None
class LearnerEventRequest(BaseModel):
    student_id: int
    concept_id: int | None = None
    event_type: str
    signal: float | None = None
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

    query = """
        SELECT
            chunks.chunk_id,
            chunks.source_id,
            chunks.topic_id,
            chunks.content,
            chunks.page_number,
            chunks.slide_number,
            chunks.timestamp_seconds,
            chunks.metadata,
            sources.source_name,
            sources.source_type,
            1 - (chunks.embedding <=> %s) AS similarity
        FROM chunks
        JOIN sources
            ON chunks.source_id = sources.source_id
        WHERE chunks.embedding IS NOT NULL
    """

    parameters = [query_vector]

    if request.course_id is not None:
        query += " AND sources.course_id = %s"
        parameters.append(request.course_id)

    if request.topic_id is not None:
        query += " AND chunks.topic_id = %s"
        parameters.append(request.topic_id)

    query += """
        ORDER BY chunks.embedding <=> %s
        LIMIT %s;
    """

    parameters.append(query_vector)
    parameters.append(request.top_k)

    cursor.execute(query, parameters)

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
            "source_name": row[8],
            "source_type": row[9],
            "similarity": row[10]
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


@app.post("/quiz/answer")
def store_quiz_answer(request: QuizAnswerRequest):

    connection = get_connection()
    cursor = connection.cursor()

    # Get the correct answer from the database
    cursor.execute("""
        SELECT correct_answer
        FROM questions
        WHERE question_id = %s;
    """, (request.question_id,))

    question = cursor.fetchone()

    if question is None:
        cursor.close()
        connection.close()

        return {
            "status": "error",
            "message": "Question not found"
        }

    correct_answer = question[0]

    # Check the student's answer
    is_correct = (
        request.student_answer.strip().lower()
        == correct_answer.strip().lower()
    )

    # Store the answer and backend-calculated result
    cursor.execute("""
        INSERT INTO answers (
            attempt_id,
            question_id,
            student_answer,
            is_correct
        )
        VALUES (%s, %s, %s, %s)
        RETURNING answer_id;
    """, (
        request.attempt_id,
        request.question_id,
        request.student_answer,
        is_correct
    ))

    answer_id = cursor.fetchone()[0]

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "stored",
        "answer_id": answer_id,
        "is_correct": is_correct
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
@app.post("/students")
def create_student(request: StudentRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO students (name, email)
        VALUES (%s, %s)
        RETURNING student_id, name, email;
    """, (
        request.name,
        request.email
    ))

    student = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "student_id": student[0],
        "name": student[1],
        "email": student[2]
    }
@app.post("/courses")
def create_course(request: CourseRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO courses (course_name)
        VALUES (%s)
        RETURNING course_id, course_name;
    """, (
        request.course_name,
    ))

    course = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "course_id": course[0],
        "course_name": course[1]
    }
@app.post("/topics")
def create_topic(request: TopicRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO topics (course_id, topic_name)
        VALUES (%s, %s)
        RETURNING topic_id, course_id, topic_name;
    """, (
        request.course_id,
        request.topic_name
    ))

    topic = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "topic_id": topic[0],
        "course_id": topic[1],
        "topic_name": topic[2]
    }
@app.post("/concepts")
def create_concept(request: ConceptRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO concepts (topic_id, concept_name)
        VALUES (%s, %s)
        RETURNING concept_id, topic_id, concept_name;
    """, (
        request.topic_id,
        request.concept_name
    ))

    concept = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "concept_id": concept[0],
        "topic_id": concept[1],
        "concept_name": concept[2]
    }
@app.post("/sources")
def create_source(request: SourceRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO sources (
            course_id,
            source_name,
            source_type,
            file_path
        )
        VALUES (%s, %s, %s, %s)
        RETURNING source_id, course_id, source_name, source_type, file_path, status;
    """, (
        request.course_id,
        request.source_name,
        request.source_type,
        request.file_path
    ))

    source = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "source_id": source[0],
        "course_id": source[1],
        "source_name": source[2],
        "source_type": source[3],
        "file_path": source[4],
        "source_status": source[5]
    }
@app.put("/sources/{source_id}/status")
def update_source_status(source_id: int, request: SourceStatusRequest):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            UPDATE sources
            SET status = %s
            WHERE source_id = %s
            RETURNING source_id, source_name, status;
        """, (
            request.status,
            source_id
        ))

        source = cursor.fetchone()

        if source is None:
            connection.rollback()
            raise HTTPException(
                status_code=404,
                detail="Source not found"
            )

        connection.commit()

        return {
            "status": "updated",
            "source_id": source[0],
            "source_name": source[1],
            "source_status": source[2]
        }

    except HTTPException:
        raise

    except Exception as e:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Database operation failed"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/chunks/batch")
def create_chunks_batch(request: BatchChunksRequest):

    connection = get_connection()
    cursor = connection.cursor()

    inserted_chunks = []

    for chunk in request.chunks:

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
            chunk.source_id,
            chunk.topic_id,
            chunk.content,
            chunk.page_number,
            chunk.slide_number,
            chunk.timestamp_seconds,
            Json(chunk.metadata) if chunk.metadata else None,
            Vector(chunk.embedding)
        ))

        chunk_id = cursor.fetchone()[0]

        inserted_chunks.append(chunk_id)

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "inserted_count": len(inserted_chunks),
        "chunk_ids": inserted_chunks
    }
@app.post("/questions")
def create_question(request: QuestionRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO questions (
            topic_id,
            source_id,
            concept_id,
            chunk_id,
            question_text,
            difficulty,
            correct_answer,
            question_type,
            options,
            explanation,
            verified,
            embedding
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING question_id;
    """, (
        request.topic_id,
        request.source_id,
        request.concept_id,
        request.chunk_id,
        request.question_text,
        request.difficulty,
        request.correct_answer,
        request.question_type,
        Json(request.options) if request.options else None,
        request.explanation,
        request.verified,
        Vector(request.embedding) if request.embedding else None
    ))

    question_id = cursor.fetchone()[0]

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "question_id": question_id
    }
@app.get("/questions")
def get_questions(
    topic_id: int | None = None,
    concept_id: int | None = None,
    difficulty: int | None = None,
    student_id: int | None = None
):

    connection = get_connection()
    cursor = connection.cursor()

    query = """
        SELECT
            question_id,
            topic_id,
            source_id,
            concept_id,
            chunk_id,
            question_text,
            difficulty,
            question_type,
            options,
            explanation,
            verified
        FROM questions
        WHERE 1 = 1
    """

    parameters = []

    # Filter by topic
    if topic_id is not None:
        query += " AND topic_id = %s"
        parameters.append(topic_id)

    # Filter by concept
    if concept_id is not None:
        query += " AND concept_id = %s"
        parameters.append(concept_id)

    # Filter by difficulty
    if difficulty is not None:
        query += " AND difficulty = %s"
        parameters.append(difficulty)

    # Exclude questions already answered by this student
    if student_id is not None:
        query += """
            AND NOT EXISTS (
                SELECT 1
                FROM answers a
                JOIN quiz_attempts qa
                    ON a.attempt_id = qa.attempt_id
                WHERE qa.student_id = %s
                  AND a.question_id = questions.question_id
            )
        """
        parameters.append(student_id)

    query += " ORDER BY question_id;"

    cursor.execute(query, parameters)

    questions = cursor.fetchall()

    cursor.close()
    connection.close()

    return [
        {
            "question_id": row[0],
            "topic_id": row[1],
            "source_id": row[2],
            "concept_id": row[3],
            "chunk_id": row[4],
            "question_text": row[5],
            "difficulty": row[6],
            "question_type": row[7],
            "options": row[8],
            "explanation": row[9],
            "verified": row[10]
        }
        for row in questions
    ]
@app.get("/students/{student_id}/question-history")
def get_student_question_history(student_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            q.question_id,
            q.question_text,
            q.topic_id,
            a.is_correct,
            a.answered_at
        FROM answers a
        JOIN quiz_attempts qa
            ON a.attempt_id = qa.attempt_id
        JOIN questions q
            ON a.question_id = q.question_id
        WHERE qa.student_id = %s
        ORDER BY a.answered_at DESC;
    """, (student_id,))

    history = cursor.fetchall()

    cursor.close()
    connection.close()

    return [
        {
            "question_id": row[0],
            "question_text": row[1],
            "topic_id": row[2],
            "is_correct": row[3],
            "answered_at": row[4]
        }
        for row in history
    ]
@app.get("/concepts/{concept_id}/prerequisites")
def get_concept_prerequisites(concept_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            c.concept_id,
            c.concept_name
        FROM concept_prerequisites cp
        JOIN concepts c
            ON cp.prerequisite_id = c.concept_id
        WHERE cp.concept_id = %s;
    """, (concept_id,))

    prerequisites = cursor.fetchall()

    cursor.close()
    connection.close()

    return [
        {
            "concept_id": row[0],
            "concept_name": row[1]
        }
        for row in prerequisites
    ]
@app.get("/concepts")
def get_concepts():

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            concept_id,
            topic_id,
            concept_name
        FROM concepts
        ORDER BY concept_id;
    """)

    concepts = cursor.fetchall()

    cursor.close()
    connection.close()

    return [
        {
            "concept_id": row[0],
            "topic_id": row[1],
            "concept_name": row[2]
        }
        for row in concepts
    ]
@app.get("/students/{student_id}/concept-mastery")
def get_concept_mastery(student_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            cm.concept_id,
            c.concept_name,
            cm.mastery_score,
            cm.last_updated
        FROM concept_mastery cm
        JOIN concepts c
            ON cm.concept_id = c.concept_id
        WHERE cm.student_id = %s
        ORDER BY cm.mastery_score ASC;
    """, (student_id,))

    mastery = cursor.fetchall()

    cursor.close()
    connection.close()

    return [
        {
            "concept_id": row[0],
            "concept_name": row[1],
            "mastery_score": row[2],
            "last_updated": row[3]
        }
        for row in mastery
    ]
@app.put("/students/{student_id}/concept-mastery")
def update_concept_mastery(
    student_id: int,
    request: ConceptMasteryRequest
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO concept_mastery (
            student_id,
            concept_id,
            mastery_score
        )
        VALUES (%s, %s, %s)
        ON CONFLICT (student_id, concept_id)
        DO UPDATE SET
            mastery_score = EXCLUDED.mastery_score,
            last_updated = CURRENT_TIMESTAMP
        RETURNING student_id, concept_id, mastery_score, last_updated;
    """, (
        student_id,
        request.concept_id,
        request.mastery_score
    ))

    mastery = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "updated",
        "student_id": mastery[0],
        "concept_id": mastery[1],
        "mastery_score": mastery[2],
        "last_updated": mastery[3]
    }
@app.post("/students/{student_id}/concept-mastery/history")
def record_mastery_history(
    student_id: int,
    request: ConceptMasteryRequest
):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO mastery_history (
            student_id,
            concept_id,
            mastery_score
        )
        VALUES (%s, %s, %s)
        RETURNING id, student_id, concept_id, mastery_score, recorded_at;
    """, (
        student_id,
        request.concept_id,
        request.mastery_score
    ))

    history = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "recorded",
        "history_id": history[0],
        "student_id": history[1],
        "concept_id": history[2],
        "mastery_score": history[3],
        "recorded_at": history[4]
    }
@app.get("/students/{student_id}/concept-mastery/history")
def get_mastery_history(student_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            mh.id,
            mh.concept_id,
            c.concept_name,
            mh.mastery_score,
            mh.recorded_at
        FROM mastery_history mh
        JOIN concepts c
            ON mh.concept_id = c.concept_id
        WHERE mh.student_id = %s
        ORDER BY mh.recorded_at ASC;
    """, (student_id,))

    history = cursor.fetchall()

    cursor.close()
    connection.close()

    return [
        {
            "history_id": row[0],
            "concept_id": row[1],
            "concept_name": row[2],
            "mastery_score": row[3],
            "recorded_at": row[4]
        }
        for row in history
    ]
@app.post("/chat/sessions")
def create_chat_session(request: ChatSessionRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO chat_sessions (
            student_id,
            course_id
        )
        VALUES (%s, %s)
        RETURNING session_id, student_id, course_id, created_at;
    """, (
        request.student_id,
        request.course_id
    ))

    session = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "session_id": session[0],
        "student_id": session[1],
        "course_id": session[2],
        "created_at": session[3]
    }
@app.post("/chat/messages")
def create_chat_message(request: ChatMessageRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO chat_messages (
            session_id,
            role,
            content,
            sources
        )
        VALUES (%s, %s, %s, %s)
        RETURNING message_id, session_id, role, content, sources, created_at;
    """, (
        request.session_id,
        request.role,
        request.content,
        Json(request.sources) if request.sources else None
    ))

    message = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "message_id": message[0],
        "session_id": message[1],
        "role": message[2],
        "content": message[3],
        "sources": message[4],
        "created_at": message[5]
    }
@app.get("/chat/sessions/{session_id}/messages")
def get_chat_messages(session_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            message_id,
            session_id,
            role,
            content,
            sources,
            created_at
        FROM chat_messages
        WHERE session_id = %s
        ORDER BY created_at ASC;
    """, (session_id,))

    messages = cursor.fetchall()

    cursor.close()
    connection.close()

    return [
        {
            "message_id": row[0],
            "session_id": row[1],
            "role": row[2],
            "content": row[3],
            "sources": row[4],
            "created_at": row[5]
        }
        for row in messages
    ]
@app.post("/learner-events")
def create_learner_event(request: LearnerEventRequest):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        INSERT INTO learner_events (
            student_id,
            concept_id,
            event_type,
            signal
        )
        VALUES (%s, %s, %s, %s)
        RETURNING event_id, student_id, concept_id, event_type, signal, created_at;
    """, (
        request.student_id,
        request.concept_id,
        request.event_type,
        request.signal
    ))

    event = cursor.fetchone()

    connection.commit()

    cursor.close()
    connection.close()

    return {
        "status": "created",
        "event_id": event[0],
        "student_id": event[1],
        "concept_id": event[2],
        "event_type": event[3],
        "signal": event[4],
        "created_at": event[5]
    }
@app.get("/students/{student_id}/learner-events")
def get_learner_events(student_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    cursor.execute("""
        SELECT
            event_id,
            concept_id,
            event_type,
            signal,
            created_at
        FROM learner_events
        WHERE student_id = %s
        ORDER BY created_at DESC;
    """, (student_id,))

    events = cursor.fetchall()

    cursor.close()
    connection.close()

    return [
        {
            "event_id": row[0],
            "concept_id": row[1],
            "event_type": row[2],
            "signal": row[3],
            "created_at": row[4]
        }
        for row in events
    ]