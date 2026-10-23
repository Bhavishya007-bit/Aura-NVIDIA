"""Real PostgreSQL scheduling/ownership and Phase 4 contract regressions."""
import copy
from datetime import datetime,timedelta,timezone
import json
import os
import io
import sys
import tempfile
from contextlib import redirect_stdout,redirect_stderr
from pathlib import Path
import unittest
from unittest.mock import patch
from unittest.mock import Mock
from uuid import uuid4
from fastapi import FastAPI,HTTPException
from fastapi.testclient import TestClient
from backend.agents.store import Store
from backend.auth_routes import get_current_student
from backend.evaluation_status import calibration_summary
from backend.study_rhythm import RhythmStore,RhythmSettings,Snooze,next_review,install_study_rhythm
from evaluation import check_agents as fixtures
from evaluation.phase4 import offline_report,gate,main


class Phase4Contracts(unittest.TestCase):
    def test_review_intervals_and_incorrect_session_reset(self):
        now=datetime(2026,10,23,tzinfo=timezone.utc); streak=0
        for days in (1,3,7,14,30,30):
            streak,due=next_review(streak,True,now)
            self.assertEqual((due-now).days,days)
        streak,due=next_review(streak,False,now)
        self.assertEqual(streak,0);self.assertEqual(due-now,timedelta(days=1))
    def test_timezone_and_strict_settings(self):
        self.assertEqual(RhythmSettings(enabled=True,timezone='Asia/Calcutta').daily_hour,9)
        for bad in ({'enabled':True,'timezone':'not/a/zone'},{'enabled':True,'daily_hour':24},{'enabled':True,'student_id':43}):
            with self.assertRaises(ValueError):RhythmSettings(**bad)
    def test_judge_remains_untrusted_without_30_real_human_reviews(self):
        packet={'mode':'live_synthetic','model':'fixture-model','records':[{'id':f'cal-{i:02d}','predicted':('fully_covered','partially_covered','not_covered')[i%3],'human_label':('fully_covered','partially_covered','not_covered')[i%3],'reviewed_by':'human'} for i in range(1,31)]}
        self.assertTrue(calibration_summary(packet)['ready'])
        self.assertEqual(calibration_summary(packet)['agreement'],1)
        self.assertEqual(calibration_summary(packet)['kappa'],1)
        self.assertEqual(calibration_summary(packet)['false_absence_rate'],0)
        value=copy.deepcopy(packet)
        for row in [r for r in value['records'] if r['human_label']=='fully_covered'][:2]:row['predicted']='not_covered'
        summary=calibration_summary(value)
        self.assertGreater(summary['agreement'],.8);self.assertEqual(summary['false_absence_rate'],.1)
        self.assertFalse(summary['ready'])
        for mutate in (lambda p:p['records'].pop(),lambda p:p.update(mode='controlled_offline'),lambda p:p['records'][0].update(reviewed_by=None),lambda p:p['records'][0].update(predicted='unknown'),lambda p:p['records'][0].update(id='cal-99')):
            value=copy.deepcopy(packet);mutate(value);self.assertFalse(calibration_summary(value)['ready'])
        self.assertEqual(calibration_summary()['reviewed'],0)
        for malformed in ({'records':[{'id':[]}]*30},[],{'records':'invalid'}):
            self.assertFalse(calibration_summary(malformed)['ready'])
        value=copy.deepcopy(packet)
        for row in value['records'][:12]:row['human_label']='not_covered' if row['predicted']!='not_covered' else 'fully_covered'
        self.assertFalse(calibration_summary(value)['ready'])
    def test_regression_gate_detects_failed_or_removed_cases(self):
        with self.assertLogs('backend.agents.runtime',level='WARNING'):
            report=offline_report()
        baseline=json.loads(Path('evaluation/phase4_baseline.json').read_text())
        self.assertEqual(gate(report,baseline),[])
        report['summary'][0]['passed']-=1
        self.assertIn('agent_tasks',gate(report,baseline))
        report['summary']=[]
        self.assertEqual(len(gate(report,baseline)),3)
    def test_live_collector_keeps_actual_decisions_and_requires_independent_review(self):
        from evaluation.check_phase2 import verdict
        model=Mock();model.generate_json.return_value=verdict()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'packet.json'
            argv=['phase4','--collect-live','--model','fixture-model','--packet',str(path)]
            with patch.object(sys,'argv',argv),patch('backend.ai.llm.LLM',return_value=model),redirect_stdout(io.StringIO()):main()
            packet=json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(model.generate_json.call_count,30)
            self.assertEqual(len(packet['records']),30);self.assertTrue(packet['passages'])
            self.assertTrue(all(row['human_label'] is None and row['reviewed_by'] is None and row['decision'] for row in packet['records']))
            self.assertFalse(calibration_summary(packet)['ready'])
            payload=json.loads(model.generate_json.call_args.args[0])
            self.assertIn('output_schema',payload);self.assertEqual(payload['source_id_range'],{'minimum':1,'maximum':10})
            with patch.object(sys,'argv',argv),patch('backend.ai.llm.LLM') as second,redirect_stderr(io.StringIO()),self.assertRaises(SystemExit):main()
            second.assert_not_called()


@unittest.skipUnless(os.getenv('AURA_PGLITE_MODULE'),'Optional PostgreSQL engine not configured')
class RhythmPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.PostgresAgentChecks.setUpClass.__func__(cls)
        cls.bridge.query(Path('backend/study_tools.sql').read_text())
        cls.bridge.query(Path('backend/learning.sql').read_text())
        cls.bridge.query(Path('backend/material_preferences.sql').read_text())
        cls.rhythm=RhythmStore(cls.store);cls.rhythm.initialize();cls.rhythm.initialize()
    @classmethod
    def tearDownClass(cls):cls.bridge.close()
    def setUp(self):
        self.bridge.query('DELETE FROM aura_study_digests;DELETE FROM aura_review_schedule;DELETE FROM aura_review_events;DELETE FROM aura_study_rhythm_settings;DELETE FROM aura_learning_evidence;DELETE FROM aura_topic_mastery;DELETE FROM aura_study_results;DELETE FROM aura_study_artifacts;DELETE FROM aura_material_preferences;DELETE FROM aura_agent_tasks;DELETE FROM aura_agent_runs;')
        self.now=datetime.now(timezone.utc)
    def enable(self,student=42,course=3,hour=0,zone='UTC'):
        return self.rhythm.settings(student,course,RhythmSettings(enabled=True,timezone=zone,daily_hour=hour))
    def evidence(self,*,student=42,course=3,source=7,correct=True,when=None,questions=1,topic='Membranes'):
        artifact=str(uuid4());when=when or self.now-timedelta(days=2)
        with self.store.cursor(student,course,source) as cur:
            from psycopg2.extras import Json
            cur.execute('INSERT INTO aura_study_artifacts(id,student_id,course_id,source_id,kind,payload) VALUES(%s,%s,%s,%s,%s,%s)',(artifact,student,course,source,'assessment',Json({})))
            cur.execute('''INSERT INTO aura_topic_mastery(student_id,course_id,topic_key,topic)
                VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING''',(student,course,topic.casefold(),topic))
            for i in range(questions):
                cur.execute('''INSERT INTO aura_learning_evidence(student_id,course_id,source_id,artifact_id,question_id,topic_key,kind,correct,prior_mastery,posterior_mastery,observed_at)
                    VALUES(%s,%s,%s,%s,%s,%s,'assessment',%s,0.2,0.3,%s)''',(student,course,source,artifact,str(i),topic.casefold(),correct,when.isoformat()))
        return artifact
    def test_off_by_default_no_digest_or_schedule_without_opt_in(self):
        self.evidence();self.rhythm.tick(self.now)
        data=self.rhythm.read(42,3)
        self.assertFalse(data['settings']['enabled']);self.assertEqual(data['digests'],[]);self.assertEqual(data['reviews'],[])
        self.assertEqual(self.bridge.query('SELECT * FROM aura_review_schedule'),[])
    def test_one_digest_per_local_day_and_one_review_event_per_quiz_topic(self):
        self.evidence(questions=4);self.enable()
        self.rhythm.tick(self.now);self.rhythm.tick(self.now+timedelta(minutes=2));self.rhythm.refresh(42,3)
        data=self.rhythm.read(42,3)
        self.assertEqual(len(data['digests']),1);self.assertEqual(len(data['reviews']),1)
        self.assertEqual(len(self.bridge.query('SELECT * FROM aura_review_events')),1)
        row=self.bridge.query('SELECT * FROM aura_review_schedule')[0]
        self.assertEqual(row['streak'],1) # four questions do not skip to a 14-day interval
        self.assertEqual(data['reviews'][0]['source_id'],7)
        self.assertNotIn('Private unrelated',str(data))
    def test_later_practice_grows_interval_and_wrong_answer_resets(self):
        self.enable();self.evidence(when=self.now-timedelta(days=5));self.rhythm.refresh(42,3)
        self.evidence(when=self.now-timedelta(days=3));self.rhythm.refresh(42,3)
        self.assertEqual(self.bridge.query('SELECT streak FROM aura_review_schedule')[0]['streak'],2)
        self.evidence(correct=False,when=self.now-timedelta(days=1));self.rhythm.refresh(42,3)
        self.assertEqual(self.bridge.query('SELECT streak FROM aura_review_schedule')[0]['streak'],0)
        self.assertEqual(len(self.bridge.query('SELECT * FROM aura_review_events')),3)
    def test_pause_snooze_archive_and_other_account_are_enforced(self):
        self.evidence();self.enable();self.rhythm.refresh(42,3)
        body=Snooze(source_id=7,topic_key='membranes')
        with self.assertRaises(HTTPException):self.rhythm.snooze(43,4,body)
        self.assertEqual(self.rhythm.snooze(42,3,body)['reviews'],[])
        self.bridge.query("UPDATE aura_review_schedule SET due_at=NOW()-INTERVAL '1 day'")
        self.bridge.query('INSERT INTO aura_material_preferences(student_id,source_id,archived) VALUES(42,7,true)')
        self.assertEqual(self.rhythm.read(42,3)['reviews'],[])
        self.rhythm.settings(42,3,RhythmSettings(enabled=False))
        self.evidence(topic='Transport');self.rhythm.tick(self.now+timedelta(days=1))
        self.assertEqual(len(self.bridge.query('SELECT * FROM aura_review_events')),1)
        with self.assertRaises(HTTPException):self.rhythm.refresh(42,3)
        with self.assertRaises(HTTPException):self.rhythm.read(43,3)
    def test_timezone_hour_and_restart_catchup_do_not_backfill_multiple_days(self):
        self.enable(hour=9,zone='Asia/Calcutta')
        morning=datetime(2026,10,23,2,0,tzinfo=timezone.utc)
        self.rhythm.tick(morning);self.assertEqual(self.bridge.query('SELECT * FROM aura_study_digests'),[])
        self.rhythm.tick(morning+timedelta(hours=2));self.assertEqual(len(self.bridge.query('SELECT * FROM aura_study_digests')),1)
        restarted=RhythmStore(self.store);restarted.tick(morning+timedelta(days=3,hours=2))
        dates=[str(row['local_date'])[:10] for row in self.bridge.query('SELECT * FROM aura_study_digests ORDER BY local_date')]
        self.assertEqual(dates,['2026-10-23','2026-10-26'])
    def test_repeated_daylight_saving_hour_still_creates_one_brief(self):
        self.enable(hour=1,zone='America/New_York')
        repeated_hour=datetime(2026,11,1,5,30,tzinfo=timezone.utc)
        self.rhythm.tick(repeated_hour);self.rhythm.tick(repeated_hour+timedelta(hours=1))
        rows=self.bridge.query('SELECT * FROM aura_study_digests')
        self.assertEqual(len(rows),1);self.assertEqual(str(rows[0]['local_date'])[:10],'2026-11-01')
    def test_one_wrong_answer_in_a_session_resets_only_its_topic(self):
        self.enable();self.evidence(when=self.now-timedelta(days=5));self.rhythm.refresh(42,3)
        artifact=self.evidence(when=self.now-timedelta(days=2),questions=4)
        with self.store.cursor(42,3) as cur:
            cur.execute('UPDATE aura_learning_evidence SET correct=FALSE WHERE artifact_id=%s AND question_id=%s',(artifact,'2'))
        self.evidence(topic='Transport');self.rhythm.refresh(42,3)
        schedules={row['topic_key']:row['streak'] for row in self.bridge.query('SELECT * FROM aura_review_schedule')}
        self.assertEqual(schedules,{'membranes':0,'transport':1})
    def test_api_requires_auth_and_never_exposes_other_user_runs(self):
        app=FastAPI()
        with patch('backend.study_rhythm.RhythmStore',return_value=self.rhythm):install_study_rhythm(app)
        app.dependency_overrides[get_current_student]=lambda:{'student_id':42}
        with TestClient(app) as client:
            self.assertEqual(client.get('/study/rhythm?course_id=3').status_code,200)
            self.assertEqual(client.get('/study/rhythm?course_id=4').status_code,404)
            self.assertEqual(client.patch('/study/rhythm/settings?course_id=3',json={'enabled':True,'timezone':'UTC','daily_hour':0}).status_code,200)
            self.assertEqual(client.post('/study/rhythm/refresh?course_id=3').status_code,200)
            response=client.get('/study/evaluation?course_id=3')
            self.assertEqual(response.status_code,200);self.assertEqual(response.json()['your_runs'],{})
            self.assertFalse(response.json()['calibration']['ready'])
            self.assertNotIn('records',response.json())
            del app.dependency_overrides[get_current_student]
            self.assertEqual(client.get('/study/rhythm?course_id=3').status_code,401)
