"""Synthetic checks for local profile updates and honestly labelled background."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from dotenv import dotenv_values
from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor
from backend.ai.summary_background import background_lesson
from backend.ai.response_request import response_request, word_count
from backend.ai.llm import LLM
from evaluation.check_summary_supplements import SupplementLLM
from evaluation.check_long_answers import DocumentRetriever, HISTORY
from scripts.configure_model_quality import apply_profile, smoke_check, PROFILE, MODEL
from scripts import configure_model_quality as quality


def prose(words):
    # Count fixture, not a teaching-quality benchmark or model judgment.
    return ' '.join(f'background{i}' for i in range(words)) + '.'


class ProfileChecks(unittest.TestCase):
    def test_failed_cli_smoke_leaves_working_configuration_untouched(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'backend').mkdir()
            path = root / 'backend' / '.env'
            original = 'NEBIUS_MODEL=previous-working-model\nDB_PASSWORD=synthetic-db-value\n'
            path.write_text(original)
            with patch.object(quality, '__file__', str(root / 'scripts' / 'configure_model_quality.py')), \
                 patch('sys.argv', ['configure_model_quality.py', '--apply', '--smoke']), \
                 patch.object(quality, 'smoke_check', return_value=False):
                with self.assertRaises(SystemExit) as failure:
                    quality.main()
            self.assertEqual(failure.exception.code, 1)
            self.assertEqual(path.read_text(), original)

    def test_profile_routes_text_roles_to_ultra_with_the_larger_writing_allowance(self):
        with patch.dict(os.environ, {**PROFILE, 'NEBIUS_API_KEY': 'synthetic-key'}, clear=True):
            client = LLM()
            self.assertEqual(client.max_tokens, 16384)
            self.assertEqual(client.json_max_tokens, 16384)
            for task in ('coverage', 'answer', 'deep'):
                self.assertEqual(client.for_task(task).model_name, MODEL)
            self.assertEqual(client.for_summary().reasoning_effort, 'none')
            self.assertEqual(client.for_verification().reasoning_effort, 'none')
            self.assertEqual(client.with_output_budget(50000).max_tokens, 32768)

    def test_profile_preserves_secrets_database_comments_and_unknown_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            secret = 'NEBIUS_API_KEY="synthetic-secret"\nDB_PASSWORD="synthetic-db-value"\n# Keep this comment\nCUSTOM_SETTING=yes\n'
            path.write_text(secret + 'NEBIUS_MODEL=old\nexport NEBIUS_MODEL=duplicate\n')
            apply_profile(path)
            result = path.read_text()
            self.assertIn(secret, result)
            self.assertNotIn('=old', result)
            self.assertNotIn('=duplicate', result)
            self.assertEqual(dict(dotenv_values(path)), {**dict(dotenv_values(stream=__import__('io').StringIO(secret))), **PROFILE})
            apply_profile(path)
            self.assertEqual(path.read_text(), result)
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_smoke_uses_one_small_synthetic_request_and_never_prints_credentials(self):
        reply = Mock(status_code=200)
        reply.json.return_value = {'choices': [{'finish_reason': 'stop', 'message': {'content': '{"ok":true}'}}]}
        with patch.dict(os.environ, {'NEBIUS_API_KEY': 'synthetic-secret'}, clear=True), \
             patch('scripts.configure_model_quality.requests.post', return_value=reply) as post, patch('builtins.print') as output:
            self.assertTrue(smoke_check(Path('/does-not-exist')))
        self.assertEqual(post.call_count, 1)
        payload = post.call_args.kwargs['json']
        self.assertEqual(payload['model'], MODEL)
        self.assertEqual(payload['reasoning_effort'], 'none')
        self.assertEqual(payload['max_tokens'], 256)
        self.assertNotIn('synthetic-secret', str(output.call_args_list))

    def test_smoke_failure_is_redacted_and_does_not_downgrade(self):
        reply = Mock(status_code=403)
        with patch.dict(os.environ, {'NEBIUS_API_KEY': 'synthetic-secret'}, clear=True), \
             patch('scripts.configure_model_quality.requests.post', return_value=reply) as post, patch('builtins.print') as output:
            self.assertFalse(smoke_check(Path('/does-not-exist')))
        self.assertEqual(post.call_count, 1)
        self.assertIn('HTTP 403', str(output.call_args_list))
        self.assertNotIn('synthetic-secret', str(output.call_args_list))
        reply.json.assert_not_called()


class BackgroundLLM(SupplementLLM):
    def __init__(self, background=None):
        super().__init__(repeat=True)
        self.background = background or prose(890)
        self.background_calls = []

    def generate(self, data, max_retries=2, system_prompt=None):
        if 'GENERAL BACKGROUND lesson' in (system_prompt or ''):
            self.background_calls.append(json.loads(data))
            if isinstance(self.background, Exception):
                raise self.background
            return self.background
        return super().generate(data, max_retries, system_prompt)


class BackgroundChecks(unittest.TestCase):
    def answer(self, question='in 2000 words', background=None, enabled=True):
        llm = BackgroundLLM(background)
        with patch.dict(os.environ, {'AURA_SUMMARY_BACKGROUND': 'true' if enabled else 'false'}):
            result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
                question, course_id=3, source_id=7, history=HISTORY)
        return result, llm

    def test_quality_profile_can_complete_the_lesson_with_separate_unverified_background(self):
        result, llm = self.answer()
        self.assertEqual(result['length_validation']['actual_words'], 2000)
        self.assertTrue(result['length_validation']['valid'])
        self.assertEqual([s['kind'] for s in result['sections']], ['sourced', 'beyond'])
        self.assertTrue(result['sections'][0]['verified'])
        self.assertFalse(result['sections'][1]['verified'])
        self.assertEqual(result['sections'][1]['citation_ids'], [])
        self.assertFalse(result['citation_validation']['background_verified'])
        self.assertEqual(len(llm.background_calls), 1)
        self.assertEqual(llm.background_calls[0]['response_request']['target_words'], 890)
        self.assertNotIn('[1]', llm.background_calls[0]['checked_overview'])
        self.assertIn('not web verified', result['answer'])

    def test_explicit_source_only_request_never_adds_general_background(self):
        for policy in ('using only my material', 'based only on my slides',
                       'with no outside knowledge', 'without any background explanation'):
            with self.subTest(policy=policy):
                result, llm = self.answer('Summarize the PPT in 2000 words ' + policy + '.')
                self.assertFalse(llm.background_calls)
                self.assertEqual([s['kind'] for s in result['sections']], ['sourced'])
                self.assertFalse(result['length_validation']['valid'])

    def test_disabled_policy_keeps_the_existing_source_only_overview(self):
        result, llm = self.answer(enabled=False)
        self.assertFalse(llm.background_calls)
        self.assertEqual(result['length_validation']['actual_words'], 1110)

    def test_fake_document_citations_in_background_are_rejected(self):
        result, llm = self.answer(background='Invented slide finding [999].')
        self.assertEqual(len(llm.background_calls), 1)
        self.assertEqual([s['kind'] for s in result['sections']], ['sourced'])
        self.assertNotIn('Invented slide finding', result['answer'])

    def test_connection_loss_keeps_the_checked_answer_without_retrying(self):
        result, llm = self.answer(background=RuntimeError('PRIVATE_TRANSPORT_DETAILS'))
        self.assertEqual(len(llm.background_calls), 1)
        self.assertEqual(result['length_validation']['actual_words'], 1110)
        self.assertNotIn('PRIVATE', result['answer'])

    def test_one_length_revision_can_replace_a_short_background_without_appending(self):
        client = Mock(); client.with_output_budget.return_value = client
        client.generate.side_effect = [prose(100), prose(200)]
        section = background_lesson(client, 'in 2000 words', prose(1800), response_request('in 2000 words'))
        self.assertEqual(word_count(section.text), 200)
        self.assertEqual(client.generate.call_count, 2)
        self.assertFalse(section.verified)
        self.assertIn('prior_draft', json.loads(client.generate.call_args.args[0]))
