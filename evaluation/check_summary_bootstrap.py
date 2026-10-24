"""Recovery from the reported excerpt-only path, with real source validators.

Model decisions are controlled. Passing these tests does not measure live
Nemotron quality, OCR accuracy or human judge agreement.
"""
import json
import unittest
from unittest.mock import patch

from backend.ai.llm import LLMConnectionError, LLMResponseError
from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor
from evaluation.check_long_answers import DocumentRetriever, HISTORY
from evaluation.check_sectioned_summaries import SectionLLM


class BootstrapLLM(SectionLLM):
    def __init__(self, failure='empty', section_mode='normal'):
        super().__init__(section_mode)
        self.failure = failure

    def generate_json(self, data, max_retries=2, system_prompt=None):
        if 'SELECTED uploaded material' in (system_prompt or ''):
            payload = json.loads(data)
            if 'section_request' not in payload:
                self.calls.append(('whole', payload))
                if self.failure == 'truncated':
                    raise LLMResponseError('output_truncated', max_tokens=8192, reasoning_tokens=0)
                if self.failure == 'connection':
                    raise LLMConnectionError(timed_out=True)
                if self.failure == 'connection_after_seed':
                    if len([row for row in self.calls if row[0]=='whole']) == 1:
                        return {'sentences': self.full['sentences'][:8]}
                    raise LLMConnectionError()
                if self.failure == 'unavailable':
                    raise RuntimeError('provider unavailable')
                if self.failure == 'unsupported':
                    return {'sentences': [{'text': 'The membrane contains pure gold', 'citation_ids': [1]}]}
                return {'sentences': []}
            if self.failure == 'section_connection':
                self.calls.append(('part', payload))
                raise LLMConnectionError()
        return super().generate_json(data, max_retries, system_prompt)


class SummaryBootstrap(unittest.TestCase):
    def run_tutor(self, failure='empty', section_mode='normal'):
        llm = BootstrapLLM(failure, section_mode)
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        return result, llm

    def test_recovery_can_start_when_long_source_lines_have_no_short_excerpt(self):
        llm = BootstrapLLM()
        for row in llm.rows:
            row.chunk.content = row.chunk.content.replace('\n', ' ') * 3
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertTrue(result['length_validation']['valid'])
        self.assertEqual(result['length_validation']['actual_words'], 2000)
        self.assertEqual(result['citation_validation']['source_validation']['stage'], 'summary_section_expansion')

    def test_two_invalid_whole_drafts_can_start_verified_sections_without_a_seed(self):
        for failure in ('empty', 'truncated', 'unsupported'):
            with self.subTest(failure=failure):
                result, llm = self.run_tutor(failure)
                self.assertTrue(result['length_validation']['valid'], result['length_validation'])
                self.assertEqual(result['length_validation']['actual_words'], 2000)
                self.assertEqual(result['citation_validation']['source_validation']['stage'], 'summary_section_expansion')
                self.assertEqual(len([row for row in llm.calls if row[0]=='whole']), 2)
                parts = [row[1] for row in llm.calls if row[0]=='part']
                self.assertEqual(len(parts), 4)
                self.assertEqual(parts[0]['already_explained'], [])
                self.assertCountEqual([source['text'] for part in parts for source in part['passages']],
                                      [row.chunk.content for row in llm.rows])
                self.assertTrue(all(section['kind']=='sourced' for section in result['sections']))
                self.assertNotIn('pure gold', result['answer'])
                self.assertNotEqual(result['citation_validation']['response_mode'], 'extractive')

    def test_empty_section_recovery_is_bounded_and_keeps_honest_source_excerpts(self):
        result, llm = self.run_tutor('empty', 'empty')
        self.assertEqual(len([row for row in llm.calls if row[0]=='part']), 6)
        self.assertEqual(result['citation_validation']['response_mode'], 'extractive')
        self.assertFalse(result['length_validation']['valid'])
        self.assertIn('requested target was approximately 2000', result['answer'])

    def test_bootstrap_does_not_relax_section_citation_boundaries(self):
        result, llm = self.run_tutor('empty', 'foreign')
        self.assertTrue(result['length_validation']['valid'])
        self.assertEqual(llm.part_attempts[1], 2)
        self.assertNotIn('foreign section source', result['answer'])

    def test_unavailable_verifier_stops_bootstrap_without_publishing_new_prose(self):
        with patch.object(RAG, '_validate_answer', return_value={'valid':False,'stage':'verification_unavailable'}):
            result, llm = self.run_tutor()
        self.assertEqual(len([row for row in llm.calls if row[0]=='part']), 1)
        self.assertEqual(result['citation_validation']['response_mode'], 'extractive')
        self.assertFalse(result['length_validation']['valid'])

    def test_connection_or_unknown_provider_failure_does_not_start_more_writing(self):
        for failure in ('connection', 'unavailable'):
            with self.subTest(failure=failure):
                result, llm = self.run_tutor(failure)
                self.assertEqual(len([row for row in llm.calls if row[0]=='whole']), 2)
                self.assertEqual(len([row for row in llm.calls if row[0]=='part']), 0)
                self.assertEqual(result['citation_validation']['response_mode'], 'extractive')

    def test_connection_loss_during_section_recovery_stops_after_one_attempt(self):
        result, llm = self.run_tutor('section_connection')
        self.assertEqual(len([row for row in llm.calls if row[0]=='part']), 1)
        self.assertEqual(result['citation_validation']['response_mode'], 'extractive')
        self.assertFalse(result['length_validation']['valid'])

    def test_connection_loss_after_a_checked_draft_keeps_it_without_more_calls(self):
        with self.assertLogs('backend.ai.source_aware', 'WARNING') as logs:
            result, llm = self.run_tutor('connection_after_seed')
        self.assertEqual(len([row for row in llm.calls if row[0]=='part']), 0)
        self.assertEqual(result['length_validation']['actual_words'], 200)
        self.assertFalse(result['length_validation']['valid'])
        self.assertNotEqual(result['citation_validation']['response_mode'], 'extractive')
        self.assertIn('failure_code=model_connection_failed', '\n'.join(logs.output))

