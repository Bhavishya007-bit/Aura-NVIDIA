"""Topic planning, atomic rewrites and repeat rejection; model judgments are fixtures."""
import copy
import json
import unittest
from unittest.mock import Mock, patch

from backend.ai.llm import LLMConnectionError
from backend.ai.long_summary import expand_summary
from backend.ai.rag import RAG
from backend.ai.response_request import response_request
from backend.ai.source_aware import SourceAwareTutor, _schema_errors
from backend.ai.summary_outline import summary_plan, topic_plan
from evaluation.check_long_answers import DocumentRetriever, HISTORY
from evaluation.check_phase2 import chunk
from evaluation.check_sectioned_summaries import SectionLLM


class TopicOutlineChecks(unittest.TestCase):
    def setUp(self):
        # Independently authored test material, not extracted user slides.
        self.sources = [{'source_id': 7, 'page': n, 'content': text} for n, text in enumerate([
            'A dictionary associates keys with values.',
            'An array provides index-based access.',
            'A hash function maps a key to an array index.',
            'Different keys may collide at one index.',
            'A dictionary associates keys with values: another representation.',
            'Open addressing probes slots in the array.',
            'Separate chaining stores colliding entries in a bucket list.',
            'A key needs a stable hash for lookup.'], 1)]
        self.sources += [{**self.sources[0], 'content': 'A second diagram of the first page.'}]
        self.fallback = summary_plan(self.sources, 2000)
        self.raw = {'sections': [
            {'title': title, 'focus': focus, 'location_ids': ids} for title, focus, ids in [
                ('Dictionary interface', 'Explain key-value access once.', [1, 5]),
                ('Array foundation', 'Explain index-based storage.', [2]),
                ('Index mapping', 'Explain hashing and possible collisions.', [3, 4]),
                ('Open addressing', 'Explain the probe process.', [6]),
                ('Separate chaining', 'Explain the bucket process and contrast it with probing.', [7]),
                ('Stable keys', 'Explain why changing a hash breaks lookup.', [8])]]}

    def client(self, raw=None):
        client = Mock()
        client.with_output_budget.return_value = client
        client.generate_json.return_value = self.raw if raw is None else raw
        return client

    def test_nonadjacent_repeated_topics_group_together_without_losing_page_representations(self):
        client = self.client()
        plan = topic_plan(client, self.sources, 'summarize the PDF in 2000 words', self.fallback)
        self.assertEqual(plan[0]['source_ids'], [1, 9, 5])
        self.assertEqual(plan[0]['title'], 'Dictionary interface')
        self.assertEqual(sum(part['target_words'] for part in plan), 2000)
        self.assertCountEqual([n for part in plan for n in part['source_ids']], range(1, 10))
        self.assertEqual(client.generate_json.call_count, 1)
        self.assertEqual(client.generate_json.call_args.kwargs['max_retries'], 1)
        self.assertEqual(len(json.loads(client.generate_json.call_args.args[0])['locations']), 8)

    def test_bad_partitions_and_untrusted_extra_fields_use_the_safe_fallback(self):
        variants = []
        for ids in ([1, 5, 1], [1], [1, 99], [True, 5], ['1', 5]):
            raw = copy.deepcopy(self.raw); raw['sections'][0]['location_ids'] = ids; variants.append(raw)
        raw = copy.deepcopy(self.raw); raw['sections'][1]['title'] = raw['sections'][0]['title']; variants.append(raw)
        raw = copy.deepcopy(self.raw); raw['sections'][0]['target_words'] = 99999; variants.append(raw)
        for raw in variants:
            with self.subTest(raw=raw), self.assertLogs('backend.ai.summary_outline', 'WARNING'):
                self.assertEqual(topic_plan(self.client(raw), self.sources, 'summarize', self.fallback), self.fallback)

    def test_invalid_outline_does_not_log_document_or_model_text(self):
        client = self.client({'PRIVATE_MODEL': 'PRIVATE_DOCUMENT'})
        with self.assertLogs('backend.ai.summary_outline', 'WARNING') as logs:
            topic_plan(client, self.sources, 'summarize', self.fallback)
        self.assertNotIn('PRIVATE', '\n'.join(logs.output))

    def test_outline_connection_loss_stops_before_section_writing(self):
        client = self.client()
        client.generate_json.side_effect = LLMConnectionError()
        with self.assertLogs('backend.ai.long_summary', 'WARNING'):
            result = expand_summary(Mock(), client, self.sources, 'summarize',
                response_request('in 2000 words'), {}, _schema_errors)
        self.assertIsNone(result)
        self.assertEqual(client.generate_json.call_count, 1)

    def test_single_location_does_not_trigger_an_outline_or_unbounded_expansion(self):
        client = self.client()
        result = expand_summary(Mock(), client, self.sources[:1], 'summarize',
            response_request('in 2000 words'), {}, _schema_errors)
        self.assertIsNone(result)
        client.generate_json.assert_not_called()


class RewriteChecks(unittest.TestCase):
    def test_checked_overview_is_not_prepended_to_the_rewritten_lesson(self):
        class OverviewLLM(SectionLLM):
            def generate_json(self, data, max_retries=2, system_prompt=None):
                if ('SELECTED uploaded material' in (system_prompt or '')
                        and 'section_request' not in json.loads(data)):
                    return {'sentences': [{'text': 'This presentation introduces membrane observations', 'citation_ids': [1]}]}
                return super().generate_json(data, max_retries, system_prompt)
        llm = OverviewLLM()
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertEqual(result['length_validation']['actual_words'], 2000)
        self.assertNotIn('This presentation introduces membrane observations', result['answer'])
        parts = [row[1] for row in llm.calls if row[0] == 'part']
        self.assertEqual(parts[0]['already_explained'], [])
        self.assertTrue(all(part['section_request']['mode'] == 'complete_replacement' for part in parts))
        self.assertEqual(len(parts[0]['lesson_outline']), 6)

    def test_short_section_is_rewritten_instead_of_appended(self):
        class ShortLLM(SectionLLM):
            def generate_json(self, data, max_retries=2, system_prompt=None):
                result = super().generate_json(data, max_retries, system_prompt)
                if 'SELECTED uploaded material' in (system_prompt or ''):
                    payload = json.loads(data)
                    if payload.get('section_request', {}).get('index') == 2 and self.part_attempts[2] == 1:
                        return {'sentences': result['sentences'][:1]}
                return result
        llm = ShortLLM()
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertEqual(result['length_validation']['actual_words'], 2000)
        self.assertEqual(llm.part_attempts[2], 2)
        calls = [row[1] for row in llm.calls if row[0] == 'part' and row[1]['section_request']['index'] == 2]
        first = calls[1]['previous_draft']['sentences'][0]['text']
        self.assertEqual(result['answer'].count(first), 1)
        self.assertNotIn(first, [point['text'] for point in calls[1]['already_explained']])
        self.assertIn('ENTIRE', calls[1]['feedback']['instruction'])

    def test_repetition_rejection_happens_before_factual_support_can_publish_it(self):
        llm = Mock()
        llm.generate_json.return_value = {'answers_question': False, 'reason': 'Only repeats a completed definition.'}
        points = [{'text': 'A dictionary maps keys to values', 'citation_ids': [1]}]
        from backend.ai.summary_answer import SummaryDraft
        text = SummaryDraft.model_validate({'sentences': points}).render(1)
        rag = RAG(DocumentRetriever([]), llm)
        with patch.object(rag.citation_grounding, 'verify_points') as support:
            result = rag._validate_answer(text, [{'content': 'A dictionary maps keys to values.'}],
                'summarize in 2000 words', structured_points=points,
                intent_context={'scope': 'selected_material_section',
                    'section_question': 'Separate chaining: explain the bucket insertion process.',
                    'already_explained': [{'text': 'A dictionary associates a value with each key.'}]})
        self.assertEqual(result['stage'], 'question_relevance')
        self.assertFalse(result['valid'])
        support.assert_not_called()
        self.assertIn('only paraphrases completed sections', llm.generate_json.call_args.args[0])

    def test_worse_revision_keeps_the_previous_checked_section(self):
        llm = SectionLLM()
        calls = []
        original = llm.generate_json
        def answer(data, max_retries=2, system_prompt=None):
            result = original(data, max_retries, system_prompt)
            if 'SELECTED uploaded material' in (system_prompt or '') and 'section_request' in json.loads(data):
                payload = json.loads(data); calls.append(payload)
                # Force all sections short, then return empty repairs.
                return {'sentences': [] if 'feedback' in payload else result['sentences'][:1]}
            return result
        llm.generate_json = answer
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertFalse(result['length_validation']['valid'])
        self.assertLessEqual(len(calls), 8)
        # The shorter rewrite never replaces the caller's longer checked overview.
        self.assertEqual(result['length_validation']['actual_words'], 200)


class RetrievalDedupChecks(unittest.TestCase):
    def test_same_page_pipeline_header_duplicates_are_removed_but_distinct_evidence_stays(self):
        native = chunk('A hash table maps a key to an array index.', id='a')
        native.chunk.page = 3
        wrapped = chunk('Page 3 recognized text\nA hash table maps a key to an array index.', id='b')
        wrapped.chunk.page = 3
        other_page = chunk(native.chunk.content, id='c'); other_page.chunk.page = 4
        uncertain = chunk('Model interpretation (not independently verified): a hash table diagram.', id='d')
        uncertain.chunk.page = 3
        tutor = SourceAwareTutor(RAG(DocumentRetriever([]), SectionLLM()))
        merged = tutor._merge([native], [wrapped, other_page, uncertain])
        self.assertEqual([row.chunk.chunk_id for row in merged], ['a', 'c', 'd'])
        self.assertIn('not independently verified', merged[-1].chunk.content)
