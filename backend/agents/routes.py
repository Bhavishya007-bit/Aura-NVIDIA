"""Authenticated memory/tasks API and a durable, two-worker agent queue."""
import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2 import IntegrityError
from starlette.concurrency import run_in_threadpool
from backend.auth_routes import get_current_student
from backend.agents.contracts import Strict, MemoryInput, RunInput, SKILLS
from backend.agents.store import Store
from backend.agents.runtime import run_agent

log = logging.getLogger(__name__)


class MemoryToggle(Strict):
    enabled: bool


class TaskDone(Strict):
    done: bool


def public_run(run):
    return {key: value for key, value in run.items() if key not in {'student_id', 'worker_id'}}


def install_agents(app, llm_factory):
    store = Store()
    router = APIRouter(prefix='/agents', tags=['Agents and memory'])

    @router.get('/capabilities')
    def capabilities(student=Depends(get_current_student)):
        return {'skills': list(SKILLS), 'tools': ['document_search', 'memory_read', 'memory_write', 'task_list', 'task_create'],
                'web_search': False, 'code_execution': False, 'assessment_agent': False}

    @router.get('/memory')
    def memory(course_id: int = Query(gt=0), student=Depends(get_current_student)):
        return store.memory(student['student_id'], course_id)

    @router.patch('/memory/settings')
    def memory_settings(body: MemoryToggle, course_id: int, student=Depends(get_current_student)):
        return store.memory_change(student['student_id'], course_id, active=body.enabled)

    @router.post('/memory', status_code=201)
    def memory_add(body: MemoryInput, course_id: int, student=Depends(get_current_student)):
        return store.memory_change(student['student_id'], course_id, record=body)

    @router.patch('/memory/{record_id}')
    def memory_edit(record_id: UUID, body: MemoryInput, course_id: int, student=Depends(get_current_student)):
        try:
            return store.memory_change(student['student_id'], course_id, record=body, record_id=str(record_id))
        except IntegrityError:
            raise HTTPException(409, 'An identical memory already exists.')

    @router.post('/memory/{record_id}/delete')
    def memory_delete(record_id: UUID, course_id: int, student=Depends(get_current_student)):
        return store.memory_change(student['student_id'], course_id, record_id=str(record_id), remove=True)

    @router.get('/tasks')
    def tasks(course_id: int, student=Depends(get_current_student)):
        return {'items': store.tasks(student['student_id'], course_id)}

    @router.patch('/tasks/{task_id}')
    def task_done(task_id: UUID, body: TaskDone, course_id: int, student=Depends(get_current_student)):
        return store.task_done(student['student_id'], course_id, str(task_id), body.done)

    @router.post('/runs', status_code=202)
    def start(body: RunInput, student=Depends(get_current_student)):
        return public_run(store.create(student['student_id'], body))

    @router.get('/runs')
    def runs(course_id: int, student=Depends(get_current_student)):
        return {'items': [public_run(row) for row in store.runs(student['student_id'], course_id)]}

    @router.get('/runs/{run_id}')
    def get_run(run_id: UUID, course_id: int, student=Depends(get_current_student)):
        return public_run(store.runs(student['student_id'], course_id, str(run_id)))

    @router.post('/runs/{run_id}/cancel')
    def cancel(run_id: UUID, course_id: int, student=Depends(get_current_student)):
        return public_run(store.cancel(student['student_id'], course_id, str(run_id)))

    app.include_router(router)
    previous = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(application):
        with store.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(817264,2)')
            cur.execute(Path(__file__).with_name('schema.sql').read_text())
        worker = str(uuid4())
        stopping = threading.Event()
        active = set()

        async def dispatch():
            while not stopping.is_set():
                try:
                    await run_in_threadpool(store.expire)
                    for task in list(active):
                        if task.done():
                            active.remove(task)
                            if not task.cancelled() and task.exception():
                                log.warning('agent_worker=failed error_type=%s', type(task.exception()).__name__)
                    if len(active) < 2:
                        run = await run_in_threadpool(store.claim, worker)
                        if run:
                            active.add(asyncio.create_task(run_in_threadpool(run_agent, store, run, llm_factory, stopping)))
                except Exception as error:
                    log.warning('agent_dispatch=unavailable error_type=%s', type(error).__name__)
                await asyncio.sleep(1)

        async with previous(application):
            dispatcher = asyncio.create_task(dispatch())
            try:
                yield
            finally:
                stopping.set()
                dispatcher.cancel()
                await asyncio.gather(dispatcher, return_exceptions=True)
                await run_in_threadpool(store.expire, worker)
                # In-flight HTTP work has a bounded timeout; its late output is
                # discarded by the persisted state check before any effect.
    app.router.lifespan_context = lifespan
