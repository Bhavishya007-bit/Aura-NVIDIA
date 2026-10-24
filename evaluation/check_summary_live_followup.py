"""Controlled regressions for the successful-length run's remaining integrity gaps."""
import copy
import json
import os
import unittest
from unittest.mock import Mock, patch

from backend.ai.answer_contract import AnswerSection, has_noncanonical_citations
from backend.ai.background_review import review_background
from backend.ai.llm import LLMResponseError
from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor
from backend.ai.summary_answer import SummaryDraft, SummaryDraftError, recover_summary
from backend.ai.summary_outline import summary_plan, topic_plan
from evaluation.check_background_review import REJECT
from evaluation.check_phase2 import FakeLLM, Retriever, verdict
from evaluation.check_quality_profile import prose
from evaluation.check_summary_recovery import SummaryLLM


class GroupedReferenceChecks(unittest.TestCase):
    def test_numeric_reference_groups_never_escape_via_structured_text(self):
        for marker in ('[1,2]', '[1, 2]', '[1;2]', '[1-3]', '【1,2】', '[999,1000]'):
            with self.subTest(marker=marker):
                draft = SummaryDraft.model_validate({'sentences': [
                    {'text': 'A material statement ' + marker, 'citation_ids': [1, 2]}]})
                with self.assertRaises(SummaryDraftError) as failure:
                    draft.render(2)
                self.assertEqual(failure.exception.failure_code, 'noncanonical_citation_marker')
                self.assertEqual(failure.exception.feedback['sentence_index'], 0)

    def test_background_cannot_smuggle_grouped_document_references(self):
        with self.assertRaises(ValueError):
            AnswerSection(kind='beyond', text='A model claim [1,2].',
                          provenance='model_knowledge', verified=False)
        with self.assertRaises(ValueError):
            AnswerSection(kind='sourced', text='A claim [1,2] [1].',
                          provenance='uploaded_material', verified=True, citation_ids=[1])

    def test_numeric_arrays_inside_code_are_not_rewritten_as_reference_ids(self):
        for text in ('The example uses `values = [1, 2]`.',
                     'The example uses ``[1,2]``.',
                     'An example:\n```python\nvalues = [1, 2]\n```',
                     'An example:\n~~~python\nvalues = [1, 2]\n~~~'):
            with self.subTest(text=text):
                self.assertFalse(has_noncanonical_citations(text))
                draft = SummaryDraft.model_validate({'sentences': [{'text': text, 'citation_ids': [1]}]})
                self.assertIn('[1, 2]' if '[1, 2]' in text else '[1,2]', draft.render(1))
        self.assertTrue(has_noncanonical_citations('An example `values = [1,2]` with claim [7,8].'))

    def test_bad_grouped_markers_in_recovery_are_not_published_as_checked_claims(self):
        sources = [{'content': 'An ambiguous numeric reference appears here [7,8].', 'source_id': 7, 'page': 1}]
        checks = [{'grounding_validation': {'results': [
            {'claim': 'An ambiguous reference [7,8]', 'supported': True, 'citations': [1]}]}}]
        section, _ = recover_summary(sources, checks, 'summarize the PDF')
        self.assertIsNone(section)

    def test_model_repairs_grouped_reference_before_any_source_approval(self):
        class RepairLLM(SummaryLLM):
            def generate_json(self, data, max_retries=2, system_prompt=None):
                result = super().generate_json(data, max_retries, system_prompt)
                if 'SELECTED uploaded material' in (system_prompt or ''):
                    payload = json.loads(data)
                    if 'feedback' not in payload:
                        return {'sentences': [{'text': 'The membrane is a lipid bilayer [1,2]', 'citation_ids': [1]}]}
                return result
        client = RepairLLM()
        result = SourceAwareTutor(RAG(Retriever(), client)).answer('summarize the PDF', course_id=3, source_id=7)
        self.assertNotIn('[1,2]', result['answer'])
        self.assertTrue(result['citation_validation']['valid'])
        calls = [json.loads(c[-1]) for c in client.calls if c[1] == 'summary_json']
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]['feedback']['draft_error']['code'], 'noncanonical_citation_marker')


class StructuralRepairChecks(unittest.TestCase):
    def outline(self):
        sources = [{'source_id': 7, 'page': n, 'content': f'A distinct authored topic {n}.'} for n in range(1, 7)]
        good = {'sections': [{'title': f'Topic {n}', 'focus': 'Explain this assigned topic.', 'location_ids': [n]}
                             for n in range(1, 7)]}
        bad = copy.deepcopy(good); bad['sections'][0]['location_ids'] = [1, 1]
        client = Mock(); client.with_output_budget.return_value = client
        return sources, summary_plan(sources, 2000), good, bad, client

    def test_invalid_partition_gets_one_scoped_repair_with_explicit_location_schema(self):
        sources, fallback, good, bad, client = self.outline()
        client.generate_json.side_effect = [bad, good]
        result = topic_plan(client, sources, 'summarize', fallback)
        self.assertEqual([p['source_ids'] for p in result], [[n] for n in range(1, 7)])
        self.assertEqual(client.generate_json.call_count, 2)
        payload = json.loads(client.generate_json.call_args.args[0])
        self.assertEqual(payload['partition_feedback']['allowed_location_ids'], list(range(1, 7)))
        schema = payload['output_schema']
        self.assertEqual(schema['properties']['sections']['maxItems'], 6)
        self.assertEqual(schema['$defs']['OutlineSection']['properties']['location_ids']['items']['enum'], list(range(1, 7)))

    def test_repeated_invalid_partition_falls_back_without_losing_locations(self):
        sources, fallback, _, bad, client = self.outline()
        client.generate_json.return_value = bad
        self.assertEqual(topic_plan(client, sources, 'summarize', fallback), fallback)
        self.assertEqual(client.generate_json.call_count, 2)

    def test_provider_failure_does_not_trigger_partition_repair(self):
        sources, fallback, _, _, client = self.outline()
        client.generate_json.side_effect = LLMResponseError('output_truncated', max_tokens=4096)
        self.assertEqual(topic_plan(client, sources, 'summarize', fallback), fallback)
        self.assertEqual(client.generate_json.call_count, 1)

    def test_too_many_coverage_parts_are_regrouped_by_model_not_silently_truncated(self):
        rows = [{'content': f'Authored evidence {n}.'} for n in range(39)]
        oversized = verdict(covered_parts=[{'part': f'Topic {n}', 'citation_ids': [n+1]} for n in range(39)])
        grouped = verdict(covered_parts=[{'part': 'Document overview', 'citation_ids': list(range(1, 40))}])
        client = FakeLLM(decisions=[oversized, grouped])
        result = SourceAwareTutor(RAG(Retriever(), client))._judge('summarize the PDF', rows)
        self.assertEqual(result.status, 'fully_covered')
        self.assertEqual(len(result.covered_parts[0].citation_ids), 39)
        self.assertEqual(len(client.calls), 2)
        self.assertEqual(json.loads(client.calls[1][-1])['format_feedback']['failure_code'], 'part_limit')

    def test_repeated_part_overflow_remains_unknown_and_valid_negatives_are_not_rerolled(self):
        oversized = verdict(covered_parts=[{'part': f'Topic {n}', 'citation_ids': [1]} for n in range(13)])
        for data, expected, count in ((oversized, 'unknown', 2), (verdict('not_covered'), 'not_covered', 1)):
            with self.subTest(expected=expected):
                client = FakeLLM(decisions=[data])
                result = SourceAwareTutor(RAG(Retriever(), client))._judge('summarize', [{'content': 'Evidence.'}])
                self.assertEqual(result.status, expected)
                self.assertEqual(len(client.calls), count)


class CompletenessAndReviewChecks(unittest.TestCase):
    def test_background_length_success_does_not_hide_an_omitted_source_section(self):
        source = AnswerSection(kind='sourced', text=prose(1603) + ' [1]', provenance='uploaded_material',
                               verified=True, citation_ids=[1])
        background = AnswerSection(kind='beyond', text=prose(521), provenance='model_knowledge', verified=False)
        tutor = SourceAwareTutor(RAG(Retriever(), SummaryLLM()))
        with patch.dict(os.environ, {'AURA_SUMMARY_BACKGROUND': 'true'}), \
             patch.object(tutor, '_source_answer', return_value=(source, {
                 'valid': True, 'response_mode': 'checked_points', 'sections_missing': 1})), \
             patch('backend.ai.source_aware.background_lesson', return_value=background):
            result = tutor.answer('summarize the PDF in 2000 words', course_id=3, source_id=7)
        self.assertTrue(result['length_validation']['valid'])
        self.assertEqual(result['length_validation']['actual_words'], 2124)
        self.assertIn('Some parts of your material could not be included', result['answer'])
        self.assertIn('does not fill those source gaps', result['answer'])
        self.assertFalse(result['sections'][1]['verified'])

    def test_reviewer_receives_both_accounts_and_explicit_correction_requirements(self):
        client = Mock(); client.with_output_budget.return_value = client
        client.generate_json.return_value = REJECT
        source = 'The material describes transport from side A toward side B.'
        draft = 'The same transporter moves material from side B toward side A.'
        checked = review_background(client, 'Explain transport', source, draft, 'standard')
        self.assertFalse(checked.acceptable)
        prompt = client.generate_json.call_args.args[0]
        self.assertIn('two contradictory accounts', prompt)
        self.assertIn('composition ratio cannot establish a measured diffusion rate', prompt)
        payload = json.loads(prompt.split('\nDATA: ', 1)[1])
        self.assertEqual(payload['checked_overview'], source)
        self.assertEqual(payload['draft'], draft)
        self.assertFalse(payload['external_sources_available'])


if __name__ == '__main__':
    unittest.main()
