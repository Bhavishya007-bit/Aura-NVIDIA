"""Draft/coverage contract regressions based on the reported live validation failures."""
import copy
import json
import unittest

from pydantic import ValidationError

from backend.ai.answer_contract import CoverageDecision
from backend.ai.rag import RAG
from backend.ai.response_request import response_request
from backend.ai.source_aware import SourceAwareTutor
from backend.ai.summary_answer import SummaryDraft, SummaryDraftError, summary_contract
from evaluation.check_phase2 import Retriever, FakeLLM, verdict
from evaluation.check_summary_recovery import SummaryLLM
from evaluation.check_long_answers import DocumentRetriever, LengthLLM, long_fixture, HISTORY


class CoverageDraftChecks(unittest.TestCase):
    def test_overview_can_reference_all_96_available_passages(self):
        data = verdict(covered_parts=[{'part': 'Presentation overview', 'citation_ids': list(range(1, 97))}])
        rows = [{'content': f'Fixture teaching passage {i}.'} for i in range(96)]
        llm = FakeLLM(decisions=[data])
        tutor = SourceAwareTutor(RAG(Retriever(), llm))
        decision = tutor._judge('summarize the ppt', rows)
        self.assertEqual(decision.status, 'fully_covered')
        self.assertEqual(len(decision.covered_parts[0].citation_ids), 96)
        payload = json.loads(llm.calls[0][-1])
        self.assertEqual(payload['source_id_range'], {'minimum': 1, 'maximum': 96})
        schema = payload['output_schema']['$defs']['CoveredPart']['properties']['citation_ids']
        self.assertEqual(schema['maxItems'], 96)

    def test_coverage_still_rejects_foreign_or_unbounded_source_ids(self):
        for ids, source_count in (([40], 39), ([0], 39), ([True], 39), (list(range(1, 98)), 96)):
            with self.subTest(ids=ids):
                with self.assertRaises(ValueError):
                    CoverageDecision.model_validate(verdict(covered_parts=[
                        {'part': 'Overview', 'citation_ids': ids}])).check_citations(source_count)


class SummaryDraftChecks(unittest.TestCase):
    def render(self, text, ids=None, source_count=2):
        return SummaryDraft.model_validate({'sentences': [
            {'text': text, 'citation_ids': ids or [1]}]}).render(source_count)

    def test_matching_inline_citations_get_canonical_references(self):
        self.assertEqual(self.render('The membrane contains lipids [1].'),
                         'The membrane contains lipids [1].')
        self.assertEqual(self.render('Two teaching points 【1】【2】.', [1, 2]),
                         'Two teaching points [1][2].')

    def test_conflicting_and_foreign_citations_never_get_silently_removed(self):
        for text, ids, code in (('A point [2].', [1], 'citation_metadata_mismatch'),
                                ('A point.', [9], 'citation_out_of_range'),
                                ('[1]', [1], 'empty_sentence')):
            with self.subTest(code=code):
                with self.assertRaises(SummaryDraftError) as error:
                    self.render(text, ids)
                self.assertEqual(error.exception.failure_code, code)
                self.assertEqual(error.exception.feedback['sentence_index'], 0)
                self.assertNotIn(text, str(error.exception))

    def test_contract_tells_model_the_real_long_answer_bounds(self):
        request = response_request('summarize in 2000 words')
        contract = summary_contract(request, 39)
        self.assertEqual((contract['minimum_words'], contract['maximum_words']), (1800, 2200))
        self.assertEqual(contract['suggested_sentence_count'], 80)
        schema = contract['output_schema']
        self.assertEqual(schema['properties']['sentences']['maxItems'], request['max_sentences'])
        ids = schema['$defs']['SummarySentence']['properties']['citation_ids']
        self.assertEqual(ids['items']['maximum'], 39)
        self.assertEqual(ids['maxItems'], 8)

    def test_matching_citation_format_does_not_approve_false_facts(self):
        llm = SummaryLLM(draft={'sentences': [
            {'text': 'Membranes contain pure gold [1].', 'citation_ids': [1]}]})
        result = SourceAwareTutor(RAG(Retriever(), llm)).answer(
            'summarize the ppt', course_id=3, source_id=7)
        self.assertNotIn('pure gold', result['answer'])
        self.assertEqual(result['citation_validation']['response_mode'], 'extractive')

    def test_repair_receives_original_draft_and_specific_fault(self):
        rows, good = long_fixture()
        bad = copy.deepcopy(good)
        bad['sentences'][0]['text'] += ' [999]'
        class Repairing(LengthLLM):
            def generate_json(self, data, max_retries=2, system_prompt=None):
                if 'SELECTED uploaded material' in (system_prompt or ''):
                    payload = json.loads(data)
                    if 'feedback' not in payload:
                        self.calls.append(('first_draft', payload))
                        return copy.deepcopy(bad)
                    self.calls.append(('repair', payload))
                    return copy.deepcopy(good)
                return super().generate_json(data, max_retries, system_prompt)
        llm = Repairing()
        with self.assertLogs('backend.ai.source_aware', 'WARNING') as logs:
            result = SourceAwareTutor(RAG(DocumentRetriever(rows), llm)).answer(
                'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertTrue(result['length_validation']['valid'])
        self.assertEqual(result['length_validation']['actual_words'], 2000)
        repair = next(c[1] for c in llm.calls if c[0] == 'repair')
        self.assertEqual(repair['previous_draft'], bad)
        self.assertEqual(repair['feedback']['draft_error']['code'], 'citation_metadata_mismatch')
        self.assertIn('failure_code=citation_metadata_mismatch', ' '.join(logs.output))
        self.assertNotIn(good['sentences'][0]['text'], ' '.join(logs.output))

    def test_empty_first_draft_can_be_repaired_to_requested_length(self):
        rows, good = long_fixture()
        class Repairing(LengthLLM):
            def generate_json(self, data, max_retries=2, system_prompt=None):
                if 'SELECTED uploaded material' in (system_prompt or ''):
                    payload = json.loads(data)
                    if 'feedback' not in payload:
                        return {'sentences': []}
                    self.calls.append(('repair', payload))
                    return copy.deepcopy(good)
                return super().generate_json(data, max_retries, system_prompt)
        llm = Repairing()
        result = SourceAwareTutor(RAG(DocumentRetriever(rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertTrue(result['length_validation']['valid'])
        repair = next(c[1] for c in llm.calls if c[0] == 'repair')
        self.assertEqual(repair['previous_draft'], {'sentences': []})
        self.assertEqual(repair['feedback']['draft_error']['errors'][0]['type'], 'too_short')

    def test_short_valid_draft_survives_empty_second_attempt(self):
        rows, good = long_fixture()
        short = {'sentences': copy.deepcopy(good['sentences'][:8])}
        for item in short['sentences']:
            item['text'] += f" [{item['citation_ids'][0]}]"
        class ShortThenEmpty(LengthLLM):
            def generate_json(self, data, max_retries=2, system_prompt=None):
                if 'SELECTED uploaded material' in (system_prompt or ''):
                    payload = json.loads(data)
                    self.calls.append(('draft', payload))
                    return {'sentences': []} if 'feedback' in payload else copy.deepcopy(short)
                return super().generate_json(data, max_retries, system_prompt)
        llm = ShortThenEmpty()
        result = SourceAwareTutor(RAG(DocumentRetriever(rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertFalse(result['length_validation']['valid'])
        self.assertNotEqual(result['citation_validation']['response_mode'], 'extractive')
        self.assertIn('requested target was approximately 2000', result['answer'])
        # Two whole-draft attempts, four scoped sections, and two shared repairs.
        self.assertEqual(len([c for c in llm.calls if c[0] == 'draft']), 8)
        feedback = [c[1]['feedback'] for c in llm.calls if c[0] == 'draft' and 'feedback' in c[1]][0]
        self.assertEqual(feedback['length_validation']['target_words'], 2000)

    def test_empty_and_noninteger_schema_cases_remain_rejected(self):
        for draft in ({'sentences': []}, {'sentences': [{'text': 'A point', 'citation_ids': [True]}]}):
            with self.assertRaises(ValidationError):
                SummaryDraft.model_validate(draft)


if __name__ == '__main__':
    unittest.main()
