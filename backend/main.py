from functools import lru_cache

from backend.ai.embeddings import EmbeddingModel
from backend.ai.pg_retrieval import PostgresRetriever

from backend.ai.rag import RAG
from backend.ai.llm import LLM

from backend.ai.adaptive_assessment import AdaptiveAssessment
from backend.ai.learner_model import LearnerState
from backend.ai.question_generator import QuestionGenerator
from backend.ai.question_validator import QuestionValidator
from backend.ai.question_grounding import QuestionGrounding
from backend.ai.question_duplicate import QuestionDuplicateDetector
from backend.ai.assessment_session import AssessmentSession

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2
from psycopg2.extras import Json
import os
from dotenv import load_dotenv
from pgvector.psycopg2 import register_vector
from pgvector import Vector
from pathlib import Path

import pymupdf
from pathlib import Path
import shutil

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
    query: str
    top_k: int = 5
    course_id: int | None = None
    topic_id: int | None = None
    concept_id: int | None = None

class ChatRequest(BaseModel):
    question: str
    top_k: int = 3

class AdaptiveQuestionRequest(BaseModel):
    student_id: int
    topic_id: int
    top_k: int = 3

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


@lru_cache(maxsize=1)
def get_retriever():
    embedding_model = EmbeddingModel()
    return PostgresRetriever(embedding_model)


@lru_cache(maxsize=1)
def get_rag():
    retriever = get_retriever()
    llm = LLM()

    return RAG(
        retriever=retriever,
        llm=llm
    )

@lru_cache(maxsize=1)
def get_assessment_components():
    llm = LLM()
    embedding_model = get_retriever().embedding_model

    return {
        "question_generator": QuestionGenerator(llm),
        "question_validator": QuestionValidator(),
        "grounding_checker": QuestionGrounding(llm),
        "duplicate_detector": QuestionDuplicateDetector(embedding_model),
    }


@app.post("/adaptive/question")
def generate_adaptive_question(request: AdaptiveQuestionRequest):
    # 1. Retrieve the topic and verify the student exists.
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT topic_name
            FROM topics
            WHERE topic_id = %s;
            """,
            (request.topic_id,)
        )
        topic_row = cursor.fetchone()

        cursor.execute(
            """
            SELECT student_id
            FROM students
            WHERE student_id = %s;
            """,
            (request.student_id,)
        )
        student_row = cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

    if topic_row is None:
        raise HTTPException(status_code=404, detail="Topic not found.")

    if student_row is None:
        raise HTTPException(status_code=404, detail="Student not found.")

    topic_name = topic_row[0]

    # 1.1 Retrieve previously answered questions for this student and topic.
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT
                q.question_text,
                MAX(a.answered_at) AS last_answered
            FROM answers AS a
            JOIN quiz_attempts AS qa
                ON qa.attempt_id = a.attempt_id
            JOIN questions AS q
                ON q.question_id = a.question_id
            WHERE qa.student_id = %s
              AND qa.topic_id = %s
            GROUP BY q.question_text
            ORDER BY last_answered DESC
            LIMIT 30;
            """,
            (request.student_id, request.topic_id)
        )

        previous_questions = [
            row[0] for row in cursor.fetchall()
        ]

    finally:
        cursor.close()
        connection.close()

    # 2. Retrieve relevant course material.
    retriever = get_retriever()

    retrieved_chunks = retriever.search(
        query=topic_name,
        top_k=request.top_k,
        topic=topic_name
    )

    if not retrieved_chunks:
        raise HTTPException(
            status_code=404,
            detail="No indexed course material was found for this topic."
        )

    # 3. Initialize the assessment components.
    components = get_assessment_components()

    # Load the student's saved mastery for this topic.
    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT mastery_score
            FROM mastery
            WHERE student_id = %s
              AND topic_id = %s;
            """,
            (request.student_id, request.topic_id)
        )

        mastery_row = cursor.fetchone()

    finally:
        cursor.close()
        connection.close()

    # Initialize the learner with saved mastery when available.
    learner = LearnerState(student_id=request.student_id)

    if mastery_row is not None:
        learner.get_topic_state(
            topic_name,
            initial_mastery=float(mastery_row[0])
        )

    session = AssessmentSession(
        student_id=request.student_id,
        topic=topic_name
    )

    assessment = AdaptiveAssessment(
        learner=learner,
        question_generator=components["question_generator"],
        question_validator=components["question_validator"],
        grounding_checker=components["grounding_checker"],
        duplicate_detector=components["duplicate_detector"],
        session=session
    )

    # 4. Generate and validate the question using persistent history.
    try:
        mcq = assessment.generate_question(
            retrieved_chunks=retrieved_chunks,
            topic=topic_name,
            previous_questions=previous_questions
        )
    except (ValueError, RuntimeError) as error:
        raise HTTPException(
            status_code=502,
            detail=f"Could not generate a valid question: {error}"
        ) from error

    # 5. Resolve a valid source and chunk for the database.
    source_id = mcq.source_ids[0] if mcq.source_ids else None

    if source_id is None:
        raise HTTPException(
            status_code=502,
            detail="Generated question has no source ID."
        )

    matching_chunks = [
        result.chunk
        for result in retrieved_chunks
        if result.chunk.source_id == source_id
    ]

    if not matching_chunks:
        raise HTTPException(
            status_code=502,
            detail="Could not resolve the question's source chunk."
        )

    chunk = matching_chunks[0]

    # Convert the generator's difficulty to the database's 1–5 scale.
    difficulty_map = {
        "easy": 1,
        "medium": 3,
        "hard": 5
    }

    difficulty_value = difficulty_map.get(
        (mcq.difficulty or "").lower()
    )

    if difficulty_value is None:
        raise HTTPException(
            status_code=502,
            detail="Generated question has an invalid difficulty."
        )

    # 6. Save the generated question.
    connection = get_connection()
    cursor = connection.cursor()

    try:
        # Avoid saving an exact duplicate question for the same topic.
        cursor.execute(
            """
            SELECT question_id
            FROM questions
            WHERE topic_id = %s
              AND LOWER(TRIM(question_text)) = LOWER(TRIM(%s))
            LIMIT 1;
            """,
            (request.topic_id, mcq.question)
        )

        existing_question = cursor.fetchone()

        if existing_question is not None:
            connection.rollback()
            raise HTTPException(
                status_code=409,
                detail="This question already exists for the selected topic."
            )

        cursor.execute(
            """
            INSERT INTO questions (
                topic_id,
                source_id,
                chunk_id,
                question_text,
                difficulty,
                correct_answer,
                question_type,
                options,
                explanation,
                verified
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING question_id;
            """,
            (
                request.topic_id,
                source_id,
                chunk.chunk_id,
                mcq.question,
                difficulty_value,
                mcq.correct_answer,
                "MCQ",
                Json({
                    "A": mcq.options[0],
                    "B": mcq.options[1],
                    "C": mcq.options[2],
                    "D": mcq.options[3]
                }),
                mcq.explanation,
                True
            )
        )

        inserted_row = cursor.fetchone()

        if inserted_row is None:
            raise HTTPException(
                status_code=500,
                detail="Question was inserted, but no question ID was returned."
            )

        question_id = inserted_row[0]
        connection.commit()

    except HTTPException:
        connection.rollback()
        raise

    except Exception as error:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to save generated question: {error}"
        ) from error

    finally:
        cursor.close()
        connection.close()

    # 7. Return the saved question without exposing its answer.
    return {
        "question_id": question_id,
        "student_id": request.student_id,
        "topic_id": request.topic_id,
        "topic": topic_name,
        "question": mcq.question,
        "options": mcq.options,
        "difficulty": mcq.difficulty,
        "source_ids": mcq.source_ids,
        "verified": True
    }




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

@app.post("/courses/{course_id}/sources")
async def upload_course_source(
    course_id: int,
    file: UploadFile = File(...)
):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400,
            detail="Please upload a PDF file"
        )

    connection = get_connection()
    cursor = connection.cursor()
    saved_path = None

    try:
        cursor.execute(
            "SELECT course_id FROM courses WHERE course_id = %s",
            (course_id,)
        )

        if cursor.fetchone() is None:
            raise HTTPException(
                status_code=404,
                detail="Course not found"
            )

        upload_dir = Path(__file__).parent / "uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)

        saved_path = upload_dir / file.filename

        with saved_path.open("wb") as output_file:
            shutil.copyfileobj(file.file, output_file)

        with pymupdf.open(str(saved_path)) as pdf:
            page_count = len(pdf)
            extracted_pages: list[str] = []

            for page in pdf:
                page_text = str(page.get_text("text"))
                extracted_pages.append(page_text)

            extracted_text: str = "\n".join(extracted_pages).strip()

        if not extracted_text:
            status = "empty"
        else:
            status = "success"

        cursor.execute(
            """
            INSERT INTO sources (
                course_id,
                source_name,
                source_type,
                file_path,
                status
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING source_id
            """,
            (
                course_id,
                file.filename,
                "pdf",
                str(saved_path),
                status
            )
        )

        row = cursor.fetchone()

        if row is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to create source record"
            )

        source_id = row[0]
        connection.commit()


        return {
            "source_id": source_id,
            "course_id": course_id,
            "source_name": file.filename,
            "source_type": "pdf",
            "status": status,
            "page_count": page_count,
            "extracted_characters": len(extracted_text),
            "message": "PDF uploaded and text extraction completed"
        }

    except HTTPException:
        connection.rollback()
        raise

    except Exception as exc:
        connection.rollback()
        print("PDF UPLOAD ERROR:", repr(exc))
        raise HTTPException(
            status_code=500,
            detail=f"PDF upload failed: {str(exc)}"
        )

    finally:
        cursor.close()
        connection.close()
        await file.close()

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

    if not request.query or not request.query.strip():
        raise HTTPException(
            status_code=422,
            detail="Query cannot be empty"
        )

    if request.top_k < 1 or request.top_k > 20:
        raise HTTPException(
            status_code=422,
            detail="top_k must be between 1 and 20"
        )

    try:
        retriever = get_retriever()

        results = retriever.search(
            query=request.query,
            top_k=request.top_k,
            topic=None
        )

        response_results = []

        for result in results:
            response_results.append({
                "chunk_id": int(result.chunk.chunk_id),
                "source_id": result.chunk.source_id,
                "source_name": result.chunk.source_name,
                "source_type": result.chunk.source_type,
                "content": result.chunk.content,
                "page_number": result.chunk.page,
                "slide_number": result.chunk.slide,
                "timestamp_seconds": result.chunk.timestamp_start,
                "timestamp_end": result.chunk.timestamp_end,
                "topic": result.chunk.topic,
                "similarity": result.score
            })

        return {
            "query": request.query,
            "results": response_results
        }

    except HTTPException:
        raise

    except Exception as error:
        print(f"Search error: {error}")

        raise HTTPException(
            status_code=500,
            detail="Search operation failed"
        )

@app.post("/chat")
def chat(request: ChatRequest):
    if not request.question or not request.question.strip():
        raise HTTPException(
            status_code=422,
            detail="Question cannot be empty"
        )

    if request.top_k < 1 or request.top_k > 10:
        raise HTTPException(
            status_code=422,
            detail="top_k must be between 1 and 10"
        )

    try:
        rag = get_rag()

        result = rag.answer(
            question=request.question,
            top_k=request.top_k
        )

        return result

    except HTTPException:
        raise

    except Exception as error:
        print(f"Chat error: {error}")
        raise HTTPException(
            status_code=500,
            detail="Chat operation failed"
        )

    
@app.get("/students/{student_id}/mastery")
def get_student_mastery(student_id: int, course_id: int | None = None):

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

        # Get current topic-level mastery, optionally filtered by course.
        if course_id is None:
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
        else:
            # Verify that the requested course exists.
            cursor.execute("""
                SELECT course_id
                FROM courses
                WHERE course_id = %s;
            """, (course_id,))

            if cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail="Course not found"
                )

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
                  AND t.course_id = %s
                ORDER BY m.topic_id;
            """, (student_id, course_id))

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


@app.post("/students/{student_id}/mastery/{topic_id}")
def update_topic_mastery(
    student_id: int,
    topic_id: int,
    score: float
):
    if score < 0 or score > 100:
        raise HTTPException(
            status_code=422,
            detail="Score must be between 0 and 100"
        )

    current_performance = score / 100.0

    connection = get_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "SELECT student_id FROM students WHERE student_id = %s;",
            (student_id,)
        )
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Student not found")

        cursor.execute(
            "SELECT topic_id FROM topics WHERE topic_id = %s;",
            (topic_id,)
        )
        if cursor.fetchone() is None:
            raise HTTPException(status_code=404, detail="Topic not found")

        cursor.execute(
            """
            SELECT mastery_score
            FROM mastery
            WHERE student_id = %s AND topic_id = %s;
            """,
            (student_id, topic_id)
        )
        existing = cursor.fetchone()

        if existing is None:
            new_mastery = current_performance

            cursor.execute(
                """
                INSERT INTO mastery (student_id, topic_id, mastery_score)
                VALUES (%s, %s, %s);
                """,
                (student_id, topic_id, new_mastery)
            )
            previous_mastery = None
        else:
            previous_mastery = float(existing[0])
            new_mastery = (
                0.7 * previous_mastery
                + 0.3 * current_performance
            )

            cursor.execute(
                """
                UPDATE mastery
                SET mastery_score = %s,
                    last_updated = CURRENT_TIMESTAMP
                WHERE student_id = %s AND topic_id = %s;
                """,
                (new_mastery, student_id, topic_id)
            )

        connection.commit()

        return {
            "status": "updated",
            "student_id": student_id,
            "topic_id": topic_id,
            "previous_mastery": previous_mastery,
            "mastery_score": new_mastery
        }

    except HTTPException:
        connection.rollback()
        raise
    except Exception as error:
        connection.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update topic mastery: {error}"
        ) from error
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

        if row is None:
            raise HTTPException(
                status_code=500,
                detail="Quiz attempt was created, but no attempt ID was returned."
            )

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
        # Get the quiz attempt and its topic
        cursor.execute("""
            SELECT attempt_id, student_id, topic_id, score
            FROM quiz_attempts
            WHERE attempt_id = %s;
        """, (attempt_id,))

        attempt = cursor.fetchone()

        if attempt is None:
            raise HTTPException(
                status_code=404,
                detail="Quiz attempt not found"
            )

        student_id = attempt[1]
        topic_id = attempt[2]
        existing_score = attempt[3]

        # Mastery is updated by BKT when each answer is submitted.
        cursor.execute("""
            SELECT mastery_score
            FROM mastery
            WHERE student_id = %s AND topic_id = %s;
        """, (student_id, topic_id))
        mastery_row = cursor.fetchone()
        previous_mastery = (
            float(mastery_row[0]) if mastery_row is not None else 0.20
        )
        new_mastery = previous_mastery

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

        answer_counts = cursor.fetchone()

        if answer_counts is None:
            raise HTTPException(
                status_code=400,
                detail="No answers found for this quiz attempt"
            )

        total_questions, correct_answers = answer_counts

        if total_questions == 0:
            raise HTTPException(
                status_code=400,
                detail="No answers found for this quiz attempt"
            )

        # Calculate percentage score
        score = round((correct_answers / total_questions) * 100)

        # Save the completed quiz score
        cursor.execute("""
            UPDATE quiz_attempts
            SET score = %s
            WHERE attempt_id = %s;
        """, (score, attempt_id))

       
        # Mastery is updated by BKT when each answer is submitted.
        # Quiz completion only records the final quiz score.
        connection.commit()


        return {
            "status": "completed",
            "attempt_id": attempt_id,
            "student_id": student_id,
            "topic_id": topic_id,
            "total_questions": total_questions,
            "correct_answers": correct_answers,
            "score": score,
            "previous_mastery": previous_mastery,
            "mastery_score": round(new_mastery, 4)
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
            # Check that the quiz attempt exists and get the student and topic
        cursor.execute("""
            SELECT attempt_id, student_id, topic_id, score
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
        student_id = attempt[1]
        topic_id = attempt[2]

        # Load the topic name required by the learner model.
        cursor.execute("""
            SELECT topic_name
            FROM topics
            WHERE topic_id = %s;
        """, (topic_id,))
        topic_row = cursor.fetchone()

        if topic_row is None:
            raise HTTPException(
                status_code=404,
                detail="Topic not found"
            )

        topic_name = topic_row[0]

        # Do not allow answers after quiz completion
        if attempt[3] is not None:
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

        print("DEBUG correct_answer:", repr(correct_answer))
        print("DEBUG student_answer:", repr(request.student_answer))

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

        
        answer_row = cursor.fetchone()
        if answer_row is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve the stored answer ID"
            )

        answer_id = answer_row[0]

        # Load the current topic mastery from the database.
        cursor.execute("""
            SELECT mastery_score
            FROM mastery
            WHERE student_id = %s AND topic_id = %s;
        """, (student_id, topic_id))

        mastery_row = cursor.fetchone()

        if mastery_row is None:
            current_mastery = 0.20
        else:
            current_mastery =  min(0.99,max(0.01, float(mastery_row[0])))
    

        # Initialize BKT with the saved mastery.
        learner = LearnerState(student_id=student_id)
        learner.get_topic_state(
            topic_name,
            initial_mastery=current_mastery
        )

        # Update mastery based on this answer.
        updated_mastery = learner.update_mastery(
            topic=topic_name,
            correct=is_correct
        )

        # Save the updated mastery.
        if mastery_row is None:
            cursor.execute("""
                INSERT INTO mastery (
                    student_id,
                    topic_id,
                    mastery_score,
                    last_updated
                )
                VALUES (%s, %s, %s, CURRENT_TIMESTAMP);
            """, (student_id, topic_id, updated_mastery))
        else:
            cursor.execute("""
                UPDATE mastery
                SET mastery_score = %s,
                    last_updated = CURRENT_TIMESTAMP
                WHERE student_id = %s AND topic_id = %s;
            """, (updated_mastery, student_id, topic_id))

        connection.commit()

        return {
            "status": "stored",
            "answer_id": answer_id,
            "is_correct": is_correct,
            "topic_id": topic_id,
            "mastery_score": updated_mastery
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

        result = cursor.fetchone()
        if result is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to retrieve created question"
            )

        question_id = result[0]

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

    if history is None:
        connection.rollback()
        cursor.close()
        connection.close()
        raise HTTPException(
            status_code=500,
            detail="Failed to record mastery history"
        )

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

        if session is None:
            connection.rollback()
            raise HTTPException(
                status_code=500,
                detail="Failed to create chat session"
            )

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

        if message is None:
            connection.rollback()
            raise HTTPException(
                status_code=500,
                detail="Failed to create chat message"
            )

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

        if event is None:
            raise HTTPException(
                status_code=500,
                detail="Failed to create learner event"
            )

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

        parameters: list[int | str] = [student_id]

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