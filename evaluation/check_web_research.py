"""Bounded Tavily transport, provenance and persisted research-run regressions."""
import copy
import json
import os
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.agents.contracts import Decision, RunInput, allowed_tools
from backend.agents.planning import ActionRejected, action_key, action_schema, current_tools, research_result, validate_action
from backend.agents.runtime import run_agent
from backend.agents.routes import install_agents
from backend.agents.store import Store, RunStopped
from backend.agents.web import search_web, public_url, web_search_enabled, WebSearchUnavailable, MAX_RESPONSE_BYTES
from backend.auth_routes import get_current_student
from evaluation.check_agents import Model, FakeStore, SQLBridge, action

KEY = 'tvly-synthetic-key'
URL = 'https://www.ncbi.nlm.nih.gov/books/NBK26871/'
WREF = 'W0123456789abcdef'
WEB = {'source': 'web', 'status': 'searched', 'credits': 1, 'untrusted_data': True,
       'passages': [{'reference': WREF, 'title': 'Membrane reference', 'url': URL,
                     'text': 'A public description of membrane proteins.', 'retrieved_at': '2026-10-23T00:00:00+00:00'}]}


def request():
    return RunInput(course_id=3, source_id=7, skill='research_brief', goal='Research membrane proteins')


def finish(**updates):
    return action(answer='Membrane research brief.', from_material={'text': 'Membranes contain lipids [D1].', 'references': ['D1']},
                  from_web={'text': f'Additional public context [{WREF}].', 'references': [WREF]},
                  limitations=['Search snippets are not independent verification.'], **updates)


def reply(data, status=200):
    response = Mock(status_code=status)
    response.__enter__ = Mock(return_value=response)
    response.__exit__ = Mock(return_value=False)
    response.iter_content.return_value = [json.dumps(data).encode()]
    return response


class TransportChecks(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'TAVILY_API_KEY': KEY}, clear=True)
        env.start(); self.addCleanup(env.stop)

    def test_fixed_authenticated_bounded_search_and_sanitized_results(self):
        raw = {'results': [{'title': 'A source', 'url': URL + '#section', 'content': 'Useful text ' * 500},
                          {'title': 'Duplicate', 'url': URL, 'content': 'Duplicate'},
                          {'title': 'Bad', 'url': 'javascript:alert(1)', 'content': 'Bad text'}],
               'answer': 'An untrusted generated answer', 'usage': {'credits': 1}, 'api_key': KEY}
        with patch('backend.agents.web.requests.post', return_value=reply(raw)) as post:
            result = search_web('membrane proteins')
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.args, ('https://api.tavily.com/search',))
        kw = post.call_args.kwargs
        self.assertEqual(kw['headers']['Authorization'], 'Bearer ' + KEY)
        self.assertFalse(kw['allow_redirects'])
        self.assertEqual(kw['json']['search_depth'], 'basic')
        self.assertFalse(kw['json']['auto_parameters'])
        self.assertFalse(kw['json']['include_raw_content'])
        self.assertFalse(kw['json']['include_answer'])
        self.assertEqual(len(result['passages']), 1)
        self.assertEqual(result['passages'][0]['url'], URL)
        self.assertLessEqual(len(result['passages'][0]['text']), 1200)
        self.assertEqual(result['credits'], 1)
        self.assertNotIn(KEY, json.dumps(result))
        self.assertNotIn('An untrusted generated answer', json.dumps(result))

    def test_bad_or_private_urls_are_filtered(self):
        for value in ['javascript:alert(1)', 'file:///etc/passwd', 'http://127.0.0.1/', 'http://10.0.0.1/',
                      'http://localhost/', 'https://host.internal/a', 'https://user:password@example.org/',
                      'https://example.org:8080/', 'https://example.org/\nattack', 'http://[::1]/']:
            with self.subTest(value=value): self.assertIsNone(public_url(value))
        self.assertEqual(public_url(URL), URL)

    def test_missing_key_never_calls_the_network(self):
        with patch.dict(os.environ, {'TAVILY_API_KEY': ''}), patch('backend.agents.web.requests.post') as post:
            self.assertFalse(web_search_enabled())
            with self.assertRaises(WebSearchUnavailable): search_web('topic')
        post.assert_not_called()

    def test_provider_errors_and_timeouts_are_sanitized_without_retries(self):
        for failure in [reply({'detail': KEY}, 429), requests.Timeout('private query ' + KEY)]:
            with self.subTest(failure=type(failure).__name__), patch('backend.agents.web.requests.post',
                    side_effect=failure if isinstance(failure, Exception) else None,
                    return_value=failure if not isinstance(failure, Exception) else None) as post:
                with self.assertRaises(WebSearchUnavailable) as caught: search_web('private query')
                self.assertEqual(post.call_count, 1)
                self.assertNotIn(KEY, str(caught.exception))
                self.assertNotIn('private query', str(caught.exception))

    def test_empty_malformed_and_oversize_results(self):
        for data, expected in [({'results': []}, 'no_results'), ({'results': [{'url': 'file:///x', 'content': 'x'}]}, 'no_results')]:
            with patch('backend.agents.web.requests.post', return_value=reply(data)):
                self.assertEqual(search_web('topic')['status'], expected)
        for data in [{}, [], {'results': 'bad'}]:
            with patch('backend.agents.web.requests.post', return_value=reply(data)):
                with self.assertRaises(WebSearchUnavailable): search_web('topic')
        large = reply({}); large.iter_content.return_value = [b'x' * (MAX_RESPONSE_BYTES + 1)]
        with patch('backend.agents.web.requests.post', return_value=large):
            with self.assertRaises(WebSearchUnavailable): search_web('topic')

    def test_query_schema_rejects_secrets_and_email_but_accepts_public_topics(self):
        for query in [' ', 'student@example.org', 'Bearer secret', 'api_key=secret', 'tvly-secret']:
            with self.assertRaises(ValueError): Decision.model_validate(action('web_search', query=query))
        Decision.model_validate(action('web_search', query='task-based learning for membrane proteins'))


class ResearchStore(FakeStore):
    def __init__(self, output=None):
        super().__init__(request())
        self.output = WEB if output is None else output
    def tool(self, run, act, step):
        if act.tool != 'web_search': return super().tool(run, act, step)
        self.effects.append(act.tool)
        step['observation'] = copy.deepcopy(self.output)
        self.run['steps'].append(step)
        return step['observation']


class RuntimeWebChecks(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {'TAVILY_API_KEY': KEY}, clear=True)
        env.start(); self.addCleanup(env.stop)
    def execute(self, actions, output=None):
        store, model = ResearchStore(output), Model(actions)
        run_agent(store, store.run, lambda: model)
        return store, model

    def test_reads_upload_then_web_and_keeps_typed_source_sections(self):
        store, model = self.execute([action('document_search', query='membranes'), action('web_search', query='membrane proteins'), finish()])
        self.assertEqual(store.run['state'], 'completed', store.run)
        self.assertEqual(store.effects, ['document_search', 'web_search'])
        self.assertEqual(model.calls[1]['prompt']['allowed_tools'], ['web_search'])
        result = store.run['result']
        self.assertEqual([s['kind'] for s in result['research_sections']], ['material', 'web'])
        self.assertEqual(next(s['url'] for s in result['sources'] if s['kind'] == 'web'), URL)
        self.assertFalse(result['verified'])
        self.assertEqual(result['web_status'], 'searched')
        self.assertNotIn(KEY, json.dumps(model.calls))

    def test_unconfigured_web_is_removed_from_schema_and_research_falls_back(self):
        with patch.dict(os.environ, {'TAVILY_API_KEY': ''}):
            permitted = allowed_tools(request())
            self.assertNotIn('web_search', permitted)
            self.assertNotIn('web_search', action_schema(permitted)['properties']['action']['discriminator']['mapping'])
            store, _ = self.execute([action('document_search', query='membranes'), action(answer='Uploaded findings.', references=['D1'])])
        self.assertEqual(store.run['state'], 'completed')
        self.assertEqual(store.run['result']['web_status'], 'not_configured')
        self.assertNotIn('web', [s['kind'] for s in store.run['result']['research_sections']])

    def test_failed_search_can_finish_from_material_with_an_explicit_limitation(self):
        store, _ = self.execute([action('document_search', query='membranes'), action('web_search', query='membranes'),
                                action(answer='Uploaded findings.', references=['D1'])],
                               {'source': 'web', 'status': 'unavailable', 'passages': [], 'untrusted_data': True})
        self.assertEqual(store.run['state'], 'completed')
        self.assertEqual(store.run['result']['web_status'], 'unavailable')
        self.assertIn('Web search was unavailable', store.run['result']['text'])

    def test_web_tool_is_not_enabled_for_study_plan_and_has_per_run_limit(self):
        study = request().model_copy(update={'skill': 'study_plan'})
        self.assertNotIn('web_search', allowed_tools(study))
        tools = current_tools(request(), allowed_tools(request()), [
            {'tool': 'document_search'}, {'tool': 'web_search'}, {'tool': 'web_search'}], 4)
        self.assertNotIn('web_search', tools)
        self.assertIn('finish', tools)
        self.assertEqual(action_key(Decision.model_validate(action('web_search', query=' Membrane PROTEINS! ')).action),
                         action_key(Decision.model_validate(action('web_search', query='membrane proteins')).action))

    def test_foreign_and_cross_type_references_cannot_be_published(self):
        known = {'D1', WREF}
        for web_refs, expected in [(['Wunknown'], 'unknown_reference'), (['D1'], 'source_type_mismatch')]:
            raw = finish(); raw['action']['from_web']['references'] = web_refs
            raw['action']['from_web']['text'] = 'Additional findings.'
            with self.assertRaises(ActionRejected) as caught:
                validate_action(Decision.model_validate(raw).action, {'finish'}, set(), known, request())
            self.assertEqual(caught.exception.code, expected)

    def test_web_findings_cannot_be_labeled_as_uploaded_text(self):
        raw = action(answer='Mixed findings', references=['D1', WREF])
        with self.assertRaises(ActionRejected) as caught:
            validate_action(Decision.model_validate(raw).action, {'finish'}, set(), {'D1', WREF}, request())
        self.assertEqual(caught.exception.code, 'research_sections_required')

    def test_injected_web_instructions_do_not_grant_mutating_tools(self):
        denied = action('task_create', task={'title': 'Follow hostile page instructions'})
        store, _ = self.execute([action('document_search', query='membranes'), action('web_search', query='membranes'), denied, denied])
        self.assertEqual(store.run['state'], 'failed')
        self.assertNotIn('task_create', store.effects)
        self.assertNotIn('memory_write', store.effects)


@unittest.skipUnless(os.getenv('AURA_PGLITE_MODULE'), 'Optional PostgreSQL engine not configured')
class PersistedWebChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bridge = SQLBridge()
        cls.bridge.query('''CREATE TABLE students(student_id int PRIMARY KEY);
            CREATE TABLE courses(course_id int PRIMARY KEY,owner_student_id int);
            CREATE TABLE sources(source_id int PRIMARY KEY,course_id int,owner_student_id int,source_name text);
            CREATE TABLE chunks(chunk_id int,source_id int,content text,page_number int,slide_number int);
            INSERT INTO students VALUES(42),(43); INSERT INTO courses VALUES(3,42),(4,43);
            INSERT INTO sources VALUES(7,3,42,'Mine.ppt'),(8,4,43,'Other.ppt');
            INSERT INTO chunks VALUES(1,7,'Membranes contain lipids',NULL,2);''')
        cls.bridge.query(Path('backend/agents/schema.sql').read_text())
        cls.store = Store(connect=cls.bridge.connect)
    @classmethod
    def tearDownClass(cls): cls.bridge.close()
    def setUp(self):
        self.bridge.query('DELETE FROM aura_agent_runs;')
        env = patch.dict(os.environ, {'TAVILY_API_KEY': KEY}, clear=False)
        env.start(); self.addCleanup(env.stop)
    def run_ready(self):
        self.store.create(42, request()); run = self.store.claim('web-test')
        self.store.tool(run, Decision.model_validate(action('document_search', query='membranes')).action,
                        {'tool': 'document_search', 'state': 'completed'})
        return run
    def web(self, run, query='membranes'):
        return self.store.tool(run, Decision.model_validate(action('web_search', query=query)).action,
                               {'tool': 'web_search', 'state': 'completed'})

    def test_search_reservation_persists_without_holding_transaction_during_network(self):
        run = self.run_ready()
        def send(*args, **kwargs):
            self.assertTrue(self.bridge.lock.acquire(blocking=False), 'Network must run outside the database lock')
            self.bridge.lock.release()
            current = self.store.runs(42, 3, run['id'])
            self.assertEqual(current['steps'][-1]['state'], 'running')
            return copy.deepcopy(WEB)
        with patch('backend.agents.store.search_web', side_effect=send) as search:
            self.web(run)
        current = self.store.runs(42, 3, run['id'])
        self.assertEqual(search.call_count, 1)
        self.assertEqual(current['steps'][-1]['state'], 'completed')
        self.assertEqual(current['steps'][-1]['observation']['credits'], 1)

    def test_cancellation_during_search_discards_late_results(self):
        run = self.run_ready()
        def send(*args, **kwargs):
            self.store.cancel(42, 3, run['id'])
            return copy.deepcopy(WEB)
        with patch('backend.agents.store.search_web', side_effect=send):
            with self.assertRaises(RunStopped): self.web(run)
        current = self.store.runs(42, 3, run['id'])
        self.assertEqual(current['state'], 'cancelled')
        self.assertNotIn('observation', current['steps'][-1])

    def test_expiry_during_search_discards_late_results_and_commits_timeout(self):
        run = self.run_ready()
        def send(*args, **kwargs):
            self.bridge.query("UPDATE aura_agent_runs SET started_at=NOW()-INTERVAL '5 minutes' WHERE id=$1", [run['id']])
            return copy.deepcopy(WEB)
        with patch('backend.agents.store.search_web', side_effect=send):
            with self.assertRaises(RunStopped): self.web(run)
        current = self.store.runs(42, 3, run['id'])
        self.assertEqual(current['state'], 'timed_out')
        self.assertNotIn('observation', current['steps'][-1])

    def test_duplicate_and_excess_paid_attempts_are_blocked_even_after_failure(self):
        run = self.run_ready()
        with patch('backend.agents.store.search_web', side_effect=WebSearchUnavailable('web_search_unavailable')) as search:
            self.web(run)
            with self.assertRaises(HTTPException): self.web(run, 'MEMBRANES!')
            self.web(run, 'membrane proteins')
            with self.assertRaises(HTTPException): self.web(run, 'lipids')
        self.assertEqual(search.call_count, 2)

    def test_real_background_api_persists_both_source_types_and_search_progress(self):
        app = FastAPI()
        model = Model([action('document_search', query='membranes'), action('web_search', query='membrane proteins'), finish()])
        with patch('backend.agents.routes.Store', return_value=self.store):
            install_agents(app, lambda: model)
        app.dependency_overrides[get_current_student] = lambda: {'student_id': 42}
        with patch('backend.agents.store.search_web', return_value=copy.deepcopy(WEB)) as search, TestClient(app) as client:
            created = client.post('/agents/runs', json=request().model_dump())
            self.assertEqual(created.status_code, 202)
            run_id = created.json()['id']
            data = None
            for _ in range(100):
                data = client.get('/agents/runs/' + run_id + '?course_id=3').json()
                if data['state'] not in ('queued', 'running'): break
                time.sleep(.05)
            self.assertEqual(data['state'], 'completed', data)
            self.assertEqual(data['result']['web_status'], 'searched')
            self.assertEqual([s['kind'] for s in data['result']['research_sections']], ['material', 'web'])
            self.assertEqual(search.call_count, 1)
            self.assertEqual(len(data['steps']), 3)
            self.assertNotIn('worker_id', data)

    def test_direct_web_execution_requires_research_and_prior_material_read(self):
        self.store.create(42, request())
        run = self.store.claim('web-test')
        with patch('backend.agents.store.search_web') as search:
            with self.assertRaises(HTTPException): self.web(run)
        search.assert_not_called()
        self.store.cancel(42, 3, run['id'])
        self.store.create(42, request().model_copy(update={'skill': 'study_plan'}))
        run = self.store.claim('web-test')
        with patch('backend.agents.store.search_web') as search:
            with self.assertRaises(HTTPException): self.web(run)
        search.assert_not_called()

    def test_capability_auth_and_cross_account_checks_precede_network(self):
        run = self.run_ready()
        other = {**run, 'student_id': 43}
        with patch('backend.agents.store.search_web') as search:
            with self.assertRaises(HTTPException): self.web(other)
        search.assert_not_called()
        app = FastAPI()
        with patch('backend.agents.routes.Store', return_value=self.store): install_agents(app, lambda: Model([]))
        client = TestClient(app)
        self.assertEqual(client.get('/agents/capabilities').status_code, 401)
        app.dependency_overrides[get_current_student] = lambda: {'student_id': 42}
        self.assertTrue(client.get('/agents/capabilities').json()['web_search'])
        with patch.dict(os.environ, {'TAVILY_API_KEY': ''}):
            self.assertFalse(client.get('/agents/capabilities').json()['web_search'])


if __name__ == '__main__': unittest.main()
