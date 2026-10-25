"""Durable, account-scoped generation with cooperative cancellation."""
import asyncio
import contextvars
import logging
from contextlib import asynccontextmanager, contextmanager
from uuid import UUID, uuid4
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from psycopg2.extras import Json, RealDictCursor
from starlette.concurrency import run_in_threadpool
from backend.auth_db import get_auth_connection
from backend.auth_routes import get_current_student
from backend.material_groups import require_materials, selected_ids

log = logging.getLogger(__name__)
current = contextvars.ContextVar('aura_generation', default=None)
SCHEMA = '''CREATE TABLE IF NOT EXISTS aura_generation_jobs (
 id uuid PRIMARY KEY, student_id integer NOT NULL, course_id integer NOT NULL,
 operation text NOT NULL, request jsonb NOT NULL, state text NOT NULL DEFAULT 'queued',
 result jsonb, created_at timestamptz NOT NULL DEFAULT NOW(), updated_at timestamptz NOT NULL DEFAULT NOW(),
 worker_id uuid, deadline timestamptz NOT NULL DEFAULT NOW()+interval '10 minutes');
 ALTER TABLE aura_generation_jobs ADD COLUMN IF NOT EXISTS error_code text;
 CREATE INDEX IF NOT EXISTS aura_generation_owner ON aura_generation_jobs(student_id,course_id,created_at);'''

@contextmanager
def db():
    con = get_auth_connection()
    try:
        with con.cursor(cursor_factory=RealDictCursor) as cur: yield cur
        con.commit()
    except BaseException:
        con.rollback(); raise
    finally: con.close()

class GenerationStopped(BaseException): pass

def guard(cursor=None):
    job = current.get()
    if not job: return
    def check(cur):
        cur.execute('SELECT state,deadline>NOW() AS valid FROM aura_generation_jobs WHERE id=%s AND student_id=%s FOR UPDATE', job)
        row = cur.fetchone()
        if isinstance(row, dict): state, valid = row['state'], row['valid']
        elif row: state, valid = row
        else: raise GenerationStopped()
        if state != 'running' or not valid: raise GenerationStopped()
    if cursor is not None: check(cursor)
    else:
        with db() as cur: check(cur)

class JobInput(BaseModel):
    course_id: int = Field(gt=0)
    operation: str = Field(pattern='^(chat|generate|grade)$')
    payload: dict


def public(row):
    return {'id': str(row['id']), 'course_id': row['course_id'], 'operation': row['operation'],'kind':row.get('kind') or row.get('request',{}).get('kind'),'material_ids':row.get('material_ids') or row.get('request',{}).get('material_ids',[]),
            'state': row['state'], 'status':row['state'], 'progress':{'done':row.get('batches_done',0),'total':row.get('batches_total',0)}, 'requested':row.get('requested_count',0),'delivered':row.get('delivered_count',0),'items':row['result'].get('payload',{}).get('items',[]) if row['result'] else [], 'usage':{k:row.get(k,0) for k in ('prompt_tokens','cached_tokens','completion_tokens')}, 'usage_complete':row.get('usage_complete',True),'model_tier':row.get('model_tier'),'updated_at':row.get('updated_at').isoformat() if hasattr(row.get('updated_at'),'isoformat') else str(row.get('updated_at','')),'error_code':row.get('error_code'), 'result': row['result'], 'created_at': row['created_at'].isoformat() if hasattr(row['created_at'], 'isoformat') else str(row['created_at'])}


def install_generation(app, handlers):
    @app.get('/study/capabilities')
    def capabilities(student=Depends(get_current_student)):
        return {'multi_chat': True, 'multi_study': True, 'multi_agents': True, 'study_jobs': True, 'study_v2': True}

    @app.post('/study/generation-jobs', status_code=202)
    def create(body: JobInput, student=Depends(get_current_student)):
        try: payload = handlers[body.operation][0](body.payload)
        except ValueError: raise HTTPException(422, 'Check the selected materials and generation settings.')
        data = payload.model_dump(mode='json')
        if data.get('course_id', body.course_id) != body.course_id: raise HTTPException(422, 'Choose one workspace.')
        with db() as cur:
            cur.execute('SELECT course_id FROM courses WHERE course_id=%s AND owner_student_id=%s', (body.course_id, student['student_id']))
            if cur.fetchone() is None: raise HTTPException(404, 'Workspace not found.')
            try: ids = selected_ids(data.get('source_id'), data.get('material_ids', []))
            except ValueError: raise HTTPException(422, 'Choose up to five distinct materials.')
            require_materials(cur, student['student_id'], body.course_id, ids)
            if body.operation == 'grade':
                cur.execute('''SELECT a.id FROM aura_study_artifacts a JOIN sources s ON s.source_id=a.source_id JOIN courses c ON c.course_id=s.course_id
                    WHERE a.id=%s AND a.course_id=%s AND a.student_id=%s AND s.owner_student_id=%s AND c.owner_student_id=%s''',
                            (data['artifact_id'], body.course_id, student['student_id'], student['student_id'], student['student_id']))
                if cur.fetchone() is None: raise HTTPException(404, 'Assessment not found.')
            cur.execute('SELECT pg_advisory_xact_lock(817264,8)')
            cur.execute("SELECT count(*) AS n FROM aura_generation_jobs WHERE state IN ('queued','running') AND deadline>NOW()")
            if cur.fetchone()['n'] >= 20: raise HTTPException(429, 'Aura is busy. Please try again shortly.')
            cur.execute("SELECT count(*) AS n FROM aura_generation_jobs WHERE student_id=%s AND state IN ('queued','running','cancelling') AND deadline>NOW()", (student['student_id'],))
            if cur.fetchone()['n'] >= 1: raise HTTPException(429, {'code':'one_job_at_a_time','message':'Finish or stop your current generation before starting another.'})
            if data.get('generation_version') == 2:
                cur.execute('''INSERT INTO aura_generation_jobs(id,student_id,course_id,operation,request,kind,material_ids,params,requested_count)
                    VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
                    (str(uuid4()),student['student_id'],body.course_id,body.operation,Json(data),data['kind'],ids,Json(data),data.get('count',0)))
            else:
                cur.execute('INSERT INTO aura_generation_jobs(id,student_id,course_id,operation,request) VALUES(%s,%s,%s,%s,%s) RETURNING *',
                            (str(uuid4()), student['student_id'], body.course_id, body.operation, Json(data)))
            return public(cur.fetchone())

    app.state.start_generation=create

    def owned(cur, student, course, job, cancel=False):
        if cancel:
            cur.execute("UPDATE aura_generation_jobs SET state=CASE WHEN state IN ('queued','running') THEN CASE WHEN state='running' AND request->>'generation_version'='2' THEN 'cancelling' WHEN result IS NOT NULL AND COALESCE(result->'payload'->'items','[]'::jsonb) <> '[]'::jsonb THEN 'partial' ELSE 'cancelled' END ELSE state END,updated_at=NOW() WHERE id=%s AND course_id=%s AND student_id=%s RETURNING *", (str(job), course, student['student_id']))
        else: cur.execute('SELECT * FROM aura_generation_jobs WHERE id=%s AND course_id=%s AND student_id=%s', (str(job), course, student['student_id']))
        row = cur.fetchone()
        if row is None: raise HTTPException(404, 'Saved work not found.')
        return public(row)

    @app.get('/study/generation-jobs/{job_id}')
    def read(job_id: UUID, course_id: int, student=Depends(get_current_student)):
        with db() as cur: return owned(cur, student, course_id, job_id)

    @app.post('/study/generation-jobs/{job_id}/cancel')
    def cancel(job_id: UUID, course_id: int, student=Depends(get_current_student)):
        with db() as cur: return owned(cur, student, course_id, job_id, True)

    def claim(worker):
        with db() as cur:
            cur.execute("UPDATE aura_generation_jobs SET state=CASE WHEN result IS NOT NULL THEN 'partial' ELSE 'failed' END,error_code='generation_timeout',updated_at=NOW() WHERE state IN ('queued','running','cancelling') AND deadline<=NOW()")
            cur.execute("""WITH next AS (SELECT id FROM aura_generation_jobs WHERE state='queued' ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE aura_generation_jobs j SET state='running',worker_id=%s,updated_at=NOW() FROM next WHERE j.id=next.id RETURNING j.*""", (worker,))
            return cur.fetchone()

    def execute(row):
        token = current.set((str(row['id']), row['student_id']))
        try:
            guard()
            result = handlers[row['operation']][1](row['request'], {'student_id': row['student_id']})
            with db() as cur:
                guard(cur)
                cur.execute("UPDATE aura_generation_jobs SET state='completed',result=%s,updated_at=NOW() WHERE id=%s", (Json(result), str(row['id'])))
        except GenerationStopped:
            with db() as cur:
                cur.execute("UPDATE aura_generation_jobs SET state=CASE WHEN result IS NOT NULL AND COALESCE(result->'payload'->'items','[]'::jsonb)<>'[]'::jsonb THEN 'partial' ELSE 'cancelled' END,error_code='cancelled',updated_at=NOW() WHERE id=%s AND state='cancelling'",(str(row['id']),))
        except Exception as error:
            log.warning('generation_job=failed error_type=%s', type(error).__name__)
            code=error.detail.get('code') if isinstance(error,HTTPException) and isinstance(error.detail,dict) else None
            code=code if code in ('daily_token_budget','over_cap','one_job_at_a_time') else 'generation_unavailable'
            with db() as cur:
                cur.execute("UPDATE aura_generation_jobs SET state=CASE WHEN result IS NOT NULL THEN 'partial' ELSE 'failed' END,error_code=%s,updated_at=NOW() WHERE id=%s AND state='running'", (code,str(row['id'])))
        finally: current.reset(token)

    previous = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        with db() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(817264,9)')
            cur.execute(SCHEMA)
        worker = str(uuid4()); tasks = set()
        async def dispatch():
            while True:
                try:
                    tasks.difference_update(task for task in list(tasks) if task.done())
                    if len(tasks) < 2:
                        row = await run_in_threadpool(claim, worker)
                        if row: tasks.add(asyncio.create_task(run_in_threadpool(execute, row)))
                except Exception as error: log.warning('generation_queue=unavailable error_type=%s', type(error).__name__)
                await asyncio.sleep(1)
        async with previous(application):
            dispatcher = asyncio.create_task(dispatch())
            try: yield
            finally:
                dispatcher.cancel(); await asyncio.gather(dispatcher, return_exceptions=True)
                with db() as cur:
                    cur.execute("UPDATE aura_generation_jobs SET state='failed',updated_at=NOW() WHERE worker_id=%s AND state='running'", (worker,))
                if tasks: await asyncio.gather(*tasks, return_exceptions=True)
    app.router.lifespan_context = lifespan
