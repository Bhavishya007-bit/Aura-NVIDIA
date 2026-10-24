"""Real HTTP serialization/parser checks; responses are authored, never live accuracy scores."""
import json
import os
import unittest
from unittest.mock import Mock, patch

from backend.ai.llm import LLM, LLMConnectionError, LLMResponseError
from backend.ai.response_request import response_request, word_count
from backend.ai.summary_background import background_lesson
from evaluation.check_background_review import ACCEPT
from evaluation.check_quality_profile import PROFILE, MODEL, prose
import evaluation.check_quality_profile as quality_fixtures
from evaluation.check_summary_reasoning import response


class BackgroundReasoningChecks(unittest.TestCase):
    def test_937_word_source_can_reach_2000_with_configured_background_effort_on_the_wire(self):
        source, background = prose(937), prose(1063)
        with patch.dict(os.environ, {**PROFILE, 'NEBIUS_API_KEY': 'PRIVATE_KEY'}, clear=True):
            base = LLM()
            client = base.for_task('answer')
            replies = [response(background), response(json.dumps(ACCEPT))]
            with patch('backend.ai.llm.requests.post', side_effect=replies) as post:
                result = background_lesson(client, 'Summarize the PDF in 2000 words', source,
                                           response_request('in 2000 words'))
        self.assertEqual(word_count(source) + word_count(result.text), 2000)
        self.assertFalse(result.verified)
        payloads = [call.kwargs['json'] for call in post.call_args_list]
        self.assertEqual(len(payloads), 2)
        self.assertTrue(all(p['model'] == MODEL and p['reasoning_effort'] == 'none' for p in payloads))
        self.assertNotIn('response_format', payloads[0])
        self.assertEqual(payloads[1]['max_tokens'], 2048)
        self.assertEqual(payloads[1]['response_format'], {'type': 'json_object'})
        self.assertIsNone(base.reasoning_effort)
        self.assertIsNone(client.reasoning_effort)

    def test_operator_reasoning_setting_is_used_without_changing_review_setting(self):
        for setting, expected in [('low', 'low'), ('provider', None)]:
            with self.subTest(setting=setting), patch.dict(os.environ,
                    {**PROFILE, 'NEBIUS_API_KEY': 'fixture-key', 'NEBIUS_SUMMARY_REASONING_EFFORT': setting}, clear=True):
                client = LLM()
                with patch('backend.ai.llm.requests.post', side_effect=[
                        response(prose(1063)), response(json.dumps(ACCEPT))]) as post:
                    background_lesson(client, 'in 2000 words', prose(937), response_request('in 2000 words'))
            payloads = [call.kwargs['json'] for call in post.call_args_list]
            self.assertEqual(payloads[0].get('reasoning_effort'), expected)
            self.assertEqual(payloads[1]['reasoning_effort'], 'none')

    def test_truncation_reuses_second_attempt_with_measured_budget_and_never_reviews_partial_text(self):
        with patch.dict(os.environ, {**PROFILE, 'NEBIUS_API_KEY': 'fixture-key',
                                    'NEBIUS_MAX_TOKENS': '4096', 'NEBIUS_JSON_MAX_TOKENS': '4096',
                                    'AURA_MAX_ANSWER_TOKENS': '7000'}, clear=True):
            client = LLM()
            with patch('backend.ai.llm.requests.post', side_effect=[
                    response('PRIVATE_PARTIAL', finish='length', reasoning=3000),
                    response(prose(1063)), response(json.dumps(ACCEPT))]) as post:
                result = background_lesson(client, 'in 2000 words', prose(937), response_request('in 2000 words'))
        payloads = [call.kwargs['json'] for call in post.call_args_list]
        self.assertEqual([p['max_tokens'] for p in payloads], [5120, 7000, 2048])
        self.assertNotIn('PRIVATE_PARTIAL', json.dumps(payloads) + result.text)
        feedback = json.loads(payloads[1]['messages'][-1]['content'])['feedback']
        self.assertEqual(feedback['failure_code'], 'output_truncated')
        self.assertFalse(result.verified)

    def test_repeated_truncation_stops_after_two_writes_and_publishes_nothing(self):
        with patch.dict(os.environ, {**PROFILE, 'NEBIUS_API_KEY': 'fixture-key'}, clear=True):
            with patch('backend.ai.llm.requests.post', return_value=response('PARTIAL', finish='length')) as post:
                result = background_lesson(LLM(), 'in 2000 words', prose(937), response_request('in 2000 words'))
        self.assertIsNone(result)
        self.assertEqual(post.call_count, 2)
        self.assertTrue(all('response_format' not in call.kwargs['json'] for call in post.call_args_list))

    def test_review_failure_never_restarts_background_generation(self):
        client = Mock()
        client.with_output_budget.return_value = client
        client.generate.return_value = prose(1063)
        client.generate_json.side_effect = LLMResponseError('output_truncated', max_tokens=2048)
        with self.assertLogs('backend.ai.summary_background', 'WARNING') as logs:
            result = background_lesson(client, 'in 2000 words', prose(937), response_request('in 2000 words'))
        self.assertIsNone(result)
        self.assertEqual(client.generate.call_count, 1)
        self.assertIn('stage=review failure_code=output_truncated', '\n'.join(logs.output))

    def test_safe_stage_diagnostics_do_not_log_error_bodies_or_untrusted_codes(self):
        for error in (RuntimeError('PRIVATE_BODY'),
                      LLMConnectionError(timed_out=True),
                      LLMResponseError('PRIVATE_CODE', max_tokens=4096)):
            with self.subTest(error=type(error).__name__):
                client = Mock(); client.with_output_budget.return_value = client
                client.generate.side_effect = error
                with self.assertLogs('backend.ai.summary_background', 'WARNING') as logs:
                    result = background_lesson(client, 'PRIVATE_QUESTION in 2000 words', prose(937),
                                               response_request('in 2000 words'))
                self.assertIsNone(result)
                self.assertEqual(client.generate.call_count, 1)
                self.assertIn('stage=generation failure_code=', '\n'.join(logs.output))
                self.assertNotIn('PRIVATE', '\n'.join(logs.output))

    def test_invalid_background_configuration_preserves_source_instead_of_raising(self):
        with patch.dict(os.environ, {**PROFILE, 'NEBIUS_API_KEY': 'fixture-key',
                                    'NEBIUS_SUMMARY_REASONING_EFFORT': 'PRIVATE_INVALID'}, clear=True):
            with patch('backend.ai.llm.requests.post') as post, \
                 self.assertLogs('backend.ai.summary_background', 'WARNING') as logs:
                result = background_lesson(LLM(), 'in 2000 words', prose(937), response_request('in 2000 words'))
        self.assertIsNone(result)
        post.assert_not_called()
        self.assertIn('stage=configuration failure_code=invalid_configuration', '\n'.join(logs.output))
        self.assertNotIn('PRIVATE', '\n'.join(logs.output))

    def test_disabled_and_source_only_policies_have_distinct_diagnostics_and_no_background_calls(self):
        fixture = quality_fixtures.BackgroundChecks()
        for question, enabled, reason in [('in 2000 words', False, 'disabled'),
                ('Summarize the PPT in 2000 words using only my material.', True, 'source_only')]:
            with self.subTest(reason=reason), self.assertLogs('backend.ai.source_aware', 'INFO') as logs:
                result, client = fixture.answer(question=question, enabled=enabled)
            self.assertFalse(client.background_calls)
            self.assertEqual([s['kind'] for s in result['sections']], ['sourced'])
            self.assertIn('summary_background=skipped reason=' + reason, '\n'.join(logs.output))


if __name__ == '__main__':
    unittest.main()
