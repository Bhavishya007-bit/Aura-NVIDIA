"""Controlled assessment-agent, real PostgreSQL, API and grading regressions."""
import copy
import json
import os
import time
import unittest
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from backend.agents.contracts import Decision, RunInput, allowed_tools
from backend.agents.planning import current_tools, validate_action, ActionRejected
from backend.agents.routes import install_agents, public_run
from backend.agents.runtime import run_agent
from backend.agents.store import RunStopped
from backend.auth_routes import get_current_student
from backend import study_tools
from evaluation import check_agents as fixtures
from evaluation.check_agents import action, Model, SQLCursor


def request(**kwargs):
    return RunInput(course_id=3, source_id=7, skill='assessment', goal='Create 1 question on membranes', **kwargs)


def quiz(count=1):
    prompts = ['Which material is a principal component of biological membranes?',
               'What controls the selective movement of molecules across a cell boundary?',
               'Which membrane property permits vesicles to change their shape?']
    answers = ['Lipids', 'Membrane proteins', 'Flexibility']
    topics = ['Composition', 'Transport', 'Dynamics']
    return action('assessment_create', title='Check your membrane knowledge', focus='membranes', difficulty='beginner',
        questions=[{'prompt': prompts[i], 'choices': [{'id': letter, 'text': text} for letter, text in
                    zip('ABCD', [answers[i], 'Cellulose walls', 'Chromosome replication', 'Ribosomal RNA'])],
                    'correct_choice_id': 'A', 'explanation': 'The cited material states this membrane property.',
                    'topic': topics[i], 'references': ['D1']} for i in range(count)])


def verdict(count=1, supported=True):
    return {'checks': [{'id': f'item-{i}', 'supported': supported} for i in range(1, count+1)]}


class QuizModel(Model):
    def generate_json(self, prompt, **kwargs):
        # The real verifier prompt contains trusted instructions followed by JSON DATA.
        self.calls[-1].update(prompt=prompt, **kwargs)
        self.last_usage = {'prompt_tokens': 900, 'completion_tokens': 90}
        value = next(self.outputs)
        if callable(value): value = value()
        if isinstance(value, Exception): raise value
        return value


class AssessmentContracts(unittest.TestCase):
    def test_assessment_only_gets_implemented_tools_and_requires_source(self):
        permitted = allowed_tools(request())
        self.assertIn('assessment_create', permitted)
        self.assertNotIn('web_search', permitted)
        self.assertNotIn('task_create', permitted)
        self.assertNotIn('memory_write', permitted)
        self.assertEqual(current_tools(request(), permitted, [], 8), {'document_search'})
        self.assertNotIn('finish', current_tools(request(), permitted, [{'tool': 'document_search'}], 7))
        with self.assertRaises(ValueError): RunInput(course_id=3, skill='assessment', goal='Quiz me')
        with self.assertRaises(ValueError): request().model_validate({**request().model_dump(), 'goal': 'Create 6 questions'})

    def test_typed_questions_disallow_extra_accounts_bad_counts_and_unknown_refs(self):
        for mutate in (lambda value: value['action'].update(student_id=43),
                       lambda value: value['action']['questions'][0].update(references=[]),
                       lambda value: value['action']['questions'][0].update(correct_choice_id='E'),
                       lambda value: value['action'].update(questions=[])):
            value = quiz(); mutate(value)
            with self.assertRaises(ValueError): Decision.model_validate(value)
        for refs, code in [(['D999'], 'unknown_reference'), (['Wabcd'], 'source_type_mismatch')]:
            value = quiz(); value['action']['questions'][0]['references'] = refs
            with self.assertRaises(ActionRejected) as caught:
                validate_action(Decision.model_validate(value).action, {'assessment_create'}, set(), {'D1', 'Wabcd'}, request())
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(ActionRejected) as caught:
            validate_action(Decision.model_validate(quiz(3)).action, {'assessment_create'}, set(), {'D1'}, request())
        self.assertEqual(caught.exception.code, 'question_count_mismatch')


@unittest.skipUnless(os.getenv('AURA_PGLITE_MODULE'), 'Optional PostgreSQL engine not configured')
class AssessmentPostgres(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.PostgresAgentChecks.setUpClass.__func__(cls)
        cls.bridge.query(Path('backend/study_tools.sql').read_text())
        cls.bridge.query(Path('backend/learning.sql').read_text())
        cls.bridge.query("UPDATE chunks SET content='Biological membranes contain lipids. Membrane proteins control selective molecular transport across cell boundaries. Flexibility permits shape changes and vesicle formation.' WHERE chunk_id=1")
    @classmethod
    def tearDownClass(cls): cls.bridge.close()
    def setUp(self):
        self.bridge.query('DELETE FROM aura_learning_evidence; DELETE FROM aura_topic_mastery; DELETE FROM aura_study_results; DELETE FROM aura_study_artifacts; DELETE FROM aura_agent_runs; DELETE FROM aura_agent_tasks; DELETE FROM aura_memories; DELETE FROM aura_memory_settings;')
    def prepare(self, req=None):
        self.store.create(42, req or request())
        return self.store.claim('quiz-worker')
    def execute(self, outputs=None, req=None):
        run = self.prepare(req)
        model = QuizModel(outputs or [action('document_search', query='membranes'), quiz(), verdict()])
        run_agent(self.store, run, lambda: model)
        return self.store.runs(42, 3, run['id']), model
    def artifacts(self): return self.bridge.query('SELECT * FROM aura_study_artifacts')
    def draft(self, run):
        self.store.tool(run, Decision.model_validate(action('document_search', query='membranes')).action,
                        {'tool': 'document_search', 'state': 'completed'})
        return self.store.assessment_draft(run, Decision.model_validate(quiz()).action)[0]

    def test_three_question_quiz_is_saved_atomically_and_public_run_never_reveals_keys(self):
        req = request().model_copy(update={'goal': 'Create 3 questions'})
        saved, model = self.execute([action('document_search', query='membranes'), quiz(3), verdict(3)], req)
        self.assertEqual(saved['state'], 'completed', saved)
        artifact = self.artifacts()[0]
        self.assertEqual(str(artifact['id']), str(saved['id']))
        self.assertEqual(len(artifact['payload']['items']), 3)
        self.assertEqual(artifact['payload']['verification'], 'model_checked')
        self.assertEqual(saved['result']['assessment']['question_count'], 3)
        self.assertEqual(saved['tokens_used'], 2970)  # includes the source checker
        self.assertEqual(len(saved['steps']), 3)
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(model.calls[-1]['budget'], 700)
        public = json.dumps(public_run(saved), default=str)
        self.assertNotIn('correct_choice_id', public)
        self.assertNotIn('action', public_run(saved)['steps'][-1])
        self.assertNotIn('evidence_quote', public)
        self.assertEqual(self.store.tasks(42, 3), [])
        with self.assertRaises(RunStopped): self.store.save_assessment(saved, Decision.model_validate(quiz(3)).action, {}, artifact['payload'])
        self.assertEqual(len(self.artifacts()), 1)

    def test_source_checker_runs_outside_database_transaction(self):
        def checked():
            self.assertFalse(self.bridge.lock.locked())
            state = self.bridge.query('SELECT steps FROM aura_agent_runs')[0]
            self.assertEqual(state['steps'][-1]['state'], 'running')
            return verdict()
        saved, _ = self.execute([action('document_search', query='membranes'), quiz(), checked])
        self.assertEqual(saved['state'], 'completed')

    def test_negative_source_verdict_is_never_retried_or_published(self):
        saved, model = self.execute([action('document_search', query='membranes'), quiz(), verdict(supported=False)])
        self.assertEqual(saved['error_code'], 'assessment_not_supported')
        self.assertEqual(saved['state'], 'failed')
        self.assertEqual(len(model.calls), 3)
        self.assertEqual(self.artifacts(), [])

    def test_incomplete_judge_can_repair_once_and_all_usage_is_counted(self):
        saved, model = self.execute([action('document_search', query='membranes'), quiz(), {'checks': []}, verdict()])
        self.assertEqual(saved['state'], 'completed')
        self.assertEqual(len(model.calls), 4)
        self.assertEqual(len(saved['steps']), 4)
        self.assertEqual(saved['tokens_used'], 3960)

    def test_invalid_or_unavailable_judge_cannot_publish(self):
        for checks in ([{'checks': [{'id': 'item-1', 'supported': 'true'}]}]*2,
                       [RuntimeError('PRIVATE provider details')]):
            with self.subTest(checks=checks):
                self.setUp()
                saved, _ = self.execute([action('document_search', query='membranes'), quiz(), *checks])
                self.assertEqual(saved['state'], 'failed')
                self.assertEqual(self.artifacts(), [])
                self.assertNotIn('PRIVATE', str(saved))

    def test_cancel_during_verification_discards_late_quiz(self):
        run = self.prepare()
        def cancel():
            self.store.cancel(42, 3, run['id'])
            return verdict()
        model = QuizModel([action('document_search', query='membranes'), quiz(), cancel])
        run_agent(self.store, run, lambda: model)
        self.assertEqual(self.store.runs(42, 3, run['id'])['state'], 'cancelled')
        self.assertEqual(self.artifacts(), [])

    def test_deadline_during_verification_discards_late_quiz(self):
        def late():
            self.bridge.query("UPDATE aura_agent_runs SET started_at=NOW()-interval '200 seconds'")
            return verdict()
        saved, _ = self.execute([action('document_search', query='membranes'), quiz(), late])
        self.assertEqual(saved['state'], 'timed_out')
        self.assertEqual(self.artifacts(), [])

    def test_step_and_token_budgets_stop_before_publishing(self):
        saved, model = self.execute([action('document_search', query='membranes'), quiz()], request(max_steps=2))
        self.assertEqual(saved['error_code'], 'step_budget')
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(self.artifacts(), [])
        self.setUp()
        run = self.prepare()
        model = QuizModel([action('document_search', query='membranes'), quiz(), verdict()])
        original = model.generate_json
        def expensive(*args, **kwargs):
            result = original(*args, **kwargs)
            if len(model.calls) == 3: model.last_usage = {'prompt_tokens': 31000, 'completion_tokens': 1000}
            return result
        model.generate_json = expensive
        run_agent(self.store, run, lambda: model)
        self.assertEqual(self.store.runs(42, 3, run['id'])['error_code'], 'token_budget')
        self.assertEqual(self.artifacts(), [])

    def test_unchecked_or_changed_payload_and_wrong_user_cannot_save(self):
        run = self.prepare(); draft = self.draft(run); act = Decision.model_validate(quiz()).action
        with self.assertRaises(HTTPException): self.store.tool(run, act, {})
        with self.assertRaises(HTTPException): self.store.save_assessment(run, act, {}, draft)
        with self.assertRaises((RunStopped, HTTPException)): self.store.assessment_draft({**run, 'student_id': 43}, act)
        self.store.record(run, {'tool': 'verification', 'state': 'running'})
        self.store.finish_verification(run, approval=draft)
        changed = copy.deepcopy(draft); changed['items'][0]['correct_choice_id'] = 'B'
        with self.assertRaises(HTTPException): self.store.save_assessment(run, act, {}, changed)
        self.assertEqual(self.artifacts(), [])

    def test_checkpoint_failure_rolls_back_artifact_and_completion(self):
        original = SQLCursor.execute
        def fail(cursor, sql, params=None):
            if "state='completed',result=" in sql: raise RuntimeError('synthetic checkpoint failure')
            return original(cursor, sql, params)
        with patch.object(SQLCursor, 'execute', fail): saved, _ = self.execute()
        self.assertEqual(saved['state'], 'failed')
        self.assertEqual(self.artifacts(), [])

    def test_unknown_references_and_forbidden_actions_never_mutate(self):
        bad = quiz(); bad['action']['questions'][0]['references'] = ['D999']
        for value in (bad, action('web_search', query='outside material'), action('task_create', task={'title': 'Injected'})):
            with self.subTest(tool=value['action']['tool']):
                self.setUp()
                saved, _ = self.execute([action('document_search', query='membranes'), value, value])
                self.assertEqual(saved['state'], 'failed')
                self.assertEqual(self.artifacts(), [])
                self.assertEqual(self.store.tasks(42, 3), [])

    def test_previously_saved_questions_are_not_republished(self):
        first, _ = self.execute(); self.assertEqual(first['state'], 'completed')
        second, model = self.execute([action('document_search', query='membranes'), quiz()])
        self.assertEqual(second['state'], 'failed')
        self.assertEqual(len(self.artifacts()), 1)
        context = json.loads(model.calls[1]['prompt'])['observations'][0]['data']
        self.assertIn(quiz()['action']['questions'][0]['prompt'], context['previous_questions'])
        self.assertTrue(all(isinstance(prompt, str) for prompt in context['previous_questions']))
        self.assertNotIn('correct_choice_id', str(context))

    @contextmanager
    def tuple_database(self):
        bridge = self.bridge
        class TupleCursor(SQLCursor):
            def convert(self, row):
                return tuple(datetime.fromisoformat(v.replace('Z', '+00:00')) if k.endswith('_at') and isinstance(v, str) else v for k, v in row.items())
            def fetchone(self):
                row = super().fetchone(); return self.convert(row) if row else None
            def fetchall(self): return [self.convert(row) for row in super().fetchall()]
        with bridge.connect():
            class Connection:
                def cursor(self): return TupleCursor(bridge)
                def commit(self): pass
            yield Connection()

    def test_background_api_to_existing_assessment_submit_and_progress_evidence(self):
        app = FastAPI(); model = QuizModel([action('document_search', query='membranes'), quiz(), verdict()])
        with patch('backend.agents.routes.Store', return_value=self.store): install_agents(app, lambda: model)
        app.include_router(study_tools.router)
        app.dependency_overrides[get_current_student] = lambda: {'student_id': 42}
        with patch('backend.study_tools.database', self.tuple_database), TestClient(app) as client:
            started = client.post('/agents/runs', json=request().model_dump()); self.assertEqual(started.status_code, 202)
            run_id = started.json()['id']
            for _ in range(80):
                saved = client.get(f'/agents/runs/{run_id}?course_id=3').json()
                if saved['state'] not in ('queued', 'running'): break
                time.sleep(.05)
            self.assertEqual(saved['state'], 'completed', saved)
            self.assertTrue(client.get('/agents/capabilities').json()['assessment_agent'])
            public = client.get('/study/artifacts?course_id=3&source_id=7').json()['artifacts'][0]
            self.assertEqual(public['id'], run_id)
            self.assertNotIn('correct_choice_id', json.dumps(public))
            self.assertNotIn('explanation', json.dumps(public['payload']['items']))
            submitted = client.post(f'/study/assessments/{run_id}/submit', json={'answers': [{'question_id': 'item-1', 'answer': 'A'}]})
            self.assertEqual(submitted.status_code, 200, submitted.text)
            self.assertEqual(submitted.json()['score'], 100)
            self.assertEqual(len(submitted.json()['mastery_updates']), 1)
            repeated = client.post(f'/study/assessments/{run_id}/submit', json={'answers': [{'question_id': 'item-1', 'answer': 'B'}]})
            self.assertEqual(repeated.json()['score'], 100)  # one immutable graded attempt
            self.assertEqual(len(self.bridge.query('SELECT * FROM aura_learning_evidence')), 1)
            app.dependency_overrides[get_current_student] = lambda: {'student_id': 43}
            self.assertEqual(client.get(f'/agents/runs/{run_id}?course_id=4').status_code, 404)
            self.assertEqual(client.post(f'/study/assessments/{run_id}/submit', json={'answers': [{'question_id': 'item-1', 'answer': 'A'}]}).status_code, 404)
        self.assertEqual(len(model.calls), 3)


if __name__ == '__main__': unittest.main()
