"""Durable local preparation queue; one GPU preparation job across API workers."""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Event, Thread
from uuid import UUID, uuid4

from fastapi import Depends, File, HTTPException, UploadFile
from psycopg2.extras import Json, RealDictCursor
from starlette.concurrency import run_in_threadpool

from backend.auth_routes import get_current_student
from backend.ingestion.utils import MAX_FILE_SIZE, get_file_type
from backend.preparation_progress import preparation_progress

logger = logging.getLogger(__name__)
FIELDS = 'id,course_id,source_id,filename,state,stage,completed,total,result,error,created_at,updated_at'

def public_job(row):
    value = dict(row)
    value.pop('staged_path', None)
    value.pop('student_id', None)
    value['id'] = str(value['id'])
    value['percentage'] = (min(100, int(100 * value['completed'] / value['total']))
                           if value['total'] > 0 else None)
    return value

class PreparationWorker:
    def __init__(self, legacy, database, require_course, require_source):
        self.legacy, self.database = legacy, database
        self.require_course, self.require_source = require_course, require_source
        self.stop_event = Event()
        self.thread = Thread(target=self.loop, name='aura-preparation', daemon=True)

    def initialize(self):
        with self.database() as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(9135, 1)')
                cursor.execute((Path(__file__).with_name('preparation_jobs.sql')).read_text())

    def change(self, job_id, **fields):
        # Keys only come from this module; values always use parameters.
        allowed = {'state','stage','completed','total','result','error','source_id'}
        if not fields.keys() <= allowed:
            raise ValueError('Unexpected job field')
        with self.database() as connection:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE aura_preparation_jobs SET ' +
                               ','.join(f'{key}=%s' for key in fields) +
                               ',updated_at=NOW() WHERE id=%s',
                               (*fields.values(), str(job_id)))

    def process(self, row):
        job_id, student_id, course_id = str(row['id']), row['student_id'], row['course_id']
        last_progress = [None, 0.0]
        def progress(stage, completed=0, total=0):
            now = time.monotonic()
            # Bound progress writes without hiding completed work or new stages.
            if stage == last_progress[0] and completed != total and now-last_progress[1] < .5:
                return
            self.change(job_id, stage=stage, completed=completed, total=total)
            last_progress[:] = [stage, now]
        try:
            with self.database() as connection:
                with connection.cursor() as cursor:
                    self.require_course(cursor, course_id, student_id)
                    if row['source_id']:
                        self.require_source(cursor, row['source_id'], student_id, course_id)
            with preparation_progress(progress):
                result = row.get('result')
                if not row['source_id']:
                    progress('reading')
                    with open(row['staged_path'], 'rb') as stream:
                        file = UploadFile(filename=row['filename'], file=stream)
                        result = asyncio.run(self.legacy.upload_course_source(
                            course_id=course_id, file=file, owner_student_id=student_id))
                    source_id = result['source_id']
                    self.change(job_id, source_id=source_id, result=Json(result))
                else:
                    source_id = row['source_id']
                if not result or result.get('status') not in {'success','partial'} or result.get('chunks_created',0) < 1:
                    warnings = '; '.join(str(w) for w in (result or {}).get('warnings', []))
                    raise HTTPException(400, warnings or 'No readable content was found. Try another file.')
                progress('loading_model')
                self.legacy.generate_source_embeddings(source_id)
            self.change(job_id, state='ready', stage='ready', completed=1, total=1, error=None)
            Path(row['staged_path']).unlink(missing_ok=True)
        except Exception as error:
            logger.exception('Preparation job failed: %s', job_id)
            message = (str(error.detail)[:1000]
                       if isinstance(error, HTTPException) and error.status_code == 400 else
                       'Preparation could not finish. Check the backend terminal, then retry.')
            self.change(job_id, state='failed', stage='failed', error=message)

    def loop(self):
        while not self.stop_event.is_set():
            try:
                # Session advisory lock bounds GPU use across processes as well
                # as threads. A dead backend releases it automatically.
                with self.database() as guard:
                    with guard.cursor() as cursor:
                        cursor.execute('SELECT pg_try_advisory_lock(9135, 2)')
                        acquired = cursor.fetchone()[0]
                        guard.commit()
                        if acquired:
                            try:
                                with self.database() as connection:
                                    with connection.cursor(cursor_factory=RealDictCursor) as jobs:
                                        jobs.execute("""UPDATE aura_preparation_jobs SET state='failed',stage='failed',
                                            error='Preparation was interrupted by a backend restart. Retry to continue.',updated_at=NOW()
                                            WHERE state='processing'""")
                                        jobs.execute("""UPDATE aura_preparation_jobs SET state='processing',stage='reading',updated_at=NOW()
                                            WHERE id=(SELECT id FROM aura_preparation_jobs WHERE state='queued'
                                                ORDER BY created_at LIMIT 1 FOR UPDATE SKIP LOCKED)
                                            RETURNING *""")
                                        row = jobs.fetchone()
                                if row:
                                    self.process(row)
                            finally:
                                cursor.execute('SELECT pg_advisory_unlock(9135, 2)')
            except Exception:
                logger.exception('Preparation queue unavailable')
            self.stop_event.wait(1)

def install_preparation_jobs(app, legacy, database, require_course, require_source):
    worker = PreparationWorker(legacy, database, require_course, require_source)
    previous_lifespan = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        async with previous_lifespan(application):
            await run_in_threadpool(worker.initialize)
            worker.thread.start()
            try:
                yield
            finally:
                worker.stop_event.set()
                await run_in_threadpool(worker.thread.join, 2)
    app.router.lifespan_context = lifespan

    def owned_job(cursor, job_id, student_id):
        cursor.execute(f'SELECT {FIELDS},staged_path FROM aura_preparation_jobs WHERE id=%s AND student_id=%s',
                       (str(job_id), student_id))
        row = cursor.fetchone()
        if row is None:
            raise HTTPException(404, 'Preparation not found.')
        return row

    @app.post('/courses/{course_id}/preparation-jobs', status_code=202)
    async def upload_job(course_id: int, file: UploadFile = File(...), student=Depends(get_current_student)):
        filename = Path((file.filename or '').replace('\\','/')).name
        if not filename or get_file_type(filename) in {None,'webm'}:
            raise HTTPException(400, 'Choose a supported PDF, presentation, document, JPEG/PNG image, audio or MP4 file.')
        def check():
            with database() as connection:
                with connection.cursor() as cursor:
                    require_course(cursor, course_id, student['student_id'])
        await run_in_threadpool(check)
        job_id = uuid4()
        directory = Path(__file__).parent / 'uploads' / 'preparation'
        directory.mkdir(parents=True, exist_ok=True)
        staged = directory / f'{job_id.hex}{Path(filename).suffix.lower()}'
        try:
            size = 0
            with staged.open('xb') as stream:
                while block := await file.read(1024*1024):
                    size += len(block)
                    if size > MAX_FILE_SIZE:
                        raise HTTPException(413, 'File exceeds 100 MiB.')
                    await run_in_threadpool(stream.write, block)
            if size == 0:
                raise HTTPException(400, 'The file is empty.')
            def create():
                with database() as connection:
                    with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                        require_course(cursor, course_id, student['student_id'])
                        cursor.execute('SELECT pg_advisory_xact_lock(9135, 3)')
                        cursor.execute("SELECT COUNT(*) AS count FROM aura_preparation_jobs WHERE state IN ('queued','processing')")
                        if cursor.fetchone()['count'] >= 5:
                            raise HTTPException(429, 'Preparation queue is full. Please wait for a file to finish.')
                        cursor.execute(f'''INSERT INTO aura_preparation_jobs(id,student_id,course_id,filename,staged_path)
                            VALUES (%s,%s,%s,%s,%s) RETURNING {FIELDS}''',
                            (str(job_id), student['student_id'], course_id, filename, str(staged)))
                        return public_job(cursor.fetchone())
            return await run_in_threadpool(create)
        except Exception:
            staged.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.get('/preparation-jobs/{job_id}')
    def job_status(job_id: UUID, student=Depends(get_current_student)):
        with database() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                row = owned_job(cursor, job_id, student['student_id'])
                require_course(cursor, row['course_id'], student['student_id'])
                row.pop('staged_path')
                return public_job(row)

    @app.get('/preparation-jobs')
    def job_list(course_id: int, student=Depends(get_current_student)):
        with database() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                require_course(cursor, course_id, student['student_id'])
                cursor.execute(f'''SELECT {FIELDS} FROM aura_preparation_jobs WHERE course_id=%s AND student_id=%s
                    ORDER BY created_at DESC LIMIT 20''', (course_id, student['student_id']))
                return {'jobs': [public_job(row) for row in cursor.fetchall()]}

    @app.post('/preparation-jobs/{job_id}/retry', status_code=202)
    def retry_job(job_id: UUID, student=Depends(get_current_student)):
        with database() as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(9135, 3)')
                row = owned_job(cursor, job_id, student['student_id'])
                require_course(cursor, row['course_id'], student['student_id'])
                if row['state'] != 'failed':
                    raise HTTPException(409, 'This file is already preparing or ready.')
                if not row['source_id'] and not Path(row['staged_path']).is_file():
                    raise HTTPException(409, 'Upload the file again to restart preparation.')
                cursor.execute("SELECT COUNT(*) AS count FROM aura_preparation_jobs WHERE state IN ('queued','processing')")
                if cursor.fetchone()['count'] >= 5:
                    raise HTTPException(429, 'Preparation queue is full. Please try again later.')
                cursor.execute(f'''UPDATE aura_preparation_jobs SET state='queued',stage='queued',completed=0,total=0,error=NULL,
                    updated_at=NOW() WHERE id=%s RETURNING {FIELDS}''', (str(job_id),))
                return public_job(cursor.fetchone())
