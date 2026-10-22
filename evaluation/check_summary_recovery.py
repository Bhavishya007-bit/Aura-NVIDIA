"""Exercise the screenshot failure through real orchestration and validators."""
import copy
import json
import unittest

from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor
from backend.ai.summary_answer import SummaryDraft, recover_summary, literal_excerpt
from evaluation.check_phase2 import FakeLLM, Retriever, chunk, verdict


class SummaryLLM(FakeLLM):
    def __init__(self, draft=None, **kwargs):
        super().__init__(**kwargs)
        self.draft = draft or {'sentences': [
            {'text': 'The membrane is a lipid bilayer', 'citation_ids': [1]}]}

    def generate_json(self, data, max_retries=2, system_prompt=None):
        if 'SELECTED uploaded material' in (system_prompt or ''):
            self.calls.append((self.task, 'summary_json', system_prompt, data))
            if isinstance(self.draft, Exception):
                raise self.draft
            return copy.deepcopy(self.draft)
        if 'BATCH_CLAIMS_DATA: ' in data:
            items = json.loads(data.split('BATCH_CLAIMS_DATA: ', 1)[1])
            return {'results': [{'id': item['id'], 'supported': 'gold' not in item['claim'].casefold(),
                                 'reason': 'Controlled claim check.'} for item in items]}
        if 'CLAIM:' in data:
            claim = data.split('CLAIM:', 1)[1].split('EVIDENCE:', 1)[0]
            return {'supported': 'gold' not in claim.casefold(), 'reason': 'Controlled claim check.'}
        return super().generate_json(data, max_retries, system_prompt)


class SummaryRecoveryChecks(unittest.TestCase):
    def test_wrapped_heading_retains_its_completion(self):
        text = '<number>\n\nEach Type of Membrane Has Characteristic\nLipids and Proteins'
        quote = literal_excerpt(text, 'summarize the ppt')
        self.assertIn('Lipids and Proteins', quote)
        self.assertIn(quote, text)

    def run_tutor(self, rows=None, **kwargs):
        self.llm = SummaryLLM(**kwargs)
        return SourceAwareTutor(RAG(Retriever(rows), self.llm)).answer(
            'summarize the ppt', course_id=3, source_id=7)

    def test_partial_coverage_still_returns_source_summary(self):
        r = self.run_tutor(decisions=[verdict('partially_covered')])
        self.assertIn('The membrane is a lipid bilayer [1].', r['answer'])
        self.assertNotIn('remaining parts were not found', r['answer'])
        self.assertTrue(r['citation_validation']['valid'])
        self.assertEqual([s['kind'] for s in r['sections']], ['sourced'])

    def test_unknown_coverage_does_not_block_summary_generation(self):
        r = self.run_tutor(decisions=[RuntimeError('judge unavailable')])
        self.assertTrue(r['sections'])
        self.assertEqual(r['coverage']['status'], 'unknown')
        self.assertNotIn("couldn't determine", r['answer'])

    def test_uncovered_verdict_cannot_block_file_overview(self):
        r = self.run_tutor(decisions=[verdict('not_covered')])
        self.assertTrue(r['sections'])
        self.assertEqual(r['coverage']['status'], 'unknown')
        self.assertNotIn("couldn't find", r['answer'])

    def test_keep_individually_supported_points_drop_bad_claim(self):
        r = self.run_tutor(draft={'sentences': [
            {'text': 'Membranes contain a lipid bilayer', 'citation_ids': [1]},
            {'text': 'Membranes contain pure gold', 'citation_ids': [1]}]})
        self.assertIn('Membranes contain a lipid bilayer', r['answer'])
        self.assertNotIn('pure gold', r['answer'])
        self.assertEqual(r['citation_validation']['response_mode'], 'checked_points')

    def test_unavailable_generation_produces_exact_source_quotes(self):
        r = self.run_tutor(draft=RuntimeError('provider unavailable'))
        self.assertIn('“The membrane is a lipid bilayer.” [1]', r['answer'])
        self.assertEqual(r['citation_validation']['response_mode'], 'extractive')
        self.assertTrue(r['citation_validation']['valid'])
        self.assertEqual(len([c for c in self.llm.calls if c[1] == 'summary_json']), 2)

    def test_invalid_summary_id_never_published(self):
        r = self.run_tutor(draft={'sentences': [{'text': 'Made up', 'citation_ids': [999]}]})
        self.assertNotIn('Made up', r['answer'])
        self.assertEqual(r['sections'][0]['citation_ids'], [1])

    def test_malformed_summary_does_not_end_in_notices_only(self):
        r = self.run_tutor(draft={'answer': 'Uncited draft'})
        self.assertTrue(r['sections'])
        self.assertNotIn('Uncited draft', r['answer'])

    def test_empty_sources_do_not_generate_a_fake_summary(self):
        r = self.run_tutor(rows=[])
        self.assertEqual(r['sections'], [])
        self.assertFalse(any(c[1] == 'summary_json' for c in self.llm.calls))

    def test_readable_sources_are_scoped_through_overview_only(self):
        retriever = Retriever()
        r = SourceAwareTutor(RAG(retriever, SummaryLLM())).answer('summarize the ppt', course_id=3, source_id=7)
        self.assertTrue(r['sections'])
        self.assertTrue(all(c[0] == 'overview' and c[2]['source_id'] == 7 and c[2]['course_id'] == 3 for c in retriever.calls))

    def test_no_web_or_background_generation_for_summaries(self):
        self.run_tutor(decisions=[verdict('partially_covered')])
        self.assertFalse(any(c[1] == 'text' for c in self.llm.calls))

    def test_strict_json_disallows_boolean_source_id(self):
        with self.assertRaises(ValueError):
            SummaryDraft.model_validate({'sentences': [{'text': 'A point', 'citation_ids': [True]}]})

    def test_inline_model_citations_disallowed(self):
        with self.assertRaises(ValueError):
            SummaryDraft.model_validate({'sentences': [{'text': 'A point [999]', 'citation_ids': [1]}]}).render(1)

    def test_no_cross_sentence_anaphora_in_salvaged_points(self):
        sources = [{'content': 'A membrane contains lipids.', 'source_id': 7, 'page': 1}]
        checks = [{'grounding_validation': {'results': [
            {'claim': 'This causes a change', 'supported': True, 'citations': [1]},
            {'claim': 'The membrane contains lipids', 'supported': True, 'citations': [999]},
        ]}}]
        section, validation = recover_summary(sources, checks, 'summarize this')
        self.assertIsNone(section)

    def test_literal_quotes_preserve_citations_and_locations(self):
        sources = [
            {'content': 'Membrane proteins associate with the cell membrane.', 'source_id': 7, 'slide': 9},
            {'content': 'Another readable statement about the same slide.', 'source_id': 7, 'slide': 9},
            {'content': 'Some membrane proteins have a beta-barrel structure.', 'source_id': 7, 'slide': 18},
        ]
        section, validation = recover_summary(sources, [], 'summarize the ppt')
        self.assertEqual(section.citation_ids, [1, 3])
        self.assertNotIn('Another readable', section.text)
        self.assertEqual(validation['response_mode'], 'extractive')


if __name__ == '__main__':
    unittest.main()
