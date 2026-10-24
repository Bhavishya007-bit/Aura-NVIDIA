"""Group ownership and real PostgreSQL durable cancellation, with authored data."""
import os
import unittest
from contextlib import contextmanager
from uuid import uuid4
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from backend.material_groups import selected_ids, require_materials, GroupRetriever
from backend.study_tools import GenerateRequest
from backend.private_app import PrivateChatRequest
from backend.agents.contracts import RunInput
from backend import generation_jobs as jobs
from backend.auth_routes import get_current_student
from evaluation.check_agents import SQLBridge, SQLCursor

class SelectionChecks(unittest.TestCase):
    def test_requests_validate_all_ids_and_keep_old_primary(self):
        for contract, fields in [(GenerateRequest,dict(kind='notes')), (PrivateChatRequest,dict(question='Compare these')), (RunInput,dict(skill='study_plan',goal='Study'))]:
            self.assertEqual(contract(course_id=3,source_id=7,**fields).source_id,7)
            for ids in ([7,7], [7,8,9,10,11,12], [0,7], [True,7], [8,9]):
                with self.assertRaises((ValidationError,ValueError)): contract(course_id=3,source_id=7,material_ids=ids,**fields)
    def test_retrieval_is_bounded_balanced_and_cannot_override_scope(self):
        calls=[]
        class Base:
            def search(self, query, **kwargs):
                calls.append(kwargs);return [f"{kwargs['source_id']}-{i}" for i in range(4)]
        result=GroupRetriever(Base(),42,[7,9]).search('test',source_id=777,owner_student_id=999,top_k=4)
        self.assertEqual(result,['7-0','9-0','7-1','9-1'])
        self.assertEqual([c['owner_student_id'] for c in calls],[42,42])

@unittest.skipUnless(os.getenv('AURA_PGLITE_MODULE'),'Optional PostgreSQL engine not configured')
class SavedJobChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge=SQLBridge()
        cls.bridge.query("""CREATE TABLE students(student_id integer PRIMARY KEY); INSERT INTO students VALUES(42),(43);
            CREATE TABLE courses(course_id integer PRIMARY KEY,owner_student_id integer);
            CREATE TABLE sources(source_id integer PRIMARY KEY,course_id integer,owner_student_id integer,status text);
            INSERT INTO courses VALUES(3,42),(4,43);
            INSERT INTO sources VALUES(7,3,42,'success'),(9,3,42,'partial'),(8,4,43,'success'),(10,3,42,'processing');""")
        cls.bridge.query(jobs.SCHEMA)
        cls.bridge.query("ALTER TABLE sources ADD COLUMN source_name text; UPDATE sources SET source_name='File '||source_id; CREATE TABLE chunks(chunk_id integer,source_id integer,content text,page_number integer,slide_number integer,timestamp_seconds real,topic_id integer); INSERT INTO chunks VALUES(1,7,'Hash tables use keys',1,NULL,NULL,NULL),(2,9,'Collisions require resolution',2,NULL,NULL,NULL),(3,8,'Other account secret',1,NULL,NULL,NULL);")
        from pathlib import Path
        cls.bridge.query(Path('backend/agents/schema.sql').read_text())
    @classmethod
    def tearDownClass(cls): cls.bridge.close()
    def setUp(self):
        self.bridge.query('DELETE FROM aura_generation_jobs')
        @contextmanager
        def db():
            with self.bridge.lock:
                self.bridge.query('BEGIN')
                try: yield SQLCursor(self.bridge);self.bridge.query('COMMIT')
                except BaseException: self.bridge.query('ROLLBACK');raise
        self.db=db
        app=FastAPI();app.dependency_overrides[get_current_student]=lambda:{'student_id':42}
        class Payload(BaseModel):
            course_id:int
            source_id:int
            material_ids:list[int]
        jobs.install_generation(app,{'generate':(Payload.model_validate,lambda data, student:{'ok':True})})
        self.client=TestClient(app)
        self.patch=patch.object(jobs,'db',db);self.patch.start();self.addCleanup(self.patch.stop)
    def create(self,ids=(7,9)):
        return self.client.post('/study/generation-jobs',json={'course_id':3,'operation':'generate','payload':{'course_id':3,'source_id':7,'material_ids':list(ids)}})
    def test_group_validated_before_queuing_and_foreign_or_processing_refused(self):
        self.assertEqual(self.create().status_code,202)
        self.assertEqual(self.create((7,8)).status_code,404)
        self.assertEqual(self.create((7,10)).status_code,409)
        self.assertEqual(self.create((7,7)).status_code,422)
        self.assertEqual(len(self.bridge.query('SELECT * FROM aura_generation_jobs')),1)
    def test_cancel_survives_client_reload_and_is_course_scoped(self):
        job=self.create().json();url=f"/study/generation-jobs/{job['id']}"
        self.assertEqual(self.client.post(url+'/cancel?course_id=4').status_code,404)
        result=self.client.post(url+'/cancel?course_id=3')
        self.assertEqual(result.json()['state'],'cancelled')
        self.assertEqual(self.client.get(url+'?course_id=3').json()['state'],'cancelled')
        self.assertEqual(self.client.post(url+'/cancel?course_id=3').json()['state'],'cancelled')
    def test_cancelled_and_expired_work_cannot_pass_write_guard(self):
        job=self.create().json();token=jobs.current.set((job['id'],42))
        try:
            self.bridge.query("UPDATE aura_generation_jobs SET state='running'")
            jobs.guard()
            self.client.post(f"/study/generation-jobs/{job['id']}/cancel?course_id=3")
            with self.assertRaises(jobs.GenerationStopped): jobs.guard()
            self.bridge.query("UPDATE aura_generation_jobs SET state='running',deadline=NOW()-interval '1 second'")
            with self.assertRaises(jobs.GenerationStopped): jobs.guard()
        finally: jobs.current.reset(token)
    def test_every_group_member_requires_ownership(self):
        with self.db() as cur:
            require_materials(cur,42,3,[7,9])
            with self.assertRaises(HTTPException):require_materials(cur,42,3,[7,8])

    def test_dispatcher_finishes_valid_work_and_cancel_blocks_late_output(self):
        import threading,time
        started=threading.Event();release=threading.Event()
        class Payload(BaseModel):
            course_id:int
            source_id:int
            material_ids:list[int]
        def handler(data,student):
            started.set();release.wait(5)
            return {'answer':'Authored result','sources':[]}
        app=FastAPI();app.dependency_overrides[get_current_student]=lambda:{'student_id':42}
        jobs.install_generation(app,{'generate':(Payload.model_validate,handler)})
        with TestClient(app) as client:
            row=client.post('/study/generation-jobs',json={'course_id':3,'operation':'generate','payload':{'course_id':3,'source_id':7,'material_ids':[7,9]}}).json()
            self.assertTrue(started.wait(4))
            self.assertEqual(client.post(f"/study/generation-jobs/{row['id']}/cancel?course_id=3").json()['state'],'cancelled')
            release.set()
        saved=self.bridge.query('SELECT state,result FROM aura_generation_jobs')[0]
        self.assertEqual(saved['state'],'cancelled');self.assertIsNone(saved['result'])


    def test_group_tools_preserve_citation_identity_for_both_documents(self):
        from backend.study_tools import source_passages
        class Tuples(SQLCursor):
            def fetchone(self):
                row=super().fetchone();return tuple(row.values()) if row else None
            def fetchall(self):return [tuple(row.values()) for row in super().fetchall()]
        title,citations,total=source_passages(Tuples(self.bridge),3,[7,9])
        self.assertEqual([c['source_id'] for c in citations],[7,9])
        self.assertEqual([c['id'] for c in citations],[1,2])
        self.assertEqual([c['location'] for c in citations],['Page 1','Page 2'])
        self.assertEqual(total,2);self.assertIn('File 9',title)

    def test_agent_snapshot_and_search_cover_only_the_owned_group(self):
        from backend.agents.store import Store
        from backend.agents.contracts import Decision
        from evaluation.check_agents import action
        self.bridge.query('DELETE FROM aura_agent_runs')
        store=Store(connect=self.bridge.connect)
        request=RunInput(course_id=3,source_id=7,material_ids=[7,9],skill='study_plan',goal='Compare these materials')
        created=store.create(42,request);run=store.claim('test-worker')
        observed=store.tool(run,Decision.model_validate(action('document_search',query='keys collisions')).action,{'tool':'document_search','state':'completed'})
        self.assertEqual({p['source_id'] for p in observed['passages']},{7,9})
        self.assertNotIn('Other account secret',str(observed))
        self.assertEqual(store.runs(42,3,created['id'])['request']['material_ids'],[7,9])
        with self.assertRaises(HTTPException):store.create(42,request.model_copy(update={'material_ids':[7,8]}))
