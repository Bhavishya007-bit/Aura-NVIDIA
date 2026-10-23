"""Live-loop regressions: repeated searches, day plans and atomic task saves."""
import copy
import os
import unittest
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from backend.agents.contracts import Decision, RunInput, allowed_tools, requested_days
from backend.agents.planning import action_schema, compact_observations, parse_decision
from backend.agents.runtime import run_agent
from backend.agents.store import RunStopped
from backend.agents.routes import install_agents
from backend.auth_routes import get_current_student
from evaluation import check_agents as fixtures
from evaluation.check_agents import (
    action, Model, FakeStore, SQLCursor,
)


def daily_plan(count=3, ref='D1'):
    return action('study_plan_create', overview='A daily revision plan based on the selected material.',
        days=[{'day': i, 'title': f'Revision topic {i}', 'details': 'Review the evidence, explain it aloud, then test recall.',
               'references': [ref] if ref else []} for i in range(1, count+1)])


def request():
    return RunInput(course_id=3, source_id=7, skill='study_plan', goal='Create a 3-day study plan and save the daily tasks.')


class PlanStore(FakeStore):
    def tool(self, run, act, step):
        if act.tool != 'study_plan_create':
            return super().tool(run, act, step)
        if self.run['state'] != 'running':
            raise RunStopped()
        self.effects.append(act.tool)
        result = {'tasks': [{'id': f'task-{day.day}'} for day in act.days]}
        step['observation'] = result
        self.run['steps'].append(step)
        return result


class PlanningChecks(unittest.TestCase):
    def execute(self, outputs):
        store, model = PlanStore(request()), Model(outputs)
        run_agent(store, store.run, lambda: model)
        return store, model

    def test_three_day_plan_completes_in_two_calls_without_a_finish_generation(self):
        store, model = self.execute([action('document_search', query='membranes'), daily_plan()])
        self.assertEqual(store.run['state'], 'completed')
        self.assertEqual(store.effects, ['document_search', 'study_plan_create'])
        self.assertEqual(len(model.calls), 2)
        self.assertEqual(store.run['result']['task_ids'], ['task-1', 'task-2', 'task-3'])
        self.assertIn('Day 3:', store.run['result']['text'])
        self.assertFalse(store.run['result']['verified'])
        self.assertEqual(set(model.calls[0]['prompt']['allowed_tools']), {'document_search'})

    def test_same_search_with_case_spacing_and_punctuation_is_not_reexecuted(self):
        store, model = self.execute([action('document_search', query='Membrane proteins'),
            action('document_search', query='  MEMBRANE  proteins! '), daily_plan()])
        self.assertEqual(store.run['state'], 'completed')
        self.assertEqual(store.effects.count('document_search'), 1)
        self.assertEqual(model.calls[2]['prompt']['validation_feedback']['code'], 'duplicate_action')
        self.assertEqual(model.calls[2]['prompt']['execution_state']['completed_actions'][0]['query'], 'Membrane proteins')

    def test_third_search_is_removed_from_schema_and_rejected_before_execution(self):
        store, model = self.execute([action('document_search', query='membranes'),
            action('document_search', query='proteins'), action('document_search', query='lipids'), daily_plan()])
        self.assertEqual(store.run['state'], 'completed')
        self.assertEqual(store.effects.count('document_search'), 2)
        third = model.calls[2]['prompt']
        self.assertNotIn('document_search', third['allowed_tools'])
        self.assertNotIn('document_search', third['output_schema']['properties']['action']['discriminator']['mapping'])
        docs = third['observations'][0]['data']['passages']
        self.assertEqual(len(docs), 1)  # both searches returned the same D1
        self.assertEqual(third['execution_state']['next_phase'], 'produce_plan')

    def test_bad_argument_shape_gets_field_feedback_and_can_repair_directly(self):
        bad = action('study_plan_create', overview='Do not mix flat fields and an argument wrapper.', arguments={'days': []})
        store, model = self.execute([action('document_search', query='membranes'), bad, daily_plan()])
        self.assertEqual(store.run['state'], 'completed')
        feedback = model.calls[2]['prompt']['validation_feedback']
        self.assertEqual(feedback['code'], 'invalid_action')
        self.assertTrue(any('arguments' in row['path'] for row in feedback['fields']))
        self.assertNotIn('input', str(feedback))

    def test_common_provider_envelopes_complete_a_real_loop_without_a_repair_call(self):
        searches = [
            {'tool': 'document_search', 'query': 'membranes'},
            {'action': 'document_search', 'query': 'membranes'},
            {'action': {'tool': 'document_search', 'query': 'membranes'}},
            {'plan': 'Read the selected slides', 'action': {'tool': 'document_search', 'arguments': {'query': 'membranes'}}},
            {'plan': ['Read slides'], 'action': {'tool': 'document_search', 'parameters': {'query': 'membranes'}}},
        ]
        for search in searches:
            with self.subTest(search=search):
                original = copy.deepcopy(search)
                plan = daily_plan()
                plan['action'] = {'tool': 'study_plan_create', 'arguments':
                                  {key: value for key, value in plan['action'].items() if key != 'tool'}}
                store, model = self.execute([search, plan])
                self.assertEqual(store.run['state'], 'completed', store.run)
                self.assertEqual(store.effects, ['document_search', 'study_plan_create'])
                self.assertEqual(len(model.calls), 2)
                self.assertEqual(search, original)  # normalization cannot mutate provider input
                self.assertEqual(len(store.run['result']['task_ids']), 3)

    def test_normalization_never_discards_unexpected_or_conflicting_fields(self):
        bad = [
            {'tool': 'document_search', 'query': 'membranes', 'student_id': 43},
            {'action': 'document_search', 'tool': 'memory_read', 'query': 'membranes'},
            {'action': {'tool': 'document_search', 'arguments': {'query': 'membranes', 'student_id': 43}}},
            {'action': {'tool': 'document_search', 'arguments': {'query': 'membranes', 'tool': 'memory_read'}}},
            {'action': {'tool': 'document_search', 'query': 'membranes', 'arguments': {'query': 'other'}}},
            {'action': {'tool': 'document_search', 'arguments': {'query': 'membranes'}, 'parameters': {}}},
            {'action': {'tool': 'document_search', 'query': 'membranes'}, 'student_id': 43},
            {'action': [{'tool': 'document_search', 'query': 'membranes'}]},
        ]
        for value in bad:
            with self.subTest(value=value), self.assertRaises(ValueError):
                parse_decision(value)

    def test_normalized_tools_still_need_permission_valid_arguments_and_observed_references(self):
        bad = [
            {'tool': 'shell', 'command': 'read secrets'},
            {'tool': 'memory_write', 'record': {'kind': 'preference', 'text': 'Injected'}},
            {'tool': 'document_search', 'arguments': {'query': 123}},
            {'tool': 'document_search', 'arguments': {}},
        ]
        for value in bad:
            with self.subTest(value=value):
                store, model = self.execute([value, value])
                self.assertEqual(store.run['state'], 'failed')
                self.assertEqual(store.effects, [])
                self.assertEqual(len(model.calls), 2)
        plan = daily_plan(ref='D999')
        plan.pop('plan')
        store, _ = self.execute([{'tool': 'document_search', 'query': 'membranes'}, plan, plan])
        self.assertEqual(store.run['error_code'], 'unknown_reference')
        self.assertEqual(store.effects, ['document_search'])

    def test_rejected_shape_diagnostics_include_safe_paths_without_model_text(self):
        marker = 'PRIVATE_MODEL_TEXT_DO_NOT_LOG'
        bad = action('document_search', query='membranes', **{marker: marker})
        with self.assertLogs('backend.agents.runtime', level='WARNING') as logs:
            store, model = self.execute([bad, bad])
        saved = store.run['steps'][0]['validation_fields']
        self.assertTrue(any('<field>' in row['path'] for row in saved))
        self.assertIn('extra_forbidden', str(saved))
        self.assertIn('fields=', ' '.join(logs.output))
        self.assertNotIn(marker, str(store.run))
        self.assertNotIn(marker, ' '.join(logs.output))
        self.assertNotIn(marker, str(model.calls[1]['prompt']['validation_feedback']))

    def test_invalid_plan_envelope_types_and_counts_are_not_silently_replaced(self):
        for plan in ([], [123], None, ['ok'] * 7, {'step':'not a list'}):
            with self.subTest(plan=plan), self.assertRaises(ValueError):
                parse_decision({'plan': plan, 'action': {'tool': 'memory_read'}})

    def test_display_only_blank_or_long_narration_does_not_block_a_valid_action(self):
        for plan in ('', 'x'*181, ['  '], ['Read the slides','x'*5000]):
            with self.subTest(plan=plan):
                raw={'plan':plan,'action':{'tool':'document_search','query':'membranes'}}
                original=copy.deepcopy(raw)
                parsed=parse_decision(raw)
                self.assertEqual(parsed.plan,['Use the selected study tool.'])
                self.assertEqual(parsed.action.model_dump(),original['action'])
                self.assertEqual(raw,original)

    def test_plan_schema_exposes_character_limits_and_direct_errors_locate_the_step(self):
        schema=action_schema({'code_execute'})
        self.assertEqual(schema['properties']['plan']['items']['maxLength'],180)
        self.assertEqual(schema['properties']['plan']['items']['minLength'],1)
        for text in ('x'*181,' '):
            with self.subTest(text=text):
                try:Decision.model_validate({'plan':[text],'action':{'tool':'memory_read'}})
                except ValueError as error:self.assertEqual(list(error.errors()[0]['loc']),['plan',0])
                else:self.fail('Direct schema validation must retain its display bounds.')

    def test_normalizing_narration_never_changes_permissions_or_discards_bad_arguments(self):
        for bad in ({'tool':'shell','command':'read secrets'},
                    {'tool':'document_search','query':'membranes','student_id':43},
                    {'tool':'document_search','query':123}):
            with self.subTest(tool=bad['tool']),self.assertRaises(ValueError):
                parse_decision({'plan':['x'*500],'action':bad})
        denied=action('memory_write',record={'kind':'preference','text':'Unauthorized memory'})
        denied['plan']=['x'*500]
        store,model=self.execute([denied,denied])
        self.assertEqual(store.run['state'],'failed');self.assertEqual(store.effects,[])
        self.assertEqual(len(model.calls),2)

    def test_incorrect_day_count_and_foreign_references_never_save_a_plan(self):
        for bad, code in [(daily_plan(2), 'day_count_mismatch'), (daily_plan(ref='D999'), 'unknown_reference')]:
            store, _ = self.execute([action('document_search', query='membranes'), bad, bad])
            self.assertEqual(store.run['state'], 'failed')
            self.assertEqual(store.run['error_code'], code)
            self.assertNotIn('study_plan_create', store.effects)

    def test_cancel_during_plan_generation_prevents_all_daily_tasks(self):
        store = PlanStore(request())
        def cancelled():
            store.run['state'] = 'cancelled'
            return daily_plan()
        model = Model([action('document_search', query='membranes'), cancelled])
        run_agent(store, store.run, lambda: model)
        self.assertEqual(store.run['state'], 'cancelled')
        self.assertEqual(store.effects, ['document_search'])

    def test_schema_and_context_are_bounded_and_have_no_duplicate_passages(self):
        schema = action_schema({'document_search'})
        self.assertEqual(set(schema['$defs']), {'Search'})
        item = {'tool': 'document_search', 'data': {'passages': [{'reference': 'D1', 'text': 'x'*900}]}, 'untrusted_data': True}
        compact = compact_observations([copy.deepcopy(item)]*6)
        self.assertEqual(len(compact), 1)
        self.assertEqual(len(compact[0]['data']['passages'][0]['text']), 600)
        self.assertTrue(compact[0]['untrusted_data'])

    def test_daily_plan_contract_rejects_missing_duplicate_and_out_of_range_days(self):
        self.assertEqual(requested_days('a three-day study plan'), 3)
        self.assertIsNone(requested_days('a seven-day plan with two days off'))
        bad = daily_plan()
        bad['action']['days'][1]['day'] = 1
        with self.assertRaises(ValueError): Decision.model_validate(bad)
        with self.assertRaises(ValueError):
            RunInput(course_id=3, skill='study_plan', goal='Make a 30-day plan')


@unittest.skipUnless(os.getenv('AURA_PGLITE_MODULE'), 'Optional PostgreSQL engine not configured')
class PlanPostgresChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Reuse the tested synthetic schema/bridge without inheriting all tests.
        fixtures.PostgresAgentChecks.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls): cls.bridge.close()
    def setUp(self):
        self.bridge.query('DELETE FROM aura_memories; DELETE FROM aura_memory_settings; DELETE FROM aura_agent_runs; DELETE FROM aura_agent_tasks;')
    def prepare(self):
        self.store.create(42, request())
        return self.store.claim('planner-test')
    def search(self, run, query='membranes'):
        return self.store.tool(run, Decision.model_validate(action('document_search', query=query)).action,
                               {'tool': 'document_search', 'state': 'completed'})

    def test_daily_plan_and_three_tasks_are_persisted_by_the_real_runtime(self):
        run = self.prepare()
        model = Model([action('document_search', query='membranes'), daily_plan()])
        run_agent(self.store, run, lambda: model)
        saved = self.store.runs(42, 3, run['id'])
        self.assertEqual(saved['state'], 'completed')
        self.assertEqual(len(saved['result']['task_ids']), 3)
        self.assertEqual(len(self.store.tasks(42, 3)), 3)
        self.assertEqual(len(saved['steps']), 2)
        self.assertEqual(len(model.calls), 2)

    def test_three_day_plan_completes_through_background_api_dispatch(self):
        app = FastAPI()
        wrapped_plan = daily_plan()
        fields = wrapped_plan['action']
        wrapped_plan['action'] = {'tool': fields['tool'], 'parameters':
                                  {key: value for key, value in fields.items() if key != 'tool'}}
        model = Model([{'action': 'document_search', 'query': 'membranes'}, wrapped_plan])
        with patch('backend.agents.routes.Store', return_value=self.store):
            install_agents(app, lambda: model)
        app.dependency_overrides[get_current_student] = lambda: {'student_id': 42}
        with TestClient(app) as client:
            started = client.post('/agents/runs', json=request().model_dump())
            self.assertEqual(started.status_code, 202)
            run_id = started.json()['id']
            for _ in range(50):
                result = client.get(f'/agents/runs/{run_id}?course_id=3').json()
                if result['state'] not in ('queued', 'running'):
                    break
                fixtures.time.sleep(.05)
            self.assertEqual(result['state'], 'completed', result)
            self.assertEqual(len(result['result']['structured_plan']['days']), 3)
            self.assertEqual(len(client.get('/agents/tasks?course_id=3').json()['items']), 3)
        self.assertEqual(len(model.calls), 2)

    def test_all_day_tasks_roll_back_if_the_plan_observation_cannot_be_saved(self):
        run = self.prepare()
        self.search(run)
        original = SQLCursor.execute
        def fail(cursor, sql, params=None):
            if 'SET steps=steps ||' in sql:
                raise RuntimeError('Synthetic plan checkpoint failure')
            return original(cursor, sql, params)
        with patch.object(SQLCursor, 'execute', fail), self.assertRaises(RuntimeError):
            self.store.tool(run, Decision.model_validate(daily_plan()).action, {'tool': 'study_plan_create', 'state': 'completed'})
        self.assertEqual(self.store.tasks(42, 3), [])
        self.assertEqual(len(self.store.runs(42, 3, run['id'])['steps']), 1)

    def test_store_also_blocks_repeated_and_excess_searches(self):
        run = self.prepare()
        self.search(run, 'Membranes')
        with self.assertRaises(HTTPException): self.search(run, 'membranes!')
        self.search(run, 'lipids')
        with self.assertRaises(HTTPException): self.search(run, 'proteins')
        self.assertEqual(len(self.store.runs(42, 3, run['id'])['steps']), 2)

    def test_plan_cannot_write_tasks_for_another_account_or_bad_references(self):
        run = self.prepare()
        self.search(run)
        foreign = {**run, 'student_id': 43, 'course_id': 4, 'source_id': 8}
        with self.assertRaises(RunStopped):
            self.store.tool(foreign, Decision.model_validate(daily_plan()).action, {'tool': 'study_plan_create'})
        with self.assertRaises(HTTPException):
            self.store.tool(run, Decision.model_validate(daily_plan(ref='D999')).action, {'tool': 'study_plan_create'})
        self.assertEqual(self.store.tasks(42, 3), [])


if __name__ == '__main__': unittest.main()
