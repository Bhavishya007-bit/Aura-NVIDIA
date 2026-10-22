"""Reproduce reasoning-only verifier truncation without a hosted model call."""
import json
import os
import unittest
from unittest.mock import patch

from backend.ai.llm import LLM, generate_verification_json
from backend.ai.citation_grounding import CitationGrounding
from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor
from evaluation.check_summary_reasoning import MODEL, response
from evaluation.check_summary_supplements import SupplementLLM
from evaluation.check_long_answers import DocumentRetriever, HISTORY


class VerificationReasoningChecks(unittest.TestCase):
    def client(self, model=MODEL):
        with patch.dict(os.environ, {'NEBIUS_API_KEY': 'fixture-key',
                                    'NEBIUS_MODEL': model}, clear=True):
            return LLM()

    @staticmethod
    def verdicts(payload, *, unsupported=None):
        items = json.loads(payload['messages'][-1]['content'].split('BATCH_CLAIMS_DATA: ', 1)[1])
        return response(json.dumps({'results': [
            {'id': p['id'], 'supported': p['id'] != unsupported, 'reason': 'Controlled decision.'}
            for p in items]}))

    def test_verification_effort_is_scoped_to_judges(self):
        client = self.client()
        with patch.dict(os.environ, {}, clear=True), patch('backend.ai.llm.requests.post',
                return_value=response('{"supported":true}')) as post:
            generate_verification_json(client, 'check fixture')
        self.assertEqual(post.call_args.kwargs['json']['reasoning_effort'], 'none')
        self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 4096)
        self.assertIsNone(client.reasoning_effort)
        self.assertEqual(client.task, 'answer')
        self.assertEqual(client.for_task('deep').reasoning_effort, None)
        self.assertEqual(client.for_verification().task, 'verification')

    def test_model_defaults_and_operator_override(self):
        client = self.client('another/model')
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(client.for_verification().reasoning_effort)
        for effort, expected in [('provider', None), ('low', 'low'), ('', 'none')]:
            with patch.dict(os.environ, {'NEBIUS_VERIFICATION_REASONING_EFFORT': effort}, clear=True):
                self.assertEqual(self.client().for_verification().reasoning_effort, expected)
        with patch.dict(os.environ, {'NEBIUS_VERIFICATION_REASONING_EFFORT': 'typo'}, clear=True):
            with self.assertRaises(ValueError):
                self.client().for_verification()

    def test_only_truncated_batch_is_retried_and_negative_verdict_is_retained(self):
        seen = []
        def send(*args, **kwargs):
            payload = kwargs['json']
            items = json.loads(payload['messages'][-1]['content'].split('BATCH_CLAIMS_DATA: ', 1)[1])
            seen.append([p['id'] for p in items])
            if len(seen) == 2:
                return response(finish='length', reasoning=4096, completion=4096)
            return self.verdicts(payload, unsupported=16)
        client = self.client()
        points = [{'text': f'Teaching point {i}', 'citation_ids': [1]} for i in range(25)]
        with patch.dict(os.environ, {}, clear=True), patch('backend.ai.llm.requests.post', side_effect=send) as post:
            checked = CitationGrounding(client).verify_points(points, [{'content': 'Evidence to check.'}])
        self.assertEqual(seen, [list(range(12)), list(range(12, 24)), list(range(12, 24)), [24]])
        self.assertFalse(checked['valid'])
        self.assertEqual([p['supported'] for p in checked['results']], [i != 16 for i in range(25)])
        self.assertFalse(any(p.get('error') for p in checked['results']))
        self.assertEqual([c.kwargs['json']['max_tokens'] for c in post.call_args_list], [4096, 4096, 8192, 4096])
        self.assertTrue(all(c.kwargs['json']['reasoning_effort'] == 'none' for c in post.call_args_list))
        self.assertEqual(client.json_max_tokens, 4096)

    def test_repeated_truncation_fails_closed_with_operator_cap(self):
        # Even a complete-looking JSON object must be rejected when finish=length.
        partial = json.dumps({'results': [{'id': 0, 'supported': True}, {'id': 1, 'supported': True}]})
        with patch.dict(os.environ, {'AURA_MAX_ANSWER_TOKENS': '5000'}, clear=True), \
                patch('backend.ai.llm.requests.post', return_value=response(partial,
                    finish='length', reasoning=4096, completion=4096)) as post:
            checked = CitationGrounding(self.client()).verify_points([
                {'text': 'Point one', 'citation_ids': [1]}, {'text': 'Point two', 'citation_ids': [1]}],
                [{'content': 'Evidence.'}])
        self.assertEqual(post.call_count, 2)
        self.assertEqual(post.call_args.kwargs['json']['max_tokens'], 5000)
        self.assertFalse(checked['valid'])
        self.assertTrue(all(p.get('error') == 'verification_unavailable' for p in checked['results']))

    def test_invalid_decisions_are_not_retried_into_approval(self):
        malformed = [{"results": []}, {"results": [{'id': 0, 'supported': 'true'}]},
                     {"results": [{'id': 0, 'supported': True}, {'id': 0, 'supported': True}]}]
        for result in malformed:
            with self.subTest(result=result), patch('backend.ai.llm.requests.post',
                    return_value=response(json.dumps(result))) as post:
                checked = CitationGrounding(self.client())._verify_batch([
                    {'id': 0, 'claim': 'Point one', 'evidence': 'Evidence.'},
                    {'id': 1, 'claim': 'Point two', 'evidence': 'Evidence.'}])
            self.assertEqual(post.call_count, 1)
            self.assertTrue(all(p.get('error') == 'verification_unavailable' for p in checked.values()))

    def test_single_claim_and_intent_checks_use_bounded_verifier(self):
        for kind in ('claim', 'intent'):
            result = {'supported': False} if kind == 'claim' else {'answers_question': False}
            with self.subTest(kind=kind), patch('backend.ai.llm.requests.post', side_effect=[
                    response(finish='length', reasoning=4096, completion=4096),
                    response(json.dumps(result))]) as post:
                client = self.client()
                checked = (CitationGrounding(client).verify_claim('A claim', 'Source material')
                    if kind == 'claim' else RAG(DocumentRetriever([]), client)._question_relevance('Membranes?', 'Other topic'))
            self.assertEqual(post.call_count, 2)
            self.assertFalse(checked.get('supported', checked.get('valid')))
            self.assertNotIn('error', checked)
            self.assertNotIn('unavailable', checked)
            self.assertEqual(post.call_args.kwargs['json']['reasoning_effort'], 'none')

    def test_non_truncation_provider_error_is_not_retried(self):
        with patch('backend.ai.llm.requests.post', return_value=response('not JSON')) as post:
            checked = CitationGrounding(self.client()).verify_claim('A claim', 'Evidence.')
        self.assertEqual(post.call_count, 1)
        self.assertEqual(checked['error'], 'verification_unavailable')

    def test_recovered_verifier_allows_checked_summary_expansion(self):
        writer = SupplementLLM()
        rag = RAG(DocumentRetriever(writer.rows), writer)
        rag.citation_grounding = CitationGrounding(self.client())
        attempts = []
        def send(*args, **kwargs):
            payload = kwargs['json']
            attempts.append(payload)
            if len(attempts) == 2:
                return response(finish='length', reasoning=4096, completion=4096)
            return self.verdicts(payload)
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(CitationGrounding, '_literal_support', return_value=False), \
                patch('backend.ai.llm.requests.post', side_effect=send):
            result = SourceAwareTutor(rag).answer('in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertTrue(result['length_validation']['valid'], result['length_validation'])
        self.assertEqual(result['length_validation']['actual_words'], 2010)
        self.assertTrue(any(c[0] == 'supplement' for c in writer.calls))
        for point in writer.seed['sentences']:
            self.assertIn(point['text'], result['answer'])
        prompts = [p['messages'][-1]['content'] for p in attempts]
        self.assertEqual(prompts[1], prompts[2])
        self.assertNotEqual(prompts[0], prompts[1])


if __name__ == '__main__':
    unittest.main()
