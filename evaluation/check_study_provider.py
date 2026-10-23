"""Exercise the real study adapter and Nebius HTTP parser using synthetic responses."""
import copy
import json
import os
import unittest
from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, Mock, patch

import requests
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend import study_tools as study
from backend.auth_routes import get_current_student

MODEL = 'nvidia/nemotron-3-super-120b-a12b'
ENV = {'NEBIUS_API_KEY': 'synthetic-test-key', 'NEBIUS_MODEL': MODEL,
       'NEBIUS_BASE_URL': 'https://api.tokenfactory.nebius.com/v1',
       'NEBIUS_JSON_MAX_TOKENS': '4096'}
EVIDENCE = 'Biological membranes form a lipid bilayer. Integral proteins interact with the hydrophobic membrane core.'
CITATIONS = [{'id': 1, 'chunk_id': 101, 'source_id': 7, 'title': 'synthetic.ppt',
              'location': 'Slide 2', 'slide': 2, 'excerpt': EVIDENCE}]


def response(value=None, *, content=None, finish='stop', status=200):
    reply = Mock(status_code=status, headers={})
    if status >= 400:
        reply.raise_for_status.side_effect = requests.HTTPError('private provider response', response=reply)
    reply.json.return_value = {'choices': [{'finish_reason': finish, 'message': {
        'content': json.dumps(value) if content is None else content}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 80}}
    return reply


class StudyProviderChecks(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, ENV, clear=True)
        env.start(); self.addCleanup(env.stop)

    def test_uses_authenticated_nebius_json_protocol_and_complete_schema(self):
        schema = study.generation_schema(study.GenerateRequest(course_id=3, source_id=7, kind='flashcards', count=1), 1)
        draft = {'items': [{'question': 'What forms a biological membrane?', 'answer': 'A lipid bilayer.', 'citation_ids': [1]}]}
        with patch('backend.ai.llm.requests.post', return_value=response(draft)) as post:
            self.assertEqual(study.model_json('source text', tokens=2400, schema=schema), draft)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args[0], ENV['NEBIUS_BASE_URL'] + '/chat/completions')
        kw = post.call_args.kwargs
        self.assertEqual(kw['headers']['Authorization'], 'Bearer synthetic-test-key')
        self.assertFalse(kw['allow_redirects'])
        payload = kw['json']
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertEqual(payload['max_tokens'], 2400)
        self.assertEqual(payload['reasoning_effort'], 'none')
        for legacy in ('format', 'options', 'num_predict', 'num_ctx'):
            self.assertNotIn(legacy, payload)
        self.assertEqual(payload['messages'][-1]['content'], 'source text')
        actual = payload['messages'][0]['content'].split('schema exactly:\n', 1)[1].split('\nReturn exactly', 1)[0]
        self.assertEqual(json.loads(actual), schema)

    def test_verification_and_writing_have_separate_reasoning_settings(self):
        with patch.dict(os.environ, {'NEBIUS_SUMMARY_REASONING_EFFORT': 'low',
                                     'NEBIUS_VERIFICATION_REASONING_EFFORT': 'none',
                                     'NEBIUS_ANSWER_MODEL': MODEL}), \
                patch('backend.ai.llm.requests.post', return_value=response({'ok': True})) as post:
            study.model_json('writer', tokens=1800)
            study.model_json('judge', tokens=700, verification=True)
        calls = [call.kwargs['json'] for call in post.call_args_list]
        self.assertEqual([p['reasoning_effort'] for p in calls], ['low', 'none'])
        self.assertEqual([p['max_tokens'] for p in calls], [1800, 700])
        self.assertTrue(all(p['model'] == MODEL for p in calls))

    def test_call_budget_obeys_operator_ceiling(self):
        with patch.dict(os.environ, {'AURA_MAX_ANSWER_TOKENS': '5000'}), \
                patch('backend.ai.llm.requests.post', return_value=response({'ok': True})) as post:
            study.model_json('bounded writer', tokens=20000)
        self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 5000)

    def test_authentication_failures_are_503_without_secret_or_provider_advice(self):
        with patch('backend.ai.llm.requests.post', return_value=response(status=401)) as post, \
                self.assertLogs('backend.study_tools', 'WARNING') as captured:
            with self.assertRaises(HTTPException) as failure:
                study.model_json('private material')
        self.assertEqual(post.call_count, 1)
        self.assertEqual(failure.exception.status_code, 503)
        text = str(failure.exception.detail) + ' '.join(captured.output)
        for private in ('synthetic-test-key', 'private material', 'private provider response', 'Ollama'):
            self.assertNotIn(private, text)

    def test_missing_configuration_is_a_controlled_service_error(self):
        with patch.dict(os.environ, {'NEBIUS_API_KEY': ''}), \
                patch('backend.ai.llm.requests.post') as post:
            with self.assertRaises(HTTPException) as failure:
                study.model_json('a goal')
        self.assertEqual(failure.exception.status_code, 503)
        post.assert_not_called()

    def test_transport_failure_has_no_hidden_retry(self):
        with patch('backend.ai.llm.requests.post', side_effect=requests.Timeout()) as post:
            with self.assertRaises(HTTPException) as failure:
                study.model_json('a goal')
        self.assertEqual(failure.exception.status_code, 503)
        self.assertEqual(post.call_count, 1)

    def test_malformed_or_truncated_output_fails_closed(self):
        for content, finish in [('not JSON', 'stop'), ('[]', 'stop'), ('{"ok":true}', 'length')]:
            with self.subTest(content=content, finish=finish), \
                    patch('backend.ai.llm.requests.post', return_value=response(content=content, finish=finish)) as post:
                with self.assertRaises(HTTPException) as failure:
                    study.model_json('fixture')
                self.assertEqual(failure.exception.status_code, 503)
                self.assertEqual(post.call_count, 1)

    def test_valid_negative_source_verdict_is_never_rejudged(self):
        items = [{'id': 'item-1', 'citation_ids': [1], 'question': 'A question', 'answer': 'An unsupported answer'}]
        with patch('backend.ai.llm.requests.post', return_value=response({'checks': [{'id': 'item-1', 'supported': False}]})) as post:
            with self.assertRaises(study.SourceVerificationRejected):
                study.verify_items(items, CITATIONS, 'flashcards')
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 700)

    def test_string_verdicts_cannot_approve_content(self):
        items = [{'id': 'item-1', 'citation_ids': [1], 'question': 'A question', 'answer': 'An answer'}]
        with patch('backend.ai.llm.requests.post', return_value=response({'checks': [{'id': 'item-1', 'supported': 'true'}]})) as post:
            with self.assertRaises(HTTPException) as failure:
                study.verify_items(items, CITATIONS, 'flashcards')
        self.assertEqual(post.call_count, 2)  # Existing bounded structure repair only.
        self.assertEqual(failure.exception.status_code, 422)

    def test_short_answer_grading_uses_the_same_authenticated_judge(self):
        item = {'id': 'item-1', 'kind': 'short_answer', 'prompt': 'What forms the membrane?',
                'answer': 'A lipid bilayer', 'explanation': EVIDENCE, 'topic': 'Membranes', 'citation_ids': [1]}
        with patch('backend.ai.llm.requests.post', return_value=response({'correct': True})) as post:
            result = study.grade_answers([item], [study.Answer(question_id='item-1', answer='A lipid bilayer')], CITATIONS)
        self.assertEqual(result['score'], 100)
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 200)
        self.assertEqual(post.call_args.kwargs['json']['reasoning_effort'], 'none')

    @contextmanager
    def api(self, kind):
        cursor = MagicMock()
        cursor.__enter__.return_value = cursor
        cursor.fetchall.return_value = []
        cursor.fetchone.return_value = (datetime(2026, 10, 23, tzinfo=timezone.utc),)
        connection = MagicMock()
        connection.cursor.return_value = cursor
        @contextmanager
        def database():
            yield connection
        def send(*args, **kwargs):
            prompt = kwargs['json']['messages'][-1]['content']
            if 'Check ALL' in prompt:
                data = json.loads(prompt.rsplit('DATA: ', 1)[1])
                return response({'checks': [{'id': item['id'], 'supported': True} for item in data['records']]})
            if kind == 'flashcards':
                item = {'question': 'What structure forms a biological membrane?', 'answer': 'A lipid bilayer forms the membrane.', 'citation_ids': [1]}
            elif kind == 'assessment':
                item = {'prompt': 'What structure forms a biological membrane?', 'answer': 'A lipid bilayer',
                        'explanation': 'The source states that membranes form a lipid bilayer.', 'topic': 'Membranes', 'citation_ids': [1]}
            else:
                item = {'title': 'Membrane structure', 'text': 'Biological membranes form a lipid bilayer. Integral proteins interact with its hydrophobic core.', 'citation_ids': [1]}
            return response({'items': [item]})
        app = FastAPI()
        app.include_router(study.router)
        app.dependency_overrides[get_current_student] = lambda: {'student_id': 42}
        with patch.object(study, 'database', database), \
                patch.object(study, 'learner_profile', return_value={'topics': []}), \
                patch.object(study, 'source_passages', side_effect=lambda *a, **k: ('synthetic.ppt', copy.deepcopy(CITATIONS), 1)), \
                patch('backend.ai.llm.requests.post', side_effect=send) as post, TestClient(app) as client:
            yield client, cursor, connection, post

    def test_all_study_kinds_generate_verify_and_save_through_existing_route(self):
        for kind in ('flashcards', 'notes', 'summary', 'assessment'):
            with self.subTest(kind=kind), self.api(kind) as (client, cursor, connection, post):
                result = client.post('/study/tools', json={'course_id': 3, 'source_id': 7,
                    'kind': kind, 'count': 1, 'question_type': 'short_answer',
                    'difficulty': 'beginner', 'focus': 'Membrane structure', 'learning_mode': 'manual'})
                self.assertEqual(result.status_code, 201, result.text)
                body = result.json()
                self.assertEqual(set(body), {'id', 'kind', 'payload', 'created_at', 'result'})
                self.assertEqual(body['kind'], kind)
                self.assertEqual(body['payload']['source_id'], 7)
                self.assertEqual(body['payload']['focus'], 'Membrane structure')
                self.assertEqual(body['payload']['items'][0]['citation_ids'], [1])
                self.assertEqual(body['payload']['verification'], 'model_checked')
                if kind == 'assessment':
                    self.assertNotIn('answer', body['payload']['items'][0])
                    self.assertNotIn('explanation', body['payload']['items'][0])
                connection.commit.assert_called_once()
                insert = next(c for c in cursor.execute.call_args_list if 'INSERT INTO aura_study_artifacts' in c.args[0])
                self.assertEqual(insert.args[1][1:4], (42, 3, 7))
                self.assertEqual(post.call_count, 2)
                self.assertTrue(all(c.kwargs['headers']['Authorization'] == 'Bearer synthetic-test-key' for c in post.call_args_list))

    def test_generated_citations_still_cannot_reference_missing_evidence(self):
        request = study.GenerateRequest(course_id=3, source_id=7, kind='flashcards', count=1)
        value = {'items': [{'question': 'A question', 'answer': 'An answer', 'citation_ids': [99]}]}
        with self.assertRaises(HTTPException) as failure:
            study.validate_items(study.attach_source_evidence(value, CITATIONS), request, CITATIONS, set())
        self.assertEqual(failure.exception.status_code, 422)


if __name__ == '__main__':
    unittest.main()
