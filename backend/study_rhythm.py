"""Durable in-app digests and spaced review from actual graded practice. No LLM calls."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from psycopg2.extras import Json
from pydantic import Field, model_validator
from starlette.concurrency import run_in_threadpool
from backend.agents.contracts import Strict
from backend.agents.store import Store
from backend.auth_routes import get_current_student

log = logging.getLogger(__name__)
INTERVALS = (1, 3, 7, 14, 30)


class RhythmSettings(Strict):
    enabled: bool
    timezone: str = Field(default='UTC', min_length=1, max_length=80)
    daily_hour: int = Field(default=9, ge=0, le=23)

    @model_validator(mode='after')
    def valid_zone(self):
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError('Choose a valid IANA timezone. Windows servers need the tzdata package.')
        return self


class Snooze(Strict):
    source_id: int = Field(gt=0)
    topic_key: str = Field(min_length=1, max_length=240)


def instant(value):
    return value if isinstance(value, datetime) else datetime.fromisoformat(value.replace('Z','+00:00'))


def next_review(streak, correct, observed_at):
    # A successful graded SESSION grows the interval, not each question in a quiz.
    streak = min(5, streak + 1) if correct else 0
    return streak, observed_at + timedelta(days=INTERVALS[max(0, streak-1)])


class RhythmStore:
    def __init__(self, store=None): self.store = store or Store()

    def initialize(self):
        with self.store.cursor() as cur:
            cur.execute('SELECT pg_advisory_xact_lock(817264,5)')
            cur.execute(Path(__file__).with_name('study_rhythm.sql').read_text(encoding='utf-8'))

    def settings(self, student, course, body):
        with self.store.cursor(student, course) as cur:
            cur.execute('''INSERT INTO aura_study_rhythm_settings(student_id,course_id,enabled,timezone,daily_hour)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT(student_id,course_id) DO UPDATE
                SET enabled=EXCLUDED.enabled,timezone=EXCLUDED.timezone,daily_hour=EXCLUDED.daily_hour,checked_at=NULL''',
                (student, course, body.enabled, body.timezone, body.daily_hour))
        return self.read(student, course)

    def due(self, cur, student, course, now):
        cur.execute('''SELECT r.source_id,r.topic_key,r.topic,r.due_at,s.source_name
            FROM aura_review_schedule r JOIN sources s ON s.source_id=r.source_id
            JOIN courses c ON c.course_id=r.course_id
            LEFT JOIN aura_material_preferences p ON p.source_id=s.source_id AND p.student_id=r.student_id
            WHERE r.student_id=%s AND r.course_id=%s AND s.owner_student_id=%s AND c.owner_student_id=%s
            AND s.course_id=r.course_id AND NOT COALESCE(p.archived,FALSE) AND r.due_at<=%s::timestamptz
            ORDER BY r.due_at,r.topic LIMIT 10''', (student,course,student,student,now.isoformat()))
        return [{**dict(row), 'due_at': instant(row['due_at']).isoformat()} for row in cur.fetchall()]

    def read(self, student, course):
        with self.store.cursor(student, course) as cur:
            cur.execute('SELECT enabled,timezone,daily_hour FROM aura_study_rhythm_settings WHERE student_id=%s AND course_id=%s', (student,course))
            settings = dict(cur.fetchone() or {'enabled':False,'timezone':'UTC','daily_hour':9})
            cur.execute('SELECT id,local_date,payload,created_at FROM aura_study_digests WHERE student_id=%s AND course_id=%s ORDER BY local_date DESC LIMIT 7', (student,course))
            digests = [{**dict(row), 'id':str(row['id']), 'local_date':str(row['local_date'])[:10], 'created_at':instant(row['created_at']).isoformat()} for row in cur.fetchall()]
            return {'settings':settings, 'digests':digests,
                    'reviews':self.due(cur,student,course,datetime.now(timezone.utc)) if settings['enabled'] else [],
                    'notice':'In-app only. Based on graded practice and saved tasks; no email, push or background AI calls.'}

    def snooze(self, student, course, body):
        with self.store.cursor(student, course, body.source_id) as cur:
            cur.execute('''UPDATE aura_review_schedule SET due_at=NOW()+INTERVAL '1 day'
                WHERE student_id=%s AND course_id=%s AND source_id=%s AND topic_key=%s RETURNING topic_key''',
                (student,course,body.source_id,body.topic_key))
            if cur.fetchone() is None: raise HTTPException(404,'Review not found.')
        return self.read(student,course)

    def refresh(self, student, course):
        # Explicit refresh can create today's digest before the configured hour.
        with self.store.cursor(student,course) as cur:
            cur.execute('SELECT * FROM aura_study_rhythm_settings WHERE student_id=%s AND course_id=%s FOR UPDATE', (student,course))
            settings = cur.fetchone()
            if settings is None or not settings['enabled']: raise HTTPException(409,'Enable your study rhythm first.')
            self.process(cur,dict(settings),datetime.now(timezone.utc),force=True)
        return self.read(student,course)

    def tick(self, now=None):
        now = now or datetime.now(timezone.utc)
        with self.store.cursor() as cur:
            # Multiple server workers do not generate duplicate daily digests.
            cur.execute('SELECT pg_try_advisory_xact_lock(817264,6) AS acquired')
            if not cur.fetchone()['acquired']: return
            cur.execute('''SELECT x.* FROM aura_study_rhythm_settings x
                JOIN courses c ON c.course_id=x.course_id AND c.owner_student_id=x.student_id
                WHERE x.enabled AND (x.checked_at IS NULL OR x.checked_at < %s::timestamptz - INTERVAL '45 seconds')
                ORDER BY x.checked_at NULLS FIRST LIMIT 10 FOR UPDATE OF x SKIP LOCKED''', (now.isoformat(),))
            for settings in cur.fetchall():
                self.process(cur,dict(settings),now)
                cur.execute('UPDATE aura_study_rhythm_settings SET checked_at=%s WHERE student_id=%s AND course_id=%s', (now.isoformat(),settings['student_id'],settings['course_id']))

    def process(self, cur, settings, now, force=False):
        student,course = settings['student_id'],settings['course_id']
        # Process bounded batches; the unique event key makes every graded session idempotent.
        cur.execute('''SELECT e.artifact_id,e.source_id,e.topic_key,MIN(m.topic) AS topic,
                bool_and(e.correct) AS correct,MAX(e.observed_at) AS observed_at
            FROM aura_learning_evidence e JOIN aura_topic_mastery m
              ON m.student_id=e.student_id AND m.course_id=e.course_id AND m.topic_key=e.topic_key
            JOIN sources s ON s.source_id=e.source_id AND s.owner_student_id=e.student_id AND s.course_id=e.course_id
            WHERE e.student_id=%s AND e.course_id=%s AND NOT EXISTS (
                SELECT 1 FROM aura_review_events p WHERE p.student_id=e.student_id AND p.course_id=e.course_id
                AND p.artifact_id=e.artifact_id AND p.topic_key=e.topic_key)
            GROUP BY e.artifact_id,e.source_id,e.topic_key ORDER BY MAX(e.observed_at),e.artifact_id LIMIT 50''', (student,course))
        for event in cur.fetchall():
            cur.execute('''INSERT INTO aura_review_events(student_id,course_id,artifact_id,source_id,topic_key)
                VALUES(%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING artifact_id''',
                (student,course,event['artifact_id'],event['source_id'],event['topic_key']))
            if cur.fetchone() is None: continue
            cur.execute('''SELECT streak,last_observed_at FROM aura_review_schedule
                WHERE student_id=%s AND course_id=%s AND source_id=%s AND topic_key=%s FOR UPDATE''',
                (student,course,event['source_id'],event['topic_key']))
            previous = cur.fetchone()
            if previous and instant(event['observed_at']) < instant(previous['last_observed_at']): continue
            streak,due = next_review(previous['streak'] if previous else 0,event['correct'],instant(event['observed_at']))
            cur.execute('''INSERT INTO aura_review_schedule(student_id,course_id,source_id,topic_key,topic,streak,last_observed_at,due_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(student_id,course_id,source_id,topic_key) DO UPDATE
                SET topic=EXCLUDED.topic,streak=EXCLUDED.streak,last_observed_at=EXCLUDED.last_observed_at,due_at=EXCLUDED.due_at''',
                (student,course,event['source_id'],event['topic_key'],event['topic'],streak,instant(event['observed_at']).isoformat(),due.isoformat()))
        local = now.astimezone(ZoneInfo(settings['timezone']))
        if not force and local.hour < settings['daily_hour']: return
        reviews = self.due(cur,student,course,now)
        cur.execute('SELECT id,title FROM aura_agent_tasks WHERE student_id=%s AND course_id=%s AND NOT done ORDER BY created_at LIMIT 5', (student,course))
        tasks = [{'id':str(row['id']), 'title':row['title']} for row in cur.fetchall()]
        payload = {'title':'Your next study session', 'reviews':reviews, 'tasks':tasks,
            'takeaway':('Start with a due topic, then return to your saved checklist.' if reviews else
                        'Continue one saved task, then check your understanding.' if tasks else
                        'Take a short quiz to build a review schedule from your graded answers.'),
            'method':'Saved tasks and graded practice. Review intervals: 1, 3, 7, 14 and 30 days; any incorrect answer resets the topic interval.'}
        cur.execute('''INSERT INTO aura_study_digests(id,student_id,course_id,local_date,payload,created_at)
            VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(student_id,course_id,local_date) DO NOTHING''',
            (str(uuid4()),student,course,local.date().isoformat(),Json(payload),now.isoformat()))
        cur.execute('''DELETE FROM aura_study_digests WHERE student_id=%s AND course_id=%s
            AND local_date < %s::date - 30''',(student,course,local.date().isoformat()))


def install_study_rhythm(app):
    rhythm = RhythmStore()
    router = APIRouter(prefix='/study', tags=['Study rhythm'])

    @router.get('/rhythm')
    def read(course_id:int=Query(gt=0), student=Depends(get_current_student)):
        return rhythm.read(student['student_id'],course_id)

    @router.patch('/rhythm/settings')
    def settings(body:RhythmSettings,course_id:int=Query(gt=0),student=Depends(get_current_student)):
        return rhythm.settings(student['student_id'],course_id,body)

    @router.post('/rhythm/refresh')
    def refresh(course_id:int=Query(gt=0),student=Depends(get_current_student)):
        return rhythm.refresh(student['student_id'],course_id)

    @router.post('/rhythm/snooze')
    def snooze(body:Snooze,course_id:int=Query(gt=0),student=Depends(get_current_student)):
        return rhythm.snooze(student['student_id'],course_id,body)

    @router.get('/evaluation')
    def evaluation(course_id:int=Query(gt=0),student=Depends(get_current_student)):
        from backend.evaluation_status import evaluation_status
        with rhythm.store.cursor(student['student_id'],course_id) as cur:
            cur.execute('SELECT state,COUNT(*) AS count FROM aura_agent_runs WHERE student_id=%s AND course_id=%s GROUP BY state', (student['student_id'],course_id))
            runs = {row['state']:row['count'] for row in cur.fetchall()}
        return {**evaluation_status(), 'your_runs':runs}

    app.include_router(router)
    previous = app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        await run_in_threadpool(rhythm.initialize)
        async with previous(application):
            async def worker():
                while True:
                    try: await run_in_threadpool(rhythm.tick)
                    except Exception as error: log.warning('study_rhythm=unavailable error_type=%s',type(error).__name__)
                    await asyncio.sleep(30)
            task=asyncio.create_task(worker())
            try: yield
            finally:
                task.cancel(); await asyncio.gather(task,return_exceptions=True)
    app.router.lifespan_context=lifespan
