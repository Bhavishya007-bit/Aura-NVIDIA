import os
os.environ['AUTH_JWT_SECRET']='test-local-privacy-secret-not-production'
os.environ.pop('AI_PROVIDER',None)
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import backend
backend.__path__.insert(0,str(ROOT/'backend'))
import ast
import asyncio
import io
import tempfile
import types
import unittest
from unittest.mock import patch,Mock,AsyncMock
from uuid import uuid4
from fastapi import File,HTTPException
from starlette.datastructures import UploadFile
from fastapi.testclient import TestClient
from psycopg2.extras import Json
from backend import private_app as private
from backend import auth_routes, study_tools

class Cursor:
    def __init__(self,db):self.db=db;self.rows=[]
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def close(self):pass
    def execute(self,sql,params=()):
        self.db.calls.append((sql,params));self.rows=[]
        if sql.startswith('SELECT course_id FROM courses WHERE course_id=%s AND owner_student_id'):
            if self.db.courses.get(params[0])==params[1]:self.rows=[(params[0],)]
        elif 'INSERT INTO courses(course_name,owner_student_id)' in sql:
            course=next((i for i,owner in self.db.courses.items() if owner==params[0]),None)
            if course is None:course=max(self.db.courses)+1;self.db.courses[course]=params[0]
            self.rows=[(course,'My study materials')]
        elif 'SELECT s.source_id,s.course_id' in sql:
            source=self.db.sources.get(params[0])
            if source and source['owner']==params[1]==params[2] and self.db.courses[source['course']]==params[1]:self.rows=[(params[0],source['course'])]
        elif 'FROM sources s LEFT JOIN aura_material_preferences' in sql:
            self.rows=[(i,s['title'],'pdf','success',False) for i,s in self.db.sources.items() if s['course']==params[1] and s['owner']==params[2]]
        elif sql.startswith('SELECT source_id,source_name'):
            self.rows=[(i,s['title'],'pdf','success') for i,s in self.db.sources.items() if s['course']==params[0] and s['owner']==params[1]]
        elif 'SELECT a.source_id,a.course_id' in sql:
            if str(params[0])=='11111111-1111-1111-1111-111111111111' and params[1]==7:self.rows=[(31,17)]
        elif sql.startswith('SELECT count(*) FROM chunks'):self.rows=[(4,)]
        elif 'SELECT course_id FROM courses WHERE course_id = %s' in sql:
            if params[0] in self.db.courses:self.rows=[(params[0],)]
        elif 'INSERT INTO sources (' in sql:
            sid=max(self.db.sources)+1;self.db.sources[sid]={'course':params[0],'owner':params[-1],'title':params[1],'path':params[3]};self.rows=[(sid,)]
    def fetchone(self):return self.rows[0] if self.rows else None
    def fetchall(self):return self.rows
class Database:
    def __init__(self):
        self.calls=[];self.courses={1:None,17:7,18:8}
        self.sources={31:{'course':17,'owner':7,'title':'Owner A.pdf'},32:{'course':18,'owner':8,'title':'Owner B.pdf'},33:{'course':1,'owner':None,'title':'Track D.pdf'},34:{'course':17,'owner':None,'title':'Unassigned.pdf'}}
    def cursor(self):return Cursor(self)
    def close(self):pass
    def commit(self):pass
    def rollback(self):pass

class PrivacyTests(unittest.TestCase):
    def setUp(self):
        self.owner=7;self.db=Database();self.legacy=types.SimpleNamespace(upload_course_source=AsyncMock(return_value={'source_id':40}),generate_source_embeddings=Mock(return_value={'status':'completed','embedded_count':4}),chat=Mock(return_value={'answer':'Supported','sources':[]}),LLM=Mock(return_value=Mock(generate=Mock(return_value='General answer'))))
        self.legacy.RAG=Mock(return_value=Mock(answer=Mock(return_value={'answer':'Supported','sources':[]})))
        self.legacy.get_retriever=Mock(return_value=Mock(search=Mock(return_value=[])))
        self.app=private.create_private_app(self.legacy)
        self.app.dependency_overrides[auth_routes.get_current_student]=lambda:{'student_id':self.owner}
        self.client=TestClient(self.app)
        self.connection=patch.object(private,'get_auth_connection',return_value=self.db);self.connection.start();self.addCleanup(self.connection.stop)
        self.auth=patch.object(private,'get_current_student',side_effect=lambda credentials:{'student_id':self.owner});self.auth.start();self.addCleanup(self.auth.stop)
    def test_each_account_receives_only_its_course(self):
        first=self.client.get('/courses',headers={'Authorization':'Bearer test'}).json()
        self.owner=8;second=self.client.get('/courses',headers={'Authorization':'Bearer test'}).json()
        self.assertEqual(first['courses'][0]['course_id'],17);self.assertEqual(second['courses'][0]['course_id'],18)
    def test_authenticated_material_response_is_not_cacheable(self):
        response=self.client.get('/study/materials?course_id=17')
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertIn('Authorization',response.headers['Vary'])

    def test_new_account_starts_empty_and_legacy_material_is_hidden(self):
        self.owner=9
        course=self.client.get('/courses',headers={'Authorization':'Bearer test'}).json()['courses'][0]['course_id']
        response=self.client.get(f'/study/materials?course_id={course}')
        self.assertEqual(response.status_code,200,response.text);self.assertEqual(response.json()['sources'],[])
        self.assertIn(33,self.db.sources)
    def test_material_route_never_uses_old_course_only_handler(self):
        data=self.client.get('/study/materials?course_id=17').json()['sources']
        self.assertEqual([s['source_id'] for s in data],[31])
    def test_other_accounts_course_and_source_listing_denied(self):
        for path in ['/sources/18','/study/materials?course_id=18','/study/artifacts?course_id=18','/study/progress?course_id=18']:
            self.assertEqual(self.client.get(path).status_code,404,path)
    def test_study_generation_cannot_use_other_source_or_fake_student_id(self):
        with patch.object(study_tools,'model_json') as model:
            response=self.client.post('/study/tools',json={'course_id':17,'source_id':32,'student_id':8,'kind':'notes'})
        self.assertEqual(response.status_code,404);model.assert_not_called()
    def test_cannot_archive_other_persons_file(self):
        response=self.client.patch('/study/materials/32/visibility',json={'course_id':17,'archived':True})
        self.assertEqual(response.status_code,404)
    def test_cannot_index_other_persons_file(self):
        self.assertEqual(self.client.post('/sources/32/generate-embeddings').status_code,404)
        self.legacy.generate_source_embeddings.assert_not_called()
    def test_own_indexing_passes_and_ready_source_resume_count_is_positive(self):
        self.legacy.generate_source_embeddings.return_value={'status':'completed','embedded_count':0}
        response=self.client.post('/sources/31/generate-embeddings')
        self.assertEqual(response.status_code,200);self.assertEqual(response.json()['embedded_count'],4)
    def test_tutor_cannot_read_other_persons_or_legacy_source(self):
        for source,course in [(32,17),(33,1),(34,17)]:
            response=self.client.post('/chat',headers={'Authorization':'Bearer test'},json={'question':'Read it','course_id':course,'source_id':source})
            self.assertEqual(response.status_code,404)
        self.legacy.chat.assert_not_called()
    def test_own_tutor_scope_is_preserved(self):
        response=self.client.post('/chat',headers={'Authorization':'Bearer test'},json={'question':'Read it','course_id':17,'source_id':31})
        self.assertEqual(response.status_code,200)
        request=self.legacy.RAG.return_value.answer.call_args.kwargs;self.assertEqual(request['course_id'],17);self.assertEqual(request['source_id'],31)
        retriever=self.legacy.RAG.call_args.kwargs['retriever'];retriever.search('test',course_id=17,source_id=31)
        retriever.overview(course_id=17,source_id=31,limit=12)
        self.legacy.get_retriever.return_value.overview.assert_called_once_with(owner_student_id=7,course_id=17,source_id=31,limit=12)
        self.assertEqual(self.legacy.get_retriever.return_value.search.call_args.kwargs['owner_student_id'],7)
    def test_guest_cannot_retrieve_material_and_general_chat_does_not_search(self):
        self.assertEqual(self.client.post('/chat',json={'question':'Read it','source_id':31,'course_id':17}).status_code,401)
        response=self.client.post('/chat',json={'question':'What is a cell?','course_id':1})
        self.assertEqual(response.status_code,200);self.assertFalse(response.json()['citation_validation']['valid']);self.legacy.chat.assert_not_called()
    def test_upload_owner_comes_from_authenticated_session(self):
        response=self.client.post('/courses/17/sources',files={'file':('cell.pdf',b'file')})
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.legacy.upload_course_source.call_args.kwargs['owner_student_id'],7)
        self.assertEqual(self.client.post('/courses/18/sources',files={'file':('cell.pdf',b'file')}).status_code,404)
        self.assertEqual(self.legacy.upload_course_source.call_count,1)
    def test_raw_development_endpoints_not_exposed(self):
        for path in ['/students','/chunks/31','/search','/students/8/mastery']:
            self.assertEqual(self.client.get(path).status_code,404,path)
    def test_submission_of_other_or_unassigned_artifact_denied(self):
        response=self.client.post('/study/assessments/22222222-2222-2222-2222-222222222222/submit',json={'answers':[{'question_id':'item-1','answer':'A'}]})
        self.assertEqual(response.status_code,404)
    def test_retrieval_sql_filters_owner_before_returning_passages(self):
        import importlib.util
        module=types.ModuleType('backend.ai.embeddings');module.EmbeddingModel=object
        spec=importlib.util.spec_from_file_location('privacy_pg_test',str(ROOT/'backend/ai/pg_retrieval.py'))
        loaded=importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules,{'backend.ai.embeddings':module}):spec.loader.exec_module(loaded)
        model=Mock(embed_query=Mock(return_value=[0.0]*1024));retriever=loaded.PostgresRetriever(model)
        retriever._get_connection=Mock(return_value=self.db)
        self.assertEqual(retriever.search('cell',course_id=17,owner_student_id=7),[])
        sql,params=self.db.calls[-1]
        self.assertIn('AND sources.owner_student_id = %s',sql)
        self.assertLess(sql.index('AND sources.owner_student_id'),sql.index('LIMIT %s'))
        self.assertEqual(params[-2],7)

    def test_real_upload_implementation_stores_owner_and_unique_disk_paths(self):
        tree=ast.parse((ROOT/'backend/main.py').read_text());fn=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='upload_course_source');fn.decorator_list=[]
        with tempfile.TemporaryDirectory() as temp:
            result={'source':{'file_type':'pdf'},'status':'success','content_units':[{'unit_id':'page1','text':'A cell has a membrane.','source_location':{'page_number':1}}],'warnings':[]}
            namespace={'UploadFile':UploadFile,'File':File,'Path':Path,'HTTPException':HTTPException,'uuid4':uuid4,'Json':Json,'get_connection':lambda:self.db,'ingest_file':lambda **kw:result,'__file__':temp+'/backend/main.py'}
            exec(compile(ast.Module(body=[fn],type_ignores=[]),'upload-implementation','exec'),namespace)
            module=types.ModuleType('backend.ingestion.utils');module.get_file_type=lambda filename:'pdf'
            with patch.dict(sys.modules,{'backend.ingestion.utils':module}):
                asyncio.run(namespace['upload_course_source'](17,UploadFile(io.BytesIO(b'FIRST'),filename='cell.pdf'),owner_student_id=7))
                asyncio.run(namespace['upload_course_source'](18,UploadFile(io.BytesIO(b'SECOND'),filename='cell.pdf'),owner_student_id=8))
            stored=[s for s in self.db.sources.values() if 'path' in s]
            self.assertEqual(len(stored),2);self.assertEqual(sorted(s['owner'] for s in stored),[7,8]);self.assertNotEqual(stored[0]['path'],stored[1]['path'])
            self.assertEqual(Path(stored[0]['path']).read_bytes(),b'FIRST');self.assertEqual(Path(stored[1]['path']).read_bytes(),b'SECOND')

if __name__=='__main__':unittest.main(verbosity=2)
