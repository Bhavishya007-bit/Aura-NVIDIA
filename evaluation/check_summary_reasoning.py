"""Reproduce reasoning-only truncation with real HTTP parsing and summary recovery."""
import json
import os
import unittest
from unittest.mock import Mock, patch

from backend.ai.llm import LLM, LLMResponseError
from backend.ai.answer_contract import CoverageDecision
from backend.ai.rag import RAG
from backend.ai.response_request import response_request, length_check
from backend.ai.source_aware import SourceAwareTutor
from evaluation.check_phase2 import FakeLLM
from evaluation.check_long_answers import DocumentRetriever, long_fixture


MODEL = 'nvidia/nemotron-3-super-120b-a12b'


def response(content='', finish='stop', reasoning=0, completion=8192):
    result = Mock(status_code=200)
    result.json.return_value = {'choices': [{'finish_reason': finish,
        'message': {'content': content}}], 'usage': {'prompt_tokens': 20635,
        'completion_tokens': completion, 'completion_tokens_details': {'reasoning_tokens': reasoning}}}
    return result


class SummaryReasoningChecks(unittest.TestCase):
    def client(self, model=MODEL):
        with patch.dict(os.environ, {'NEBIUS_API_KEY': 'fixture-key', 'NEBIUS_MODEL': model}, clear=True):
            return LLM()

    def tutor(self):
        rows, draft = long_fixture()
        rag = RAG(DocumentRetriever(rows), FakeLLM())
        tutor = SourceAwareTutor(rag)
        tutor.response_request = response_request('summarize the ppt in 2000 words')
        return tutor, rag._build_sources(rows), draft

    def run_summary(self, tutor, sources, client, overview=True):
        return tutor._source_answer('summarize the ppt in 2000 words', sources,
            CoverageDecision(status='unknown', reason='Fixture'), client,
            'Explain clearly.', overview=overview)

    def test_summary_sends_documented_effort_without_mutating_other_clients(self):
        base = self.client()
        coverage, deep = base.for_task('coverage'), base.for_task('deep')
        with patch.dict(os.environ, {}, clear=True), \
             patch('backend.ai.llm.requests.post', return_value=response('{"ok":true}')) as post:
            writer = deep.with_output_budget(8192).for_summary()
            self.assertEqual(writer.generate_json('fixture'), {'ok': True})
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['reasoning_effort'], 'none')
        self.assertEqual(payload['max_tokens'], 8192)
        self.assertEqual(payload['response_format'], {'type': 'json_object'})
        self.assertNotIn('extra_body', payload)
        self.assertTrue(all(c.reasoning_effort is None for c in (base, coverage, deep)))
        self.assertEqual(base.json_max_tokens, 4096)

    def test_unrecognized_models_keep_provider_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            writer = self.client('another/model').for_summary()
        with patch('backend.ai.llm.requests.post', return_value=response('{"ok":true}')) as post:
            writer.generate_json('fixture')
        self.assertNotIn('reasoning_effort', post.call_args.kwargs['json'])

    def test_operator_can_select_or_disable_effort_control(self):
        base = self.client()
        for effort, expected in [('low', 'low'), ('provider', None), ('', 'none')]:
            with self.subTest(effort=effort), patch.dict(os.environ,
                    {'NEBIUS_SUMMARY_REASONING_EFFORT': effort}, clear=True):
                self.assertEqual(base.for_summary().reasoning_effort, expected)
        with patch.dict(os.environ, {'NEBIUS_SUMMARY_REASONING_EFFORT': 'typo'}, clear=True):
            with self.assertRaises(ValueError):
                base.for_summary()

    def test_live_log_truncations_recover_once_with_measured_reserve(self):
        for reasoning in (7524, 8192):
            with self.subTest(reasoning=reasoning):
                tutor, sources, draft = self.tutor()
                client = self.client().with_output_budget(8192)
                with patch.dict(os.environ, {}, clear=True), patch('backend.ai.llm.requests.post',
                        side_effect=[response(finish='length', reasoning=reasoning),
                                     response(json.dumps(draft))]) as post:
                    section, validation = self.run_summary(tutor, sources, client)
                self.assertTrue(validation['valid'])
                self.assertTrue(validation['length_validation']['valid'])
                self.assertEqual(validation['length_validation']['actual_words'], 2000)
                self.assertEqual(section.kind, 'sourced')
                payloads = [call.kwargs['json'] for call in post.call_args_list]
                self.assertEqual(len(payloads), 2)
                self.assertEqual([p['max_tokens'] for p in payloads], [8192, 8192 + reasoning])
                self.assertTrue(all(p['reasoning_effort'] == 'none' for p in payloads))
                self.assertNotIn('previous_draft', json.loads(payloads[1]['messages'][-1]['content']))
                self.assertEqual(client.json_max_tokens, 8192)

    def test_whole_and_section_recovery_respect_caps_and_reject_truncated_json(self):
        tutor, sources, draft = self.tutor()
        client = self.client().with_output_budget(8192)
        truncated = response(json.dumps(draft), finish='length', reasoning=8192)
        with patch.dict(os.environ, {'AURA_MAX_ANSWER_TOKENS': '10000'}, clear=True), \
             patch('backend.ai.llm.requests.post', return_value=truncated) as post:
            section, validation = self.run_summary(tutor, sources, client)
        # Two whole-file attempts, four scoped attempts and two shared repairs.
        self.assertEqual(post.call_count, 8)
        payloads = [call.kwargs['json'] for call in post.call_args_list]
        self.assertEqual([row['max_tokens'] for row in payloads[:2]], [8192, 10000])
        self.assertTrue(all(row['max_tokens']==4096 for row in payloads[2:]))
        self.assertTrue(all(row['max_tokens']<=10000 for row in payloads))
        self.assertTrue(all('section_request' in json.loads(row['messages'][-1]['content']) for row in payloads[2:]))
        self.assertEqual(validation['response_mode'], 'extractive')
        self.assertFalse(length_check(section.text, tutor.response_request)['valid'])

    def test_missing_reasoning_usage_does_not_guess_extra_budget(self):
        tutor, sources, draft = self.tutor()
        first = response(finish='length')
        first.json.return_value.pop('usage')
        with patch.dict(os.environ, {}, clear=True), patch('backend.ai.llm.requests.post',
                side_effect=[first, response(json.dumps(draft))]) as post:
            section, validation = self.run_summary(tutor, sources, self.client().with_output_budget(8192))
        self.assertTrue(validation['valid'])
        self.assertEqual([c.kwargs['json']['max_tokens'] for c in post.call_args_list], [8192, 8192])

    def test_error_carries_only_bounded_recovery_metadata(self):
        with patch('backend.ai.llm.requests.post', return_value=response(finish='length', reasoning=7524)):
            with self.assertRaises(LLMResponseError) as error:
                self.client().with_output_budget(8192).generate_json('fixture', max_retries=1)
        self.assertEqual(error.exception.failure_code, 'output_truncated')
        self.assertEqual(error.exception.reasoning_tokens, 7524)
        self.assertEqual(error.exception.max_tokens, 8192)

    def test_brief_summary_keeps_provider_defaults(self):
        tutor, sources, draft = self.tutor()
        tutor.response_request = response_request('summarize the ppt')
        draft['sentences'] = draft['sentences'][:4]
        with patch('backend.ai.llm.requests.post', return_value=response(json.dumps(draft))) as post:
            section, validation = self.run_summary(tutor, sources, self.client())
        self.assertTrue(validation['valid'])
        self.assertNotIn('reasoning_effort', post.call_args.kwargs['json'])


if __name__ == '__main__':
    unittest.main()
