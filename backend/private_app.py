"""Account-scoped API for the existing local models and extraction pipeline."""

import asyncio
import time
from contextlib import contextmanager

from fastapi import FastAPI, Depends, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from backend.auth_db import get_auth_connection
from backend.auth_routes import (
    router as auth_router,
    get_current_student,
    bearer_scheme,
)
from backend.study_tools import router as study_router
from backend.source_viewer import router as source_viewer_router
from backend.figure_tools import router as figure_router
from backend.figure_tools import image_tutor_answer
from backend.learning import install_learning, learner_profile, tutor_style


@contextmanager
def database():
    connection = get_auth_connection()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def require_course(cursor, course_id, student_id):
    cursor.execute(
        "SELECT course_id FROM courses WHERE course_id=%s AND owner_student_id=%s",
        (course_id, student_id),
    )
    if cursor.fetchone() is None:
        raise HTTPException(404, "Workspace not found.")


def require_source(cursor, source_id, student_id, course_id=None):
    cursor.execute(
        """SELECT s.source_id,s.course_id FROM sources s JOIN courses c ON c.course_id=s.course_id
        WHERE s.source_id=%s AND s.owner_student_id=%s AND c.owner_student_id=%s""",
        (source_id, student_id, student_id),
    )
    row = cursor.fetchone()
    if row is None or (course_id is not None and row[1] != course_id):
        raise HTTPException(404, "Material not found.")
    return row


async def protect_study_scope(request: Request, student=Depends(get_current_student)):
    body = await request.json() if request.method in ("POST", "PATCH") else {}
    course = body.get("course_id") or request.query_params.get("course_id")
    source = (
        body.get("source_id")
        or request.query_params.get("source_id")
        or request.path_params.get("source_id")
    )
    try:
        course = int(course) if course is not None else None
        source = int(source) if source is not None else None
    except (ValueError, TypeError):
        raise HTTPException(422, "Invalid workspace or material ID.")

    def check():
        with database() as connection:
            with connection.cursor() as cursor:
                if course is not None:
                    require_course(cursor, course, student["student_id"])
                if source is not None:
                    require_source(cursor, source, student["student_id"], course)
                # Submission endpoints already check artifact ownership. Also ensure
                # old artifacts cannot bypass source ownership using a known UUID.
                artifact = request.path_params.get("artifact_id")
                if artifact is not None:
                    cursor.execute(
                        """SELECT a.source_id,a.course_id FROM aura_study_artifacts a
                        JOIN sources s ON s.source_id=a.source_id JOIN courses c ON c.course_id=s.course_id
                        WHERE a.id=%s AND a.student_id=%s AND s.owner_student_id=%s AND c.owner_student_id=%s""",
                        (
                            str(artifact),
                            student["student_id"],
                            student["student_id"],
                            student["student_id"],
                        ),
                    )
                    if cursor.fetchone() is None:
                        raise HTTPException(404, "Assessment not found.")

    await run_in_threadpool(check)


class ChatMessage(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=12000)


class PrivateChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    top_k: int = Field(default=3, ge=1, le=10)
    include_related_background: bool = True
    course_id: int | None = None
    source_id: int | None = None
    history: list[ChatMessage] = Field(default_factory=list, max_length=8)


def create_private_app(legacy):
    app = FastAPI(title="Aura — private local workspaces")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )

    @app.middleware("http")
    async def private_response_cache(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        vary = response.headers.get("Vary", "")
        response.headers["Vary"] = ", ".join(
            dict.fromkeys(
                [part.strip() for part in vary.split(",") if part.strip()]
                + ["Authorization"]
            )
        )
        return response

    app.include_router(auth_router)

    @app.get("/health")
    async def health():
        import os
        return {"status": "ok", "profile": "private-local",
                "tutor_version": "aura-team-multimodal-v7",
                "vision_configured": bool(os.getenv('OLLAMA_VISION_MODEL', '').strip()),
                "video_visual_sampling": True}

    @app.get("/courses")
    def courses(credentials=Depends(bearer_scheme)):
        if credentials is None:
            raise HTTPException(401, "Sign in to access your study workspace.", headers={"WWW-Authenticate": "Bearer"})
        student = get_current_student(credentials)
        with database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO courses(course_name,owner_student_id)
                    VALUES ('My study materials',%s)
                    ON CONFLICT(owner_student_id) DO UPDATE SET course_name=courses.course_name
                    RETURNING course_id,course_name""",
                    (student["student_id"],),
                )
                row = cursor.fetchone()
        return {"courses": [{"course_id": row[0], "course_name": row[1]}]}

    @app.get("/sources/{course_id}")
    def sources(course_id: int, student=Depends(get_current_student)):
        with database() as connection:
            with connection.cursor() as cursor:
                require_course(cursor, course_id, student["student_id"])
                cursor.execute(
                    """SELECT source_id,source_name,source_type,status FROM sources
                    WHERE course_id=%s AND owner_student_id=%s ORDER BY source_id""",
                    (course_id, student["student_id"]),
                )
                return {
                    "sources": [
                        {
                            "source_id": r[0],
                            "source_name": r[1],
                            "source_type": r[2],
                            "status": r[3],
                        }
                        for r in cursor.fetchall()
                    ]
                }

    @app.get("/study/materials")
    def materials(course_id: int, student=Depends(get_current_student)):
        with database() as connection:
            with connection.cursor() as cursor:
                require_course(cursor, course_id, student["student_id"])
                cursor.execute(
                    """SELECT s.source_id,s.source_name,s.source_type,
                    CASE WHEN EXISTS(SELECT 1 FROM aura_preparation_jobs j WHERE j.source_id=s.source_id
                        AND j.state IN ('queued','processing')) THEN 'processing'
                    WHEN EXISTS(SELECT 1 FROM aura_preparation_jobs j WHERE j.source_id=s.source_id
                        AND j.state='failed') THEN 'error' ELSE s.status END,COALESCE(p.archived,FALSE)
                    FROM sources s LEFT JOIN aura_material_preferences p ON p.source_id=s.source_id AND p.student_id=%s
                    WHERE s.course_id=%s AND s.owner_student_id=%s ORDER BY s.source_id""",
                    (student["student_id"], course_id, student["student_id"]),
                )
                return {
                    "sources": [
                        {
                            "source_id": r[0],
                            "source_name": r[1],
                            "source_type": r[2],
                            "status": r[3],
                            "archived": r[4],
                        }
                        for r in cursor.fetchall()
                    ]
                }

    @app.post("/courses/{course_id}/sources")
    async def upload(
        course_id: int,
        file: UploadFile = File(...),
        student=Depends(get_current_student),
    ):
        def check():
            with database() as connection:
                with connection.cursor() as cursor:
                    require_course(cursor, course_id, student["student_id"])

        await run_in_threadpool(check)

        # The legacy coroutine performs synchronous OCR/database work after
        # reading the file. Run it off the shared web event loop.
        def prepare():
            return asyncio.run(
                legacy.upload_course_source(
                    course_id, file, owner_student_id=student["student_id"]
                )
            )

        started = time.perf_counter()
        result = await run_in_threadpool(prepare)
        print(
            f"[Preparation] Read/extracted material in {time.perf_counter() - started:.1f} seconds.",
            flush=True,
        )
        return result

    @app.post("/sources/{source_id}/generate-embeddings")
    def embeddings(source_id: int, student=Depends(get_current_student)):
        with database() as connection:
            with connection.cursor() as cursor:
                require_source(cursor, source_id, student["student_id"])
        result = legacy.generate_source_embeddings(source_id)
        if result.get("status") == "completed" and result.get("embedded_count") == 0:
            # Existing ready material can be resumed after refresh without returning
            # a zero count that the frontend interprets as a preparation failure.
            with database() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT count(*) FROM chunks WHERE source_id=%s AND embedding IS NOT NULL",
                        (source_id,),
                    )
                    result["embedded_count"] = cursor.fetchone()[0]
        return result

    @app.post("/chat")
    def chat(body: PrivateChatRequest, credentials=Depends(bearer_scheme)):
        if credentials is None:
            raise HTTPException(401, "Sign in to use the tutor.", headers={"WWW-Authenticate": "Bearer"})
        student = get_current_student(credentials)
        if body.course_id is None:
            raise HTTPException(422, "Choose a study workspace first.")
        image_selected = False
        with database() as connection:
            with connection.cursor() as cursor:
                require_course(cursor, body.course_id, student["student_id"])
                if body.source_id is not None:
                    require_source(
                        cursor, body.source_id, student["student_id"], body.course_id
                    )
                    cursor.execute('SELECT source_type FROM sources WHERE source_id=%s', (body.source_id,))
                    selected_type = cursor.fetchone()
                    image_selected = bool(selected_type and selected_type[0] == 'image')

        if image_selected:
            visual = image_tutor_answer(body.source_id, body.question, student['student_id'])
            if visual is not None:
                return visual

        with database() as connection:
            with connection.cursor() as cursor:
                profile = learner_profile(cursor, student["student_id"], body.course_id, body.source_id)

        class OwnedRetriever:
            def concept_context(self, query, **kwargs):
                return legacy.get_retriever().concept_context(query, owner_student_id=student["student_id"], **kwargs)

            def overview(self, **kwargs):
                return legacy.get_retriever().overview(
                    owner_student_id=student["student_id"], **kwargs
                )

            def search(self, query, **kwargs):
                return legacy.get_retriever().search(
                    query, owner_student_id=student["student_id"], **kwargs
                )

        try:
            tutor = legacy.RAG(retriever=OwnedRetriever(), llm=legacy.LLM(),
                               learning_style=tutor_style(profile, body.question),
                               include_related_background=body.include_related_background, source_first_mode=True)
            return tutor.answer(
                question=body.question,
                top_k=body.top_k,
                course_id=body.course_id,
                source_id=body.source_id,
                history=[m.model_dump() for m in body.history],
            )
        except HTTPException:
            raise
        except Exception as error:
            raise HTTPException(
                503, "The tutor is temporarily unavailable. Check Ollama and retry."
            ) from error

    app.include_router(study_router, dependencies=[Depends(protect_study_scope)])
    app.include_router(source_viewer_router, dependencies=[Depends(protect_study_scope)])
    app.include_router(figure_router, dependencies=[Depends(protect_study_scope)])
    install_learning(app, database)
    from backend.preparation_jobs import install_preparation_jobs
    install_preparation_jobs(app, legacy, database, require_course, require_source)
    return app
