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
    concept_id: int | None = None
    content: str
    page_number: int | None = None
    slide_number: int | None = None
    timestamp_seconds: int | None = None
    timestamp_end: int | None = None
    metadata: dict | None = None
    embedding: list[float] | None = None

class SearchRequest(BaseModel):
    embedding: list[float]
    top_k: int = 5
    course_id: int | None = None
    topic_id: int | None = None
    concept_id: int | None = None
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
class ChunkEmbeddingUpdateRequest(BaseModel):
    embedding: list[float]
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

    try:
        cursor.execute("""
            SELECT
                source_id,
                source_name,
                source_type,
                file_path,
                status,
                created_at
            FROM sources
            WHERE course_id = %s
            ORDER BY source_id;
        """, (course_id,))

        rows = cursor.fetchall()

        sources = []

        for row in rows:
            sources.append({
                "source_id": row[0],
                "source_name": row[1],
                "source_type": row[2],
                "file_path": row[3],
                "status": row[4],
                "created_at": row[5]
            })

        return {
            "course_id": course_id,
            "sources": sources
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch sources"
        )

    finally:
        cursor.close()
        connection.close()
@app.get("/chunks/{source_id}")
def get_chunks(source_id: int):
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT
                chunk_id,
                topic_id,
                concept_id,
                content,
                page_number,
                slide_number,
                timestamp_seconds,
                timestamp_end,
                metadata
            FROM chunks
            WHERE source_id = %s
            ORDER BY chunk_id;
        """, (source_id,))

        rows = cursor.fetchall()

        chunks = []

        for row in rows:
            chunks.append({
                "chunk_id": row[0],
                "topic_id": row[1],
                "concept_id": row[2],
                "content": row[3],
                "page_number": row[4],
                "slide_number": row[5],
                "timestamp_seconds": row[6],
                "timestamp_end": row[7],
                "metadata": row[8]
            })

        return {
            "source_id": source_id,
            "chunks": chunks
        }

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch chunks"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/search")
def search_chunks(request: SearchRequest):

    # Validate embedding dimension
    if len(request.embedding) != 1024:
        raise HTTPException(
            status_code=422,
            detail="Embedding must contain exactly 1024 values"
        )

    connection = get_connection()
    cursor = connection.cursor()

    try:
        query_vector = Vector(request.embedding)

        query = """
            SELECT
                chunks.chunk_id,
                chunks.source_id,
                chunks.topic_id,
                chunks.concept_id,
                chunks.content,
                chunks.page_number,
                chunks.slide_number,
                chunks.timestamp_seconds,
                chunks.timestamp_end,
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

        # Filter by course
        if request.course_id is not None:
            query += " AND sources.course_id = %s"
            parameters.append(request.course_id)

        # Filter by topic
        if request.topic_id is not None:
            query += " AND chunks.topic_id = %s"
            parameters.append(request.topic_id)

        # Filter by concept
        if request.concept_id is not None:
            query += " AND chunks.concept_id = %s"
            parameters.append(request.concept_id)

        query += """
            ORDER BY chunks.embedding <=> %s
            LIMIT %s;
        """

        parameters.append(query_vector)
        parameters.append(request.top_k)

        cursor.execute(query, parameters)

        rows = cursor.fetchall()

        results = []

        for row in rows:
            results.append({
                "chunk_id": row[0],
                "source_id": row[1],
                "topic_id": row[2],
                "concept_id": row[3],
                "content": row[4],
                "page_number": row[5],
                "slide_number": row[6],
                "timestamp_seconds": row[7],
                "timestamp_end": row[8],
                "metadata": row[9],
                "source_name": row[10],
                "source_type": row[11],
                "similarity": row[12]
            })

        return {
            "results": results
        }

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Search operation failed"
        )

    finally:
        cursor.close()
        connection.close()
@app.get("/students/{student_id}/mastery")
def get_student_mastery(student_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Check that student exists
        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s;
        """, (student_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        # Get current topic-level mastery
        cursor.execute("""
            SELECT
                m.student_id,
                m.topic_id,
                t.topic_name,
                m.mastery_score,
                m.last_updated
            FROM mastery m
            JOIN topics t
                ON m.topic_id = t.topic_id
            WHERE m.student_id = %s
            ORDER BY m.topic_id;
        """, (student_id,))

        rows = cursor.fetchall()

        mastery = []

        for row in rows:
            mastery.append({
                "student_id": row[0],
                "topic_id": row[1],
                "topic_name": row[2],
                "mastery_score": float(row[3]),
                "last_updated": row[4]
            })

        return {
            "student_id": student_id,
            "mastery": mastery
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch student mastery"
        )

    finally:
        cursor.close()
        connection.close()
class QuizAttemptRequest(BaseModel):
    student_id: int
    topic_id: int
    score: int | None = None


@app.post("/quiz/attempt")
def store_quiz_attempt(request: QuizAttemptRequest):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Check that the student exists
        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s;
        """, (request.student_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        # Check that the topic exists
        cursor.execute("""
            SELECT topic_id
            FROM topics
            WHERE topic_id = %s;
        """, (request.topic_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Topic not found"
            )

        # Validate score if supplied
        if request.score is not None:
            if request.score < 0 or request.score > 100:
                raise HTTPException(
                    status_code=422,
                    detail="Score must be between 0 and 100"
                )

        # Create quiz attempt
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

        return {
            "status": "stored",
            "attempt_id": row[0],
            "attempted_at": row[1]
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create quiz attempt"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/quiz/attempt/{attempt_id}/complete")
def complete_quiz_attempt(attempt_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Check that the attempt exists
        cursor.execute("""
            SELECT attempt_id, score
            FROM quiz_attempts
            WHERE attempt_id = %s;
        """, (attempt_id,))

        attempt = cursor.fetchone()

        if attempt is None:
            raise HTTPException(
                status_code=404,
                detail="Quiz attempt not found"
            )

        existing_score = attempt[1]

        # Prevent completing the same attempt twice
        if existing_score is not None:
            raise HTTPException(
                status_code=400,
                detail="Quiz attempt is already completed"
            )

        # Count total answers and correct answers
        cursor.execute("""
            SELECT
                COUNT(*) AS total_questions,
                COUNT(*) FILTER (WHERE is_correct = TRUE) AS correct_answers
            FROM answers
            WHERE attempt_id = %s;
        """, (attempt_id,))

        total_questions, correct_answers = cursor.fetchone()

        if total_questions == 0:
            raise HTTPException(
                status_code=400,
                detail="No answers found for this quiz attempt"
            )

        # Calculate percentage score
        score = round((correct_answers / total_questions) * 100)

        # Save the calculated score
        cursor.execute("""
            UPDATE quiz_attempts
            SET score = %s
            WHERE attempt_id = %s;
        """, (score, attempt_id))

        connection.commit()

        return {
            "status": "completed",
            "attempt_id": attempt_id,
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "score": score
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to complete quiz attempt"
        )

    finally:
        cursor.close()
        connection.close()
class QuizAnswerRequest(BaseModel):
    attempt_id: int
    question_id: int
    student_answer: str


@app.post("/quiz/answer")
def store_quiz_answer(request: QuizAnswerRequest):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Check that the quiz attempt exists
        cursor.execute("""
            SELECT attempt_id, score
            FROM quiz_attempts
            WHERE attempt_id = %s;
        """, (request.attempt_id,))

        attempt = cursor.fetchone()

        if attempt is None:
            raise HTTPException(
                status_code=404,
                detail="Quiz attempt not found"
            )

        # Do not allow answers after quiz completion
        if attempt[1] is not None:
            raise HTTPException(
                status_code=400,
                detail="Quiz attempt is already completed"
            )

        # Check that the question exists and get its correct answer
        cursor.execute("""
            SELECT correct_answer
            FROM questions
            WHERE question_id = %s;
        """, (request.question_id,))

        question = cursor.fetchone()

        if question is None:
            raise HTTPException(
                status_code=404,
                detail="Question not found"
            )

        correct_answer = question[0]

        # Make sure the question has a correct answer
        if correct_answer is None:
            raise HTTPException(
                status_code=500,
                detail="Question does not have a correct answer"
            )

        # Check whether this question was already answered
        cursor.execute("""
            SELECT answer_id
            FROM answers
            WHERE attempt_id = %s
              AND question_id = %s;
        """, (
            request.attempt_id,
            request.question_id
        ))

        existing_answer = cursor.fetchone()

        if existing_answer is not None:
            raise HTTPException(
                status_code=409,
                detail="Question has already been answered in this quiz attempt"
            )

        # Check the student's answer
        is_correct = (
            request.student_answer.strip().lower()
            == correct_answer.strip().lower()
        )

        # Store the answer
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

        return {
            "status": "stored",
            "answer_id": answer_id,
            "is_correct": is_correct
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to store quiz answer"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/quiz/attempt/{attempt_id}/update-mastery")
def update_mastery(attempt_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # 1. Get the quiz attempt
        cursor.execute("""
            SELECT student_id, topic_id, score
            FROM quiz_attempts
            WHERE attempt_id = %s;
        """, (attempt_id,))

        attempt = cursor.fetchone()

        if attempt is None:
            raise HTTPException(
                status_code=404,
                detail="Quiz attempt not found"
            )

        student_id = attempt[0]
        topic_id = attempt[1]
        score = attempt[2]

        # 2. Quiz must be completed first
        if score is None:
            raise HTTPException(
                status_code=400,
                detail="Quiz attempt has not been completed yet"
            )

        current_performance = float(score) / 100.0

        # 3. Find all concepts tested in this quiz attempt
        cursor.execute("""
            SELECT DISTINCT q.concept_id
            FROM answers a
            JOIN questions q
                ON a.question_id = q.question_id
            WHERE a.attempt_id = %s
              AND q.concept_id IS NOT NULL;
        """, (attempt_id,))

        concept_rows = cursor.fetchall()

        if not concept_rows:
            raise HTTPException(
                status_code=400,
                detail="No concepts found for this quiz attempt"
            )

        updated_concepts = []

        # 4. Update mastery for every concept
        for row in concept_rows:

            concept_id = row[0]

            # Check existing concept mastery
            cursor.execute("""
                SELECT mastery_score
                FROM concept_mastery
                WHERE student_id = %s
                  AND concept_id = %s;
            """, (
                student_id,
                concept_id
            ))

            existing = cursor.fetchone()

            if existing is None:

                # First attempt for this concept
                new_mastery = current_performance

                cursor.execute("""
                    INSERT INTO concept_mastery (
                        student_id,
                        concept_id,
                        mastery_score
                    )
                    VALUES (%s, %s, %s);
                """, (
                    student_id,
                    concept_id,
                    new_mastery
                ))

                previous_mastery = None

            else:

                previous_mastery = float(existing[0])

                # Combine previous mastery with latest performance
                new_mastery = (
                    (0.7 * previous_mastery)
                    + (0.3 * current_performance)
                )

                cursor.execute("""
                    UPDATE concept_mastery
                    SET mastery_score = %s
                    WHERE student_id = %s
                      AND concept_id = %s;
                """, (
                    new_mastery,
                    student_id,
                    concept_id
                ))

            # 5. Save mastery history
            cursor.execute("""
                INSERT INTO mastery_history (
                    student_id,
                    concept_id,
                    mastery_score,
                    recorded_at
                )
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP);
            """, (
                student_id,
                concept_id,
                new_mastery
            ))

            updated_concepts.append({
                "concept_id": concept_id,
                "previous_mastery": previous_mastery,
                "current_performance": current_performance,
                "mastery_score": new_mastery
            })

        connection.commit()

        return {
            "status": "updated",
            "student_id": student_id,
            "attempt_id": attempt_id,
            "updated_concepts": updated_concepts
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update mastery"
        )

    finally:
        cursor.close()
        connection.close()
@app.get("/students/{student_id}/weak-topics")
def get_weak_topics(
    student_id: int,
    threshold: float = 0.5
):

    if threshold < 0 or threshold > 1:
        raise HTTPException(
            status_code=422,
            detail="Threshold must be between 0 and 1"
        )

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Check that student exists
        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s;
        """, (student_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        # Find topics with mastery below the threshold
        cursor.execute("""
            SELECT
                m.topic_id,
                t.topic_name,
                m.mastery_score,
                m.last_updated
            FROM mastery m
            JOIN topics t
                ON m.topic_id = t.topic_id
            WHERE m.student_id = %s
              AND m.mastery_score < %s
            ORDER BY m.mastery_score ASC;
        """, (
            student_id,
            threshold
        ))

        rows = cursor.fetchall()

        weak_topics = []

        for row in rows:
            weak_topics.append({
                "topic_id": row[0],
                "topic_name": row[1],
                "mastery_score": float(row[2]),
                "last_updated": row[3]
            })

        return {
            "student_id": student_id,
            "threshold": threshold,
            "weak_topics": weak_topics
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch weak topics"
        )

    finally:
        cursor.close()
        connection.close()
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
@app.post("/chunks")
def store_chunk(request: ChunkEmbeddingRequest):

    if request.embedding is not None and len(request.embedding) != 1024:
        raise HTTPException(
            status_code=422,
            detail="Embedding must contain exactly 1024 values"
        )

    connection = get_connection()
    cursor = connection.cursor()

    try:
        embedding_value = (
            Vector(request.embedding)
            if request.embedding is not None
            else None
        )

        cursor.execute("""
            INSERT INTO chunks (
                source_id,
                topic_id,
                concept_id,
                content,
                page_number,
                slide_number,
                timestamp_seconds,
                timestamp_end,
                metadata,
                embedding
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING chunk_id;
        """, (
            request.source_id,
            request.topic_id,
            request.concept_id,
            request.content,
            request.page_number,
            request.slide_number,
            request.timestamp_seconds,
            request.timestamp_end,
            Json(request.metadata or {}),
            embedding_value
        ))

        chunk_id = cursor.fetchone()[0]

        connection.commit()

        return {
            "status": "stored",
            "chunk_id": chunk_id,
            "embedding_attached": request.embedding is not None
        }

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to store chunk"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/chunks/batch")
def create_chunks_batch(request: BatchChunksRequest):

    # Validate only embeddings that are provided
    for chunk in request.chunks:
        if chunk.embedding is not None and len(chunk.embedding) != 1024:
            raise HTTPException(
                status_code=422,
                detail="Every provided embedding must contain exactly 1024 values"
            )

    connection = get_connection()
    cursor = connection.cursor()

    inserted_chunks = []

    try:
        for chunk in request.chunks:

            embedding_value = (
                Vector(chunk.embedding)
                if chunk.embedding is not None
                else None
            )

            cursor.execute("""
                INSERT INTO chunks (
                    source_id,
                    topic_id,
                    concept_id,
                    content,
                    page_number,
                    slide_number,
                    timestamp_seconds,
                    timestamp_end,
                    metadata,
                    embedding
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING chunk_id;
            """, (
                chunk.source_id,
                chunk.topic_id,
                chunk.concept_id,
                chunk.content,
                chunk.page_number,
                chunk.slide_number,
                chunk.timestamp_seconds,
                chunk.timestamp_end,
                Json(chunk.metadata or {}),
                embedding_value
            ))

            chunk_id = cursor.fetchone()[0]
            inserted_chunks.append(chunk_id)

        connection.commit()

        return {
            "status": "created",
            "inserted_count": len(inserted_chunks),
            "chunk_ids": inserted_chunks
        }

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create chunks"
        )

    finally:
        cursor.close()
        connection.close()
@app.put("/chunks/{chunk_id}/embedding")
def update_chunk_embedding(
    chunk_id: int,
    request: ChunkEmbeddingUpdateRequest
):

    # 1. Validate embedding dimension
    if len(request.embedding) != 1024:
        raise HTTPException(
            status_code=422,
            detail="Embedding must contain exactly 1024 values"
        )

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # 2. Check that the chunk exists
        cursor.execute("""
            SELECT chunk_id
            FROM chunks
            WHERE chunk_id = %s;
        """, (chunk_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Chunk not found"
            )

        # 3. Convert list to pgvector
        embedding_value = Vector(request.embedding)

        # 4. Attach embedding to the existing chunk
        cursor.execute("""
            UPDATE chunks
            SET embedding = %s
            WHERE chunk_id = %s;
        """, (
            embedding_value,
            chunk_id
        ))

        connection.commit()

        return {
            "status": "updated",
            "chunk_id": chunk_id,
            "embedding_attached": True
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update chunk embedding"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/questions")
def create_question(request: QuestionRequest):

    # Validate difficulty
    if request.difficulty < 1 or request.difficulty > 5:
        raise HTTPException(
            status_code=422,
            detail="Difficulty must be between 1 and 5"
        )

    # Validate question type
    allowed_question_types = {
        "MCQ",
        "SHORT_ANSWER",
        "NUMERICAL"
    }

    if request.question_type not in allowed_question_types:
        raise HTTPException(
            status_code=422,
            detail="Invalid question type"
        )

    # Validate embedding dimension
    if request.embedding is not None and len(request.embedding) != 1024:
        raise HTTPException(
            status_code=422,
            detail="Embedding must contain exactly 1024 values"
        )

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Check topic exists
        cursor.execute("""
            SELECT topic_id
            FROM topics
            WHERE topic_id = %s;
        """, (request.topic_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Topic not found"
            )

        # Check source exists
        cursor.execute("""
            SELECT source_id
            FROM sources
            WHERE source_id = %s;
        """, (request.source_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Source not found"
            )

        # Check concept exists, if provided
        if request.concept_id is not None:
            cursor.execute("""
                SELECT concept_id
                FROM concepts
                WHERE concept_id = %s;
            """, (request.concept_id,))

            if cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail="Concept not found"
                )

        # Check chunk exists, if provided
        if request.chunk_id is not None:
            cursor.execute("""
                SELECT chunk_id
                FROM chunks
                WHERE chunk_id = %s;
            """, (request.chunk_id,))

            if cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail="Chunk not found"
                )

        embedding_value = (
            Vector(request.embedding)
            if request.embedding is not None
            else None
        )

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
            embedding_value
        ))

        question_id = cursor.fetchone()[0]

        connection.commit()

        return {
            "status": "created",
            "question_id": question_id
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create question"
        )

    finally:
        cursor.close()
        connection.close()
@app.get("/questions")
def get_questions(
    topic_id: int | None = None,
    concept_id: int | None = None,
    difficulty: int | None = None,
    student_id: int | None = None,
    course_id: int | None = None,
    limit: int = 10
):

    # Validate limit
    if limit < 1 or limit > 100:
        raise HTTPException(
            status_code=422,
            detail="Limit must be between 1 and 100"
        )

    connection = get_connection()
    cursor = connection.cursor()

    try:
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
            WHERE verified = TRUE
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

        # Filter by course
        if course_id is not None:
            query += """
                AND topic_id IN (
                    SELECT topic_id
                    FROM topics
                    WHERE course_id = %s
                )
            """
            parameters.append(course_id)

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

        query += " ORDER BY question_id LIMIT %s;"
        parameters.append(limit)

        cursor.execute(query, parameters)

        rows = cursor.fetchall()

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
            for row in rows
        ]

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch questions"
        )

    finally:
        cursor.close()
        connection.close()
@app.get("/students/{student_id}/question-history")
def get_question_history(student_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT
                a.answer_id,
                a.attempt_id,
                a.question_id,
                q.question_text,
                q.topic_id,
                q.concept_id,
                q.difficulty,
                q.question_type,
                a.student_answer,
                a.is_correct,
                a.answered_at
            FROM answers a
            JOIN quiz_attempts qa
                ON a.attempt_id = qa.attempt_id
            JOIN questions q
                ON a.question_id = q.question_id
            WHERE qa.student_id = %s
            ORDER BY a.answered_at ASC;
        """, (student_id,))

        rows = cursor.fetchall()

        history = []

        for row in rows:
            history.append({
                "answer_id": row[0],
                "attempt_id": row[1],
                "question_id": row[2],
                "question_text": row[3],
                "topic_id": row[4],
                "concept_id": row[5],
                "difficulty": row[6],
                "question_type": row[7],
                "student_answer": row[8],
                "is_correct": row[9],
                "answered_at": row[10]
            })

        return {
            "student_id": student_id,
            "history": history
        }

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch question history"
        )

    finally:
        cursor.close()
        connection.close()
@app.get("/concepts/{concept_id}/prerequisites")
def get_prerequisites(concept_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute("""
            SELECT
                cp.prerequisite_id,
                cp.concept_id,
                c1.concept_name AS concept_name,
                cp.prerequisite_concept_id,
                c2.concept_name AS prerequisite_concept_name
            FROM concept_prerequisites cp
            JOIN concepts c1
                ON cp.concept_id = c1.concept_id
            JOIN concepts c2
                ON cp.prerequisite_concept_id = c2.concept_id
            WHERE cp.concept_id = %s
            ORDER BY cp.prerequisite_id;
        """, (concept_id,))

        rows = cursor.fetchall()

        prerequisites = []

        for row in rows:
            prerequisites.append({
                "prerequisite_id": row[0],
                "concept_id": row[1],
                "concept_name": row[2],
                "prerequisite_concept_id": row[3],
                "prerequisite_concept_name": row[4]
            })

        return {
            "concept_id": concept_id,
            "prerequisites": prerequisites
        }

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch prerequisites"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/concepts/{concept_id}/prerequisites")
def add_concept_prerequisite(
    concept_id: int,
    prerequisite_id: int
):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Check that the main concept exists
        cursor.execute("""
            SELECT concept_id
            FROM concepts
            WHERE concept_id = %s;
        """, (concept_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Concept not found"
            )

        # Check that the prerequisite concept exists
        cursor.execute("""
            SELECT concept_id
            FROM concepts
            WHERE concept_id = %s;
        """, (prerequisite_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Prerequisite concept not found"
            )

        # Prevent a concept from being its own prerequisite
        if concept_id == prerequisite_id:
            raise HTTPException(
                status_code=400,
                detail="A concept cannot be its own prerequisite"
            )

        # Add prerequisite relationship
        cursor.execute("""
            INSERT INTO concept_prerequisites (
                concept_id,
                prerequisite_id
            )
            VALUES (%s, %s)
            ON CONFLICT (concept_id, prerequisite_id)
            DO NOTHING;
        """, (
            concept_id,
            prerequisite_id
        ))

        connection.commit()

        return {
            "status": "created",
            "concept_id": concept_id,
            "prerequisite_id": prerequisite_id
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to add prerequisite"
        )

    finally:
        cursor.close()
        connection.close()
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

    try:
        # Check that student exists
        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s;
        """, (student_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        # Get mastery for all concepts
        cursor.execute("""
            SELECT
                cm.concept_id,
                c.concept_name,
                cm.mastery_score
            FROM concept_mastery cm
            JOIN concepts c
                ON cm.concept_id = c.concept_id
            WHERE cm.student_id = %s
            ORDER BY cm.concept_id;
        """, (student_id,))

        rows = cursor.fetchall()

        mastery = []

        for row in rows:
            mastery.append({
                "concept_id": row[0],
                "concept_name": row[1],
                "mastery_score": float(row[2])
            })

        return {
            "student_id": student_id,
            "concept_mastery": mastery
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch concept mastery"
        )

    finally:
        cursor.close()
        connection.close()
@app.put("/students/{student_id}/concept-mastery")
def update_concept_mastery(
    student_id: int,
    request: ConceptMasteryRequest
):

    if request.mastery_score < 0 or request.mastery_score > 1:
        raise HTTPException(
            status_code=422,
            detail="Mastery score must be between 0 and 1"
        )

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Check student
        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s;
        """, (student_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        # Check concept
        cursor.execute("""
            SELECT concept_id
            FROM concepts
            WHERE concept_id = %s;
        """, (request.concept_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Concept not found"
            )

        # Check whether mastery already exists
        cursor.execute("""
            SELECT mastery_score
            FROM concept_mastery
            WHERE student_id = %s
              AND concept_id = %s;
        """, (
            student_id,
            request.concept_id
        ))

        existing = cursor.fetchone()

        if existing is None:

            # First mastery record
            cursor.execute("""
                INSERT INTO concept_mastery (
                    student_id,
                    concept_id,
                    mastery_score
                )
                VALUES (%s, %s, %s);
            """, (
                student_id,
                request.concept_id,
                request.mastery_score
            ))

            previous_mastery = None

        else:

            previous_mastery = float(existing[0])

            cursor.execute("""
                UPDATE concept_mastery
                SET mastery_score = %s
                WHERE student_id = %s
                  AND concept_id = %s;
            """, (
                request.mastery_score,
                student_id,
                request.concept_id
            ))

        # Save the change in history
        cursor.execute("""
            INSERT INTO mastery_history (
                student_id,
                concept_id,
                mastery_score,
                recorded_at
            )
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP);
        """, (
            student_id,
            request.concept_id,
            request.mastery_score
        ))

        connection.commit()

        return {
            "status": "updated",
            "student_id": student_id,
            "concept_id": request.concept_id,
            "previous_mastery": previous_mastery,
            "mastery_score": request.mastery_score
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to update concept mastery"
        )

    finally:
        cursor.close()
        connection.close()
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
def get_concept_mastery_history(student_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Check that student exists
        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s;
        """, (student_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        # Get mastery history
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

        rows = cursor.fetchall()

        history = []

        for row in rows:
            history.append({
                "id": row[0],
                "concept_id": row[1],
                "concept_name": row[2],
                "mastery_score": float(row[3]),
                "recorded_at": row[4]
            })

        return {
            "student_id": student_id,
            "history": history
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch mastery history"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/chat/sessions")
def create_chat_session(request: ChatSessionRequest):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # 1. Check that the student exists
        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s;
        """, (request.student_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        # 2. Check that the course exists
        cursor.execute("""
            SELECT course_id
            FROM courses
            WHERE course_id = %s;
        """, (request.course_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Course not found"
            )

        # 3. Create chat session
        cursor.execute("""
            INSERT INTO chat_sessions (
                student_id,
                course_id
            )
            VALUES (%s, %s)
            RETURNING
                session_id,
                student_id,
                course_id,
                created_at;
        """, (
            request.student_id,
            request.course_id
        ))

        session = cursor.fetchone()

        connection.commit()

        return {
            "status": "created",
            "session_id": session[0],
            "student_id": session[1],
            "course_id": session[2],
            "created_at": session[3]
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create chat session"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/chat/messages")
def create_chat_message(request: ChatMessageRequest):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # 1. Check that the chat session exists
        cursor.execute("""
            SELECT session_id
            FROM chat_sessions
            WHERE session_id = %s;
        """, (request.session_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Chat session not found"
            )

        # 2. Validate message role
        allowed_roles = {
            "user",
            "assistant",
            "system"
        }

        if request.role not in allowed_roles:
            raise HTTPException(
                status_code=422,
                detail="Invalid message role"
            )

        # 3. Make sure message content is not empty
        if not request.content.strip():
            raise HTTPException(
                status_code=422,
                detail="Message content cannot be empty"
            )

        # 4. Store the chat message
        cursor.execute("""
            INSERT INTO chat_messages (
                session_id,
                role,
                content,
                sources
            )
            VALUES (%s, %s, %s, %s)
            RETURNING
                message_id,
                session_id,
                role,
                content,
                sources,
                created_at;
        """, (
            request.session_id,
            request.role,
            request.content,
            Json(request.sources) if request.sources else None
        ))

        message = cursor.fetchone()

        connection.commit()

        return {
            "status": "created",
            "message_id": message[0],
            "session_id": message[1],
            "role": message[2],
            "content": message[3],
            "sources": message[4],
            "created_at": message[5]
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create chat message"
        )

    finally:
        cursor.close()
        connection.close()
@app.get("/chat/sessions/{session_id}/messages")
def get_chat_messages(session_id: int):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # 1. Check that the chat session exists
        cursor.execute("""
            SELECT session_id
            FROM chat_sessions
            WHERE session_id = %s;
        """, (session_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Chat session not found"
            )

        # 2. Get all messages in chronological order
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
            ORDER BY created_at ASC, message_id ASC;
        """, (session_id,))

        rows = cursor.fetchall()

        messages = []

        for row in rows:
            messages.append({
                "message_id": row[0],
                "session_id": row[1],
                "role": row[2],
                "content": row[3],
                "sources": row[4],
                "created_at": row[5]
            })

        return {
            "session_id": session_id,
            "messages": messages
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch chat messages"
        )

    finally:
        cursor.close()
        connection.close()
@app.post("/learner-events")
def create_learner_event(request: LearnerEventRequest):

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # 1. Check that the student exists
        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s;
        """, (request.student_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        # 2. If a concept is provided, check that it exists
        if request.concept_id is not None:

            cursor.execute("""
                SELECT concept_id
                FROM concepts
                WHERE concept_id = %s;
            """, (request.concept_id,))

            if cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail="Concept not found"
                )

        # 3. Validate signal if provided
        if request.signal is not None:

            if request.signal < 0 or request.signal > 1:
                raise HTTPException(
                    status_code=422,
                    detail="Signal must be between 0 and 1"
                )

        # 4. Validate event type
        allowed_event_types = {
            "quiz_answer",
            "quiz_completed",
            "chat",
            "content_viewed",
            "content_completed",
            "hint_requested"
        }

        if request.event_type not in allowed_event_types:
            raise HTTPException(
                status_code=422,
                detail="Invalid event type"
            )

        # 5. Insert learner event
        cursor.execute("""
            INSERT INTO learner_events (
                student_id,
                concept_id,
                event_type,
                signal
            )
            VALUES (%s, %s, %s, %s)
            RETURNING
                event_id,
                student_id,
                concept_id,
                event_type,
                signal,
                created_at;
        """, (
            request.student_id,
            request.concept_id,
            request.event_type,
            request.signal
        ))

        event = cursor.fetchone()

        connection.commit()

        return {
            "status": "created",
            "event_id": event[0],
            "student_id": event[1],
            "concept_id": event[2],
            "event_type": event[3],
            "signal": event[4],
            "created_at": event[5]
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to create learner event"
        )

    finally:
        cursor.close()
        connection.close()
@app.get("/students/{student_id}/learner-events")
def get_learner_events(
    student_id: int,
    concept_id: int | None = None,
    event_type: str | None = None,
    limit: int = 100
):

    if limit < 1 or limit > 500:
        raise HTTPException(
            status_code=422,
            detail="Limit must be between 1 and 500"
        )

    connection = get_connection()
    cursor = connection.cursor()

    try:
        # 1. Check that student exists
        cursor.execute("""
            SELECT student_id
            FROM students
            WHERE student_id = %s;
        """, (student_id,))

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Student not found"
            )

        # 2. Build the query
        query = """
            SELECT
                le.event_id,
                le.student_id,
                le.concept_id,
                c.concept_name,
                le.event_type,
                le.signal,
                le.created_at
            FROM learner_events le
            LEFT JOIN concepts c
                ON le.concept_id = c.concept_id
            WHERE le.student_id = %s
        """

        parameters = [student_id]

        # Optional concept filter
        if concept_id is not None:
            query += " AND le.concept_id = %s"
            parameters.append(concept_id)

        # Optional event-type filter
        if event_type is not None:
            query += " AND le.event_type = %s"
            parameters.append(event_type)

        query += """
            ORDER BY le.created_at DESC
            LIMIT %s;
        """

        parameters.append(limit)

        cursor.execute(query, parameters)

        rows = cursor.fetchall()

        events = []

        for row in rows:
            events.append({
                "event_id": row[0],
                "student_id": row[1],
                "concept_id": row[2],
                "concept_name": row[3],
                "event_type": row[4],
                "signal": row[5],
                "created_at": row[6]
            })

        return {
            "student_id": student_id,
            "events": events
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch learner events"
        )

    finally:
        cursor.close()
        connection.close()