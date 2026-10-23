"""Parameterized PostgreSQL operations. Account identity is never model supplied."""
import logging
import json
import hashlib
import unicodedata
from contextlib import contextmanager
from uuid import uuid4
from fastapi import HTTPException
from psycopg2.extras import Json, RealDictCursor
from backend.auth_db import get_auth_connection
from backend.agents.contracts import RunInput, TaskInput, allowed_tools, requested_days, requested_questions
from backend.agents.planning import action_key
from backend.agents.web import MAX_WEB_SEARCHES, WebSearchUnavailable, search_web

log = logging.getLogger(__name__)

ACTIVE = ('queued', 'running')


def signature(text):
    return hashlib.sha256(' '.join(unicodedata.normalize('NFKC', text).casefold().split()).encode()).hexdigest()


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


def scope(cur, student, course, source=None):
    cur.execute('SELECT course_id FROM courses WHERE course_id=%s AND owner_student_id=%s', (course, student))
    if cur.fetchone() is None:
        raise HTTPException(404, 'Workspace not found.')
    if source is not None:
        cur.execute('SELECT source_id FROM sources WHERE source_id=%s AND course_id=%s AND owner_student_id=%s',
                    (source, course, student))
        if cur.fetchone() is None:
            raise HTTPException(404, 'Material not found.')


def enabled(cur, student, course):
    cur.execute('SELECT enabled FROM aura_memory_settings WHERE student_id=%s AND course_id=%s', (student, course))
    row = cur.fetchone()
    return row is None or row['enabled']


def memories(cur, student, course, *, for_agent=False):
    active = enabled(cur, student, course)
    if for_agent and not active:
        return {'enabled': False, 'items': []}
    cur.execute('SELECT id,record,updated_at FROM aura_memories WHERE student_id=%s AND course_id=%s ORDER BY updated_at DESC LIMIT 100', (student, course))
    return {'enabled': active, 'items': [dict(row) for row in cur.fetchall()]}


def save_memory(cur, student, course, record):
    cur.execute('''SELECT COUNT(*) AS count FROM aura_memories WHERE student_id=%s AND course_id=%s
        AND NOT (kind=%s AND dedup_key=%s)''', (student, course, record.kind, signature(record.text)))
    if cur.fetchone()['count'] >= 100:
        raise HTTPException(409, 'Memory is full. Delete an older record before saving another.')
    cur.execute('''INSERT INTO aura_memories(id,student_id,course_id,kind,dedup_key,record)
        VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(student_id,course_id,kind,dedup_key)
        DO UPDATE SET record=EXCLUDED.record,updated_at=NOW() RETURNING id,record,updated_at''',
        (str(uuid4()), student, course, record.kind, signature(record.text), Json(record.model_dump())))
    return dict(cur.fetchone())


def save_task(cur, student, course, task, *, namespace=''):
    cur.execute('''INSERT INTO aura_agent_tasks(id,student_id,course_id,title,details,dedup_key)
        VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(student_id,course_id,dedup_key)
        DO UPDATE SET title=aura_agent_tasks.title RETURNING id,title,details,done,created_at''',
        (str(uuid4()), student, course, task.title.strip(), task.details, signature(namespace + task.title)))
    return dict(cur.fetchone())


def assessment_history(cur, run):
    cur.execute('''SELECT payload FROM aura_study_artifacts WHERE student_id=%s AND course_id=%s
        AND source_id=%s AND kind IN ('assessment','flashcards') ORDER BY created_at DESC LIMIT 100''',
        (run['student_id'], run['course_id'], run['source_id']))
    history = []
    for row in cur.fetchall():
        for item in row['payload'].get('items', []):
            answer = next((choice['text'] for choice in item.get('choices', [])
                           if choice['id'] == item.get('correct_choice_id')), item.get('answer', ''))
            history.append({'prompt': item.get('prompt') or item.get('question', ''), 'answer': answer})
    return history


class Store:
    def __init__(self, connect=database):
        self.connect = connect

    @contextmanager
    def cursor(self, student=None, course=None, source=None):
        with self.connect() as con:
            with con.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("SET LOCAL statement_timeout = '5s'")
                cur.execute("SET LOCAL lock_timeout = '2s'")
                if student is not None:
                    scope(cur, student, course, source)
                yield cur

    def memory(self, student, course):
        with self.cursor(student, course) as cur:
            return memories(cur, student, course)

    def memory_change(self, student, course, record=None, record_id=None, *, remove=False, active=None):
        with self.cursor(student, course) as cur:
            # Also serializes the toggle with an agent's memory write.
            cur.execute('SELECT pg_advisory_xact_lock(%s,%s)', (student, course))
            if active is not None:
                cur.execute('''INSERT INTO aura_memory_settings(student_id,course_id,enabled) VALUES(%s,%s,%s)
                    ON CONFLICT(student_id,course_id) DO UPDATE SET enabled=EXCLUDED.enabled''', (student, course, active))
                return {'enabled': active}
            if record_id is None:
                return save_memory(cur, student, course, record)
            if remove:
                cur.execute('DELETE FROM aura_memories WHERE id=%s AND student_id=%s AND course_id=%s RETURNING id', (record_id, student, course))
            else:
                cur.execute('''UPDATE aura_memories SET record=%s,kind=%s,dedup_key=%s,updated_at=NOW()
                    WHERE id=%s AND student_id=%s AND course_id=%s RETURNING id,record,updated_at''',
                    (Json(record.model_dump()), record.kind, signature(record.text), record_id, student, course))
            row = cur.fetchone()
            if row is None:
                raise HTTPException(404, 'Memory not found.')
            return dict(row)

    def tasks(self, student, course):
        with self.cursor(student, course) as cur:
            cur.execute('SELECT id,title,details,done,created_at FROM aura_agent_tasks WHERE student_id=%s AND course_id=%s ORDER BY created_at DESC LIMIT 100', (student, course))
            return [dict(row) for row in cur.fetchall()]

    def task_done(self, student, course, task_id, done):
        with self.cursor(student, course) as cur:
            cur.execute('UPDATE aura_agent_tasks SET done=%s WHERE id=%s AND student_id=%s AND course_id=%s RETURNING id,title,details,done,created_at', (done, task_id, student, course))
            row = cur.fetchone()
            if row is None:
                raise HTTPException(404, 'Task not found.')
            return dict(row)

    def create(self, student, request):
        with self.cursor(student, request.course_id, request.source_id) as cur:
            if request.skill == 'code_analysis':
                from backend.agents.sandbox import backend_name
                if not backend_name():
                    raise HTTPException(503, 'Code execution is unavailable on this server.')
            cur.execute('SELECT pg_advisory_xact_lock(817264,3)')
            cur.execute("SELECT COUNT(*) AS count FROM aura_agent_runs WHERE state IN ('queued','running')")
            if cur.fetchone()['count'] >= 20:
                raise HTTPException(429, 'The agent queue is full. Try again shortly.')
            cur.execute("SELECT COUNT(*) AS count FROM aura_agent_runs WHERE student_id=%s AND state IN ('queued','running')", (student,))
            if cur.fetchone()['count'] >= 2:
                raise HTTPException(429, 'Finish or cancel one of your active runs first.')
            cur.execute('''INSERT INTO aura_agent_runs(id,student_id,course_id,source_id,request)
                VALUES(%s,%s,%s,%s,%s) RETURNING *''',
                (str(uuid4()), student, request.course_id, request.source_id, Json(request.model_dump())))
            return dict(cur.fetchone())

    def runs(self, student, course, run_id=None):
        with self.cursor(student, course) as cur:
            cur.execute('''SELECT * FROM aura_agent_runs WHERE student_id=%s AND course_id=%s
                AND (%s::uuid IS NULL OR id=%s)
                ORDER BY CASE WHEN state IN ('queued','running') THEN 0 ELSE 1 END,created_at DESC LIMIT 20''',
                (student, course, run_id, run_id))
            rows = [dict(row) for row in cur.fetchall()]
            if run_id and not rows:
                raise HTTPException(404, 'Agent run not found.')
            return rows[0] if run_id else rows

    def cancel(self, student, course, run_id):
        with self.cursor(student, course) as cur:
            cur.execute('''UPDATE aura_agent_runs SET state=CASE WHEN state IN ('queued','running')
                THEN 'cancelled' ELSE state END,updated_at=NOW()
                WHERE id=%s AND student_id=%s AND course_id=%s RETURNING *''', (run_id, student, course))
            row = cur.fetchone()
            if row is None:
                raise HTTPException(404, 'Agent run not found.')
            return dict(row)

    def claim(self, worker):
        with self.cursor() as cur:
            cur.execute('''WITH next AS (SELECT id FROM aura_agent_runs WHERE state='queued'
                ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE aura_agent_runs r SET state='running',worker_id=%s,started_at=NOW(),updated_at=NOW()
                FROM next WHERE r.id=next.id RETURNING r.*''', (worker,))
            row = cur.fetchone()
            return dict(row) if row else None

    def expire(self, worker=None):
        with self.cursor() as cur:
            if worker:
                cur.execute("UPDATE aura_agent_runs SET state='interrupted',error_code='server_stopped',updated_at=NOW() WHERE worker_id=%s AND state='running'", (worker,))
            else:
                cur.execute("""UPDATE aura_agent_runs SET state='timed_out',error_code='time_budget',updated_at=NOW()
                    WHERE state='running' AND started_at + ((request->>'max_seconds')::int * interval '1 second') < NOW()""")

    @contextmanager
    def locked(self, run):
        with self.cursor(run['student_id'], run['course_id'], run['source_id']) as cur:
            cur.execute('''SELECT *,EXTRACT(EPOCH FROM clock_timestamp()-started_at)::float8 AS elapsed FROM aura_agent_runs
                WHERE id=%s AND student_id=%s AND course_id=%s FOR UPDATE''',
                (run['id'], run['student_id'], run['course_id']))
            current = cur.fetchone()
            if not current or current['state'] != 'running':
                raise RunStopped()
            if current['elapsed'] >= current['request']['max_seconds']:
                cur.execute("UPDATE aura_agent_runs SET state='timed_out',error_code='time_budget' WHERE id=%s AND student_id=%s", (run['id'], run['student_id']))
            else:
                yield cur, current
                return
        # Leave the transaction before raising, so the expiry is committed.
        raise RunStopped()

    def record(self, run, step=None, *, tokens=0, state=None, result=None, error=None):
        with self.locked(run) as (cur, current):
            cur.execute('''UPDATE aura_agent_runs SET steps=steps || %s::jsonb,tokens_used=tokens_used+%s,
                state=COALESCE(%s,state),result=COALESCE(%s,result),error_code=%s,updated_at=NOW()
                WHERE id=%s AND student_id=%s AND course_id=%s''',
                (Json([step] if step else []), tokens, state, Json(result) if result is not None else None,
                 error, run['id'], run['student_id'], run['course_id']))
            return True

    def tool(self, run, action, step):
        if action.tool == 'code_execute':
            return self.code_tool(run, action, step)
        if action.tool == 'assessment_create':
            raise HTTPException(409, 'Assessment drafts must be checked before saving.')
        if action.tool == 'web_search':
            return self.web_tool(run, action, step)
        with self.locked(run) as (cur, current):
            request = RunInput.model_validate(current['request'])
            if action.tool not in allowed_tools(request):
                raise HTTPException(403, 'This tool is not enabled for the run.')
            previous = [item for item in current['steps'] if item.get('state') == 'completed']
            limit = {'document_search': 2, 'memory_read': 1, 'task_list': 1}.get(action.tool)
            if limit is not None and sum(item.get('tool') == action.tool for item in previous) >= limit:
                raise HTTPException(409, 'This read tool has reached its per-run limit.')
            if action.tool == 'document_search' and any(item.get('action_key') == action_key(action) for item in previous):
                raise HTTPException(409, 'This search has already completed.')
            step['action'] = action.model_dump()
            step['action_key'] = action_key(action)
            step['state'] = 'completed'
            student, course = run['student_id'], run['course_id']
            if action.tool == 'memory_read':
                output = memories(cur, student, course, for_agent=True)
                output['items'] = [{'record': {**row['record'], 'text': row['record']['text'][:300]}}
                                   for row in output['items'][:8]]
            elif action.tool == 'memory_write':
                cur.execute('SELECT pg_advisory_xact_lock(%s,%s)', (student, course))
                if not enabled(cur, student, course):
                    raise HTTPException(409, 'Memory is turned off.')
                output = save_memory(cur, student, course, action.record)
            elif action.tool == 'task_list':
                cur.execute('SELECT id,title,left(details,300) AS details,done FROM aura_agent_tasks WHERE student_id=%s AND course_id=%s ORDER BY created_at DESC LIMIT 8', (student, course))
                output = [dict(row) for row in cur.fetchall()]
            elif action.tool == 'task_create':
                output = save_task(cur, student, course, action.task)
            elif action.tool == 'study_plan_create':
                target = requested_days(request.goal)
                references = {p['reference'] for item in previous if item.get('tool') == 'document_search'
                              for p in item.get('observation', {}).get('passages', [])}
                if (target is not None and not any(item.get('tool') == 'document_search' for item in previous)):
                    raise HTTPException(422, 'Consult the selected material before creating the daily plan.')
                if (target is not None and len(action.days) != target) or any(
                        ref not in references for day in action.days for ref in day.references):
                    raise HTTPException(422, 'Plan days or document references do not match this run.')
                tasks = [save_task(cur, student, course,
                    TaskInput(title=f'Day {day.day}: {day.title}', details=day.details), namespace=str(run['id']) + ':')
                    for day in action.days]
                output = {'plan': action.model_dump(), 'tasks': tasks}
            elif action.tool == 'document_search':
                cur.execute('''SELECT ch.chunk_id,ch.content,ch.page_number,ch.slide_number,s.source_name
                    FROM chunks ch JOIN sources s ON s.source_id=ch.source_id JOIN courses c ON c.course_id=s.course_id
                    WHERE s.course_id=%s AND s.owner_student_id=%s AND c.owner_student_id=%s
                    AND (%s::integer IS NULL OR s.source_id=%s) AND btrim(COALESCE(ch.content,''))<>''
                    ORDER BY ts_rank_cd(to_tsvector('simple',ch.content),plainto_tsquery('simple',%s)) DESC,ch.chunk_id LIMIT 4''',
                    (course, student, student, run['source_id'], run['source_id'], action.query))
                output = {'passages': [{'reference': 'D'+str(row['chunk_id']), 'text': row['content'][:900],
                    'title': row['source_name'], 'page': row['page_number'], 'slide': row['slide_number']}
                    for row in cur.fetchall()], 'source': 'uploaded_material', 'untrusted_data': True}
                if request.skill == 'assessment':
                    output['previous_questions'] = [item['prompt'][:600] for item in assessment_history(cur, run)[:10]]
            else:
                raise ValueError('Unknown tool.')
            # Data effects and their observed step commit as one transaction.
            from fastapi.encoders import jsonable_encoder
            step['observation'] = jsonable_encoder(output)
            cur.execute('UPDATE aura_agent_runs SET steps=steps || %s::jsonb,updated_at=NOW() WHERE id=%s AND student_id=%s AND course_id=%s',
                (Json([step]), run['id'], student, course))
            return step['observation']


    def code_tool(self, run, action, step):
        from backend.agents import sandbox
        with self.locked(run) as (cur, current):
            request = RunInput.model_validate(current['request'])
            if request.skill != 'code_analysis' or action.tool not in allowed_tools(request):
                raise HTTPException(403, 'Code execution is not enabled for this run.')
            attempts = [item for item in current['steps'] if item.get('tool') == 'code_execute']
            if len(attempts) >= sandbox.MAX_EXECUTIONS or any(item.get('action_key') == action_key(action) for item in attempts):
                raise HTTPException(409, 'Code execution has already run or reached its limit.')
            if current['tokens_used'] >= request.max_tokens or len(current['steps']) >= request.max_steps:
                raise HTTPException(409, 'The run has reached its budget.')
            index = len(current['steps'])
            remaining = min(30, request.max_seconds - current['elapsed'])
            files = {item.name: item.text for item in request.inputs}
            passages = {p['reference']: p for item in current['steps'] if item.get('tool') == 'document_search'
                        and item.get('state') == 'completed' for p in item.get('observation', {}).get('passages', [])}
            if passages:
                files['material.json'] = json.dumps(list(passages.values()))
            step.update(state='running', action=action.model_dump(), action_key=action_key(action), cleanup_pending=False)
            cur.execute('UPDATE aura_agent_runs SET steps=steps || %s::jsonb,updated_at=NOW() WHERE id=%s AND student_id=%s AND course_id=%s',
                        (Json([step]), run['id'], run['student_id'], run['course_id']))

        def check_active():
            with self.locked(run):
                pass

        def on_start(handle):
            with self.locked(run) as (cur, current):
                step.update(execution=handle, cleanup_pending=True)
                cur.execute('UPDATE aura_agent_runs SET steps=jsonb_set(steps,ARRAY[%s]::text[],%s::jsonb),updated_at=NOW() WHERE id=%s AND student_id=%s AND course_id=%s',
                            (str(index), Json(step), run['id'], run['student_id'], run['course_id']))

        try:
            output = sandbox.execute(action.code, action.outputs, files, run_id=run['id'], attempt=len(attempts)+1,
                                     seconds=remaining, check_active=check_active, on_start=on_start)
        except sandbox.SandboxUnavailable as error:
            with self.locked(run) as (cur, current):
                step.update(state='failed', error_code=error.code)
                cur.execute('UPDATE aura_agent_runs SET steps=jsonb_set(steps,ARRAY[%s]::text[],%s::jsonb),updated_at=NOW() WHERE id=%s AND student_id=%s AND course_id=%s',
                            (str(index), Json(step), run['id'], run['student_id'], run['course_id']))
            raise
        with self.locked(run) as (cur, current):
            reserved = current['steps'][index] if len(current['steps']) > index else {}
            if reserved.get('state') != 'running' or reserved.get('action_key') != action_key(action):
                raise RunStopped()
            step.update(state='completed', observation=output, cleanup_pending=False)
            cur.execute('UPDATE aura_agent_runs SET steps=jsonb_set(steps,ARRAY[%s]::text[],%s::jsonb),updated_at=NOW() WHERE id=%s AND student_id=%s AND course_id=%s',
                        (str(index), Json(step), run['id'], run['student_id'], run['course_id']))
        return output

    def cleanup_code(self):
        """Retry cleanup of owned terminal-run handles after cancellation/restart."""
        from backend.agents.sandbox import cleanup
        with self.cursor() as cur:
            cur.execute('''SELECT id,student_id,course_id,steps FROM aura_agent_runs
                WHERE state NOT IN ('queued','running') AND steps @> %s::jsonb ORDER BY updated_at LIMIT 2''',
                (Json([{'tool': 'code_execute', 'cleanup_pending': True}]),))
            rows = [dict(row) for row in cur.fetchall()]
        for row in rows:
            for index, step in enumerate(row['steps']):
                if step.get('tool') == 'code_execute' and step.get('cleanup_pending') and step.get('execution') and cleanup(step['execution']):
                    with self.cursor() as cur:
                        cur.execute('''UPDATE aura_agent_runs SET steps=jsonb_set(steps,ARRAY[%s,'cleanup_pending']::text[],%s::jsonb)
                            WHERE id=%s AND student_id=%s AND course_id=%s''',
                            (str(index), Json(False), row['id'], row['student_id'], row['course_id']))

    def assessment_draft(self, run, action):
        from backend.agents.assessment import assessment_payload
        with self.locked(run) as (cur, current):
            request = RunInput.model_validate(current['request'])
            if request.skill != 'assessment' or action.tool not in allowed_tools(request):
                raise HTTPException(403, 'Assessment creation is not enabled for this run.')
            count = requested_questions(request.goal)
            if count is not None and len(action.questions) != count:
                raise HTTPException(422, 'The quiz must match the requested question count.')
            history = assessment_history(cur, run)
            return assessment_payload(current, action, current['steps'], history), history

    def finish_verification(self, run, approval=None, *, error=None):
        with self.locked(run) as (cur, current):
            index = len(current['steps']) - 1
            if index < 0 or current['steps'][index].get('tool') != 'verification':
                raise RunStopped()
            cur.execute('''UPDATE aura_agent_runs SET steps=jsonb_set(steps,ARRAY[%s,'state']::text[],%s::jsonb),
                updated_at=NOW() WHERE id=%s AND student_id=%s AND course_id=%s''',
                (str(index), Json('failed' if error else 'completed'), run['id'], run['student_id'], run['course_id']))
            if error:
                if approval is not None:
                    raise ValueError('A failed check cannot approve a quiz.')
                cur.execute('''UPDATE aura_agent_runs SET steps=jsonb_set(steps,ARRAY[%s,'error_code']::text[],%s::jsonb)
                    WHERE id=%s AND student_id=%s AND course_id=%s''',
                    (str(index), Json(error), run['id'], run['student_id'], run['course_id']))
            if approval is not None:
                digest = hashlib.sha256(json.dumps(approval, sort_keys=True).encode()).hexdigest()
                cur.execute('''UPDATE aura_agent_runs SET steps=jsonb_set(steps,ARRAY[%s,'approval']::text[],%s::jsonb)
                    WHERE id=%s AND student_id=%s AND course_id=%s''',
                    (str(index), Json(digest), run['id'], run['student_id'], run['course_id']))

    def save_assessment(self, run, action, step, payload):
        from backend.agents.assessment import assessment_result
        with self.locked(run) as (cur, current):
            request = RunInput.model_validate(current['request'])
            if request.skill != 'assessment' or action.tool not in allowed_tools(request):
                raise HTTPException(403, 'Assessment creation is not enabled for this run.')
            if (payload['agent_run_id'] != str(run['id']) or payload['source_id'] != run['source_id']
                    or payload['course_id'] != run['course_id'] or len(payload['items']) != len(action.questions)):
                raise HTTPException(422, 'The quiz does not match this run.')
            if current['tokens_used'] >= request.max_tokens or len(current['steps']) >= request.max_steps:
                raise HTTPException(409, 'The run has reached its budget.')
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
            last = current['steps'][-1] if current['steps'] else {}
            if last.get('tool') != 'verification' or last.get('state') != 'completed' or last.get('approval') != digest:
                raise HTTPException(409, 'The quiz needs a successful source check before saving.')
            cur.execute('''INSERT INTO aura_study_artifacts(id,student_id,course_id,source_id,kind,payload)
                VALUES(%s,%s,%s,%s,'assessment',%s)''',
                (str(run['id']), run['student_id'], run['course_id'], run['source_id'], Json(payload)))
            result = assessment_result(run, action)
            step.update(state='completed', observation=result['assessment'])
            cur.execute('''UPDATE aura_agent_runs SET steps=steps || %s::jsonb,state='completed',result=%s,
                updated_at=NOW() WHERE id=%s AND student_id=%s AND course_id=%s''',
                (Json([step]), Json(result), run['id'], run['student_id'], run['course_id']))
            return result

    def web_tool(self, run, action, step):
        # Reserve a paid attempt while locked, release the transaction for I/O,
        # then re-check ownership, cancellation and deadline before saving output.
        with self.locked(run) as (cur, current):
            request = RunInput.model_validate(current['request'])
            if action.tool not in allowed_tools(request):
                raise HTTPException(403, 'Web search is not enabled for this run.')
            attempted = [item for item in current['steps'] if item.get('tool') == 'web_search']
            if len(attempted) >= MAX_WEB_SEARCHES or any(item.get('action_key') == action_key(action) for item in attempted):
                raise HTTPException(409, 'This web search has already run or reached its limit.')
            if not any(item.get('tool') == 'document_search' and item.get('state') == 'completed' for item in current['steps']):
                raise HTTPException(409, 'Read the selected material before web search.')
            if current['tokens_used'] >= request.max_tokens or len(current['steps']) >= request.max_steps:
                raise HTTPException(409, 'The run has reached its budget.')
            index = len(current['steps'])
            remaining = max(.2, min(15, request.max_seconds - current['elapsed']))
            step.update(state='running', action=action.model_dump(), action_key=action_key(action))
            cur.execute('UPDATE aura_agent_runs SET steps=steps || %s::jsonb,updated_at=NOW() WHERE id=%s AND student_id=%s AND course_id=%s',
                        (Json([step]), run['id'], run['student_id'], run['course_id']))
        try:
            output = search_web(action.query, timeout=remaining)
        except WebSearchUnavailable as error:
            log.warning('agent_web_search=unavailable failure_code=%s http_status=%s', error.code, error.http_status)
            output = {'source': 'web', 'status': 'unavailable', 'passages': [],
                      'credits': None, 'untrusted_data': True}
        with self.locked(run) as (cur, current):
            reserved = current['steps'][index] if len(current['steps']) > index else {}
            if reserved.get('state') != 'running' or reserved.get('action_key') != action_key(action):
                raise RunStopped()
            step.update(state='completed', observation=output)
            cur.execute('''UPDATE aura_agent_runs SET steps=jsonb_set(steps,ARRAY[%s]::text[],%s::jsonb),updated_at=NOW()
                WHERE id=%s AND student_id=%s AND course_id=%s''',
                (str(index), Json(step), run['id'], run['student_id'], run['course_id']))
            return output


class RunStopped(Exception):
    pass


def preference_settings(data):
    if not data['enabled']:
        return {}
    result = {}
    for row in data['items']:
        record = row['record']
        if record.get('kind') != 'preference':
            continue
        for key in ('depth', 'examples'):
            if key not in result and record.get(key) is not None:
                result[key] = record[key]
    return result


def tutor_memory(student, course):
    return preference_settings(Store().memory(student, course))


def preferred_depth(question, explicit, memory):
    from backend.ai.answer_contract import choose_depth
    if explicit:
        return explicit
    current = choose_depth(question)
    return current if current != 'standard' else memory.get('depth')
