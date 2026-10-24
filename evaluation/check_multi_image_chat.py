"""Joint-image transport/validation and actual PostgreSQL attachment ownership checks."""
import base64
import io
import json
import os
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from backend.figure_tools import vision_json
from backend.multi_image_tutor import images_tutor_answer
from backend.private_app import PrivateChatRequest, create_private_app
from evaluation.check_agents import SQLBridge, SQLCursor


def draft(text='The table lists a department identifier.'):
    return {'answerable': True, 'observations': [text],
        'explanation': 'Readable screenshot content.',
        'limitations': []}


class MultiImageChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.sources = []
        for n, color in zip((7, 8), ('red', 'blue')):
            path = Path(self.folder.name) / f'authored-{n}.png'
            Image.new('RGB', (40, 30), color).save(path)
            self.sources.append({'id': n, 'student_id': 42, 'title': path.name, 'path': path})
        self.solver_patch = patch('backend.multi_image_tutor.solve_image_problem', side_effect=lambda question, evidence, **kw:
            {**evidence, 'answerable': True, 'explanation': 'Combine the identifier with its booking.', 'limitations': []})
        self.solver = self.solver_patch.start(); self.addCleanup(self.solver_patch.stop)
        self.review_patch = patch('backend.multi_image_tutor.review_image_problem', return_value=True)
        self.review = self.review_patch.start(); self.addCleanup(self.review_patch.stop)

    def test_all_originals_and_question_reach_both_generation_and_verification(self):
        question = 'Which department meets the condition in these two tables?'
        with patch('backend.multi_image_tutor.owned_original', side_effect=self.sources) as owned, \
             patch('backend.multi_image_tutor.vision_json', side_effect=[draft(), {'supported': True},
                draft('The second table lists a booking.'), {'supported': True}]) as model:
            result = images_tutor_answer([7,8], question, 42,
                history=[{'role': 'assistant', 'content': 'Previous context, not evidence.'}])
        self.assertEqual(owned.call_args_list[0].args, (7,42))
        self.assertEqual(owned.call_args_list[1].args, (8,42))
        self.assertEqual(model.call_count, 4)
        for call, color in zip(model.call_args_list, [(255,0,0)]*2+[(0,0,255)]*2):
            self.assertIsInstance(call.args[0], bytes)
            self.assertEqual(Image.open(io.BytesIO(call.args[0])).getpixel((0,0)), color)
            self.assertIn(question, call.args[1])
        self.assertEqual([item['image'] for item in self.solver.call_args.args[1]['observations']], [1, 2])
        self.assertEqual([s['source_id'] for s in result['sources']], [7,8])
        self.assertNotIn('booking', result['sources'][0]['content'])
        self.assertIn('booking', result['sources'][1]['content'])
        self.assertTrue(result['answer'].endswith('[1][2]'))
        self.assertFalse(result['citation_validation']['valid'])
        self.assertTrue(result['citation_validation']['visual_check_passed'])

    def test_missing_or_foreign_original_does_not_answer_using_only_one_image(self):
        with patch('backend.multi_image_tutor.owned_original', side_effect=[self.sources[0], HTTPException(404,'Not found')]), \
             patch('backend.multi_image_tutor.vision_json') as model:
            with self.assertRaises(HTTPException) as error:
                images_tutor_answer([7,8], 'Question',42)
        self.assertEqual(error.exception.status_code,404)
        model.assert_not_called()

    def test_empty_evidence_and_model_assigned_image_fields_fail_closed(self):
        variants=[]
        bad=draft();bad['observations']=[];variants.append(bad)
        bad=draft();bad['image']=3;variants.append(bad)
        bad=draft();bad['observations']=[{'image':1,'text':'Untrusted mapping'}];variants.append(bad)
        bad=draft();bad['answerable']='yes';variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad), patch('backend.multi_image_tutor.owned_original', side_effect=self.sources), \
                 patch('backend.multi_image_tutor.vision_json', return_value=bad) as model:
                with self.assertRaises(HTTPException) as error:
                    images_tutor_answer([7,8], 'Question',42)
                self.assertEqual(error.exception.status_code,503)
                self.assertEqual(model.call_count, 2)
        self.solver.assert_not_called()

    def test_reader_narration_does_not_become_a_citation_or_final_answer(self):
        first = draft(); first['explanation'] = 'Raw reading narration [99]'
        with patch('backend.multi_image_tutor.owned_original', side_effect=self.sources), \
             patch('backend.multi_image_tutor.vision_json', side_effect=[first, {'supported':True}, draft(), {'supported':True}]):
            result = images_tutor_answer([7,8], 'solution', 42)
        self.assertNotIn('Raw reading narration', result['answer'])
        self.assertNotIn('[99]', result['answer'])

    def test_rejected_visual_check_never_publishes_the_unapproved_answer(self):
        with patch('backend.multi_image_tutor.owned_original', side_effect=self.sources), \
             patch('backend.multi_image_tutor.vision_json', side_effect=[draft(), {'supported':False}, draft(), {'supported':True}]):
            result=images_tutor_answer([7,8],'Question',42)
        self.assertNotIn('Combine the identifier',result['answer'])
        self.assertFalse(result['citation_validation']['visual_check_passed'])
        self.assertEqual([s['source_id'] for s in result['sources']],[7,8])
        self.assertIn('Image 1', result['answer'])
        self.solver.assert_not_called()

    def test_ollama_transport_keeps_images_separate_and_in_order(self):
        response=Mock();response.json.return_value={'message':{'content':'{"supported":true}'},'done_reason':'stop'}
        with patch.dict(os.environ, {'OLLAMA_VISION_MODEL':'fixture-vision'}), \
             patch('backend.figure_tools.requests.post',return_value=response) as post:
            self.assertEqual(vision_json([b'first',b'second'],'joint question'),{'supported':True})
        payload=post.call_args.kwargs['json']
        self.assertEqual([base64.b64decode(value) for value in payload['messages'][0]['images']],[b'first',b'second'])
        self.assertEqual(payload['messages'][0]['content'],'joint question')

    def test_request_limits_and_backward_compatible_single_source(self):
        self.assertEqual(PrivateChatRequest(question='Question',source_id=7).source_ids,[])
        for ids in ([True,8],['7',8],[7,7],[0,8],list(range(1,7))):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                PrivateChatRequest(question='Question',source_ids=ids)
        with self.assertRaises(ValueError):
            PrivateChatRequest(question='Question',source_id=9,source_ids=[7,8])


@unittest.skipUnless(os.getenv('AURA_PGLITE_MODULE'),'Optional PostgreSQL engine not configured')
class MultiImageOwnershipChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge=SQLBridge()
        cls.bridge.query('''CREATE TABLE courses(course_id int,owner_student_id int);
            CREATE TABLE sources(source_id int,course_id int,owner_student_id int,source_type text);
            INSERT INTO courses VALUES(3,42),(4,43),(5,42);
            INSERT INTO sources VALUES(7,3,42,'image'),(8,3,42,'image'),(9,4,43,'image'),
                (10,5,42,'image'),(11,3,42,'pdf'),(12,3,43,'image');''')
    @classmethod
    def tearDownClass(cls): cls.bridge.close()
    @contextmanager
    def database(self):
        bridge=self.bridge
        class Cursor(SQLCursor):
            def fetchone(self):
                row=super().fetchone()
                return list(row.values()) if isinstance(row,dict) else row
        class Connection:
            def cursor(self): return Cursor(bridge)
        with bridge.lock:
            bridge.query('BEGIN')
            try:
                yield Connection();bridge.query('COMMIT')
            except Exception:
                bridge.query('ROLLBACK');raise
    def request(self,ids,*,primary=7,auth=True):
        client=TestClient(create_private_app(Mock()))
        with patch('backend.private_app.database',self.database), \
             patch('backend.private_app.get_current_student',return_value={'student_id':42}), \
             patch('backend.private_app.images_tutor_answer',return_value={'answer':'Joint result'}) as model:
            response=client.post('/chat',json={'question':'Pasted question','course_id':3,'source_id':primary,'source_ids':ids},
                headers={'Authorization':'Bearer synthetic-token'} if auth else {})
        client.close()
        return response,model
    def test_all_attached_sources_are_owned_and_in_the_selected_workspace(self):
        response,model=self.request([8,7])
        self.assertEqual(response.status_code,200,response.text)
        self.assertEqual(model.call_args.args,([8,7],'Pasted question',42))
        for foreign in (9,10,12,999):
            with self.subTest(foreign=foreign):
                response,model=self.request([7,foreign])
                self.assertEqual(response.status_code,404,response.text)
                model.assert_not_called()
    def test_mixed_documents_and_unauthenticated_groups_are_not_sent_to_vision(self):
        response,model=self.request([7,11]);self.assertEqual(response.status_code,422);model.assert_not_called()
        response,model=self.request([7,8],auth=False);self.assertEqual(response.status_code,401);model.assert_not_called()
