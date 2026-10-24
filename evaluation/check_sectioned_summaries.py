"""Intact scientific claims and bounded long-summary expansion regressions."""
import copy
import json
import unittest
from unittest.mock import patch

from backend.ai.citation_grounding import CitationGrounding
from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor, _schema_errors
from backend.ai.summary_answer import SummaryDraft, SummaryDraftError, recover_summary
from backend.ai.long_summary import summary_plan, expand_summary
from backend.ai.response_request import response_request
from evaluation.check_phase2 import FakeLLM, Retriever
from evaluation.check_long_answers import long_fixture, LengthLLM, DocumentRetriever, HISTORY


class ScientificClaimChecks(unittest.TestCase):
    def test_scientific_abbreviations_remain_in_one_checked_unit(self):
        for text in ('Membrane sterols vary from 0% (E. coli) to 25% (mouse liver)',
                     'A helix has 3.6 residues per turn, e.g. in this recorded example',
                     'The diagram labels proteins (Fig. 2) and lipids together'):
            with self.subTest(text=text):
                points = [{'text': text, 'citation_ids': [1]}]
                sources = [{'content': text + '.', 'source_name': 'fixture.ppt'}]
                rag = RAG(Retriever(), FakeLLM())
                answer = SummaryDraft.model_validate({'sentences': points}).render(1)
                result = rag._validate_answer(answer, sources, 'summarize the ppt', structured_points=points)
                self.assertTrue(result['valid'], result)
                self.assertEqual(result['grounding_validation']['results'][0]['claim'], text)
                self.assertEqual(len(result['grounding_validation']['results']), 1)

    def test_partial_sentence_cannot_be_salvaged_even_if_judge_says_true(self):
        sources = [{'content': 'The original complete statement is available.'}]
        checks = [{'grounding_validation': {'results': [{
            'claim': 'coli) to 25% (mouse liver), with sterol type reflecting composition',
            'citations': [1], 'supported': True}]}}]
        section, validation = recover_summary(sources, checks, 'summarize the ppt')
        self.assertEqual(validation['response_mode'], 'extractive')
        self.assertNotIn('coli)', section.text)
        with self.assertRaises(SummaryDraftError):
            SummaryDraft.model_validate({'sentences': [{'text': 'coli) to 25%', 'citation_ids': [1]}]}).render(1)

    def test_verifier_gets_full_compound_claim_and_cannot_approve_only_tail(self):
        text = 'The listed membrane has 0% sterols (E. coli) and also contains pure gold'
        result = CitationGrounding(FakeLLM(supported=False)).verify_points(
            [{'text': text, 'citation_ids': [1]}], [{'content': 'The listed membrane has 0% sterols.'}])
        self.assertFalse(result['valid'])
        self.assertEqual(result['results'][0]['claim'], text)

    def test_checked_units_must_match_the_displayed_answer(self):
        points = [{'text': 'The membrane contains lipids', 'citation_ids': [1]}]
        rag = RAG(Retriever(), FakeLLM())
        result = rag._validate_answer('The membrane contains gold [1].',
            [{'content': 'The membrane contains lipids.'}], structured_points=points)
        self.assertFalse(result['valid'])
        self.assertEqual(result['stage'], 'structured_answer_mismatch')

    def test_prose_bullets_and_tables_bind_to_the_same_complete_units(self):
        points = [{'text': 'A membrane contains lipids', 'citation_ids': [1]},
                  {'text': 'A membrane contains proteins', 'citation_ids': [2]}]
        sources = [{'content': p['text'] + '.'} for p in points]
        for layout in ('prose', 'bullets', 'table'):
            with self.subTest(layout=layout):
                text = SummaryDraft.model_validate({'sentences': points}).render(2, {'max_sentences': 8, 'layout': layout})
                result = RAG(Retriever(), FakeLLM())._validate_answer(text, sources, structured_points=points)
                self.assertTrue(result['valid'], result)

    def test_structured_claim_api_still_rejects_missing_or_foreign_citations(self):
        checker = CitationGrounding(FakeLLM())
        for point in ({'text': 'A point', 'citation_ids': []},
                      {'text': 'A point', 'citation_ids': [True]},
                      {'text': 'A point', 'citation_ids': [9]},
                      {'text': 'A point [1]', 'citation_ids': [1]}):
            with self.subTest(point=point):
                self.assertFalse(checker.verify_points([point], [{'content': 'A point'}])['valid'])


def scoped_fixture_points(payload, points):
    """Answer against the actual supplied passages in their declared namespace."""
    result = []
    for point in points:
        ids = [source['id'] for source in payload['passages'] if point['text'] in source['text']]
        if ids:
            result.append({'text': point['text'], 'citation_ids': ids})
    return result


class SectionLLM(LengthLLM):
    def __init__(self, mode='normal'):
        self.rows, self.full = long_fixture()
        super().__init__()
        self.mode = mode
        self.part_attempts = {}

    def generate_json(self, data, max_retries=2, system_prompt=None):
        if 'SELECTED uploaded material' in (system_prompt or ''):
            payload = json.loads(data)
            if 'section_request' not in payload:
                self.calls.append(('whole', payload))
                return {'sentences': copy.deepcopy(self.full['sentences'][:8])}
            self.calls.append(('part', payload))
            part = payload['section_request']
            index = part['index']
            self.part_attempts[index] = self.part_attempts.get(index, 0) + 1
            if self.mode == 'empty':
                return {'sentences': []}
            points = scoped_fixture_points(payload, self.full['sentences'])
            if self.mode == 'repair' and index == 2 and self.part_attempts[index] == 1:
                return {'sentences': points[:1] + [{'text': 'The membrane contains pure gold',
                                                   'citation_ids': [part['source_ids'][0]]}]}
            if self.mode == 'foreign' and index == 1 and self.part_attempts[index] == 1:
                return {'sentences': [{'text': 'This point uses a foreign section source',
                                       'citation_ids': [next(n for n in range(1, 40) if n not in part['source_ids'])]}]}
            return {'sentences': points}
        if 'BATCH_CLAIMS_DATA: ' in data:
            items = json.loads(data.split('BATCH_CLAIMS_DATA: ', 1)[1])
            return {'results': [{'id': p['id'], 'supported': 'gold' not in p['claim'],
                                 'reason': 'Controlled evidence check.'} for p in items]}
        return super().generate_json(data, max_retries, system_prompt)


class SectionExpansionChecks(unittest.TestCase):
    def run_tutor(self, mode='normal'):
        llm = SectionLLM(mode)
        retriever = DocumentRetriever(llm.rows)
        result = SourceAwareTutor(RAG(retriever, llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        return result, llm

    def test_two_short_drafts_expand_to_2000_checked_words_across_the_file(self):
        result, llm = self.run_tutor()
        self.assertTrue(result['length_validation']['valid'], result['length_validation'])
        self.assertEqual(result['length_validation']['actual_words'], 2000)
        self.assertEqual(result['citation_validation']['source_validation']['stage'], 'summary_section_expansion')
        self.assertEqual(len([c for c in llm.calls if c[0] == 'whole']), 2)
        parts = [c[1] for c in llm.calls if c[0] == 'part']
        self.assertEqual(len(parts), 4)
        self.assertEqual([p['section_request']['target_words'] for p in parts], [300, 500, 500, 450])
        self.assertEqual([p['section_request']['section_total_target_words'] for p in parts], [500] * 4)
        supplied = [source['text'] for part in parts for source in part['passages']]
        self.assertCountEqual(supplied, [row.chunk.content for row in llm.rows])
        for part in parts:
            self.assertEqual(part['section_request']['source_ids'], list(range(1, len(part['passages'])+1)))
        self.assertFalse(any(s['kind'] == 'beyond' for s in result['sections']))
        self.assertIn(('budget', 4096), llm.calls)

    def test_only_incomplete_section_is_repaired_and_false_claim_never_appears(self):
        result, llm = self.run_tutor('repair')
        self.assertTrue(result['length_validation']['valid'], result['length_validation'])
        self.assertNotIn('gold', result['answer'])
        self.assertEqual(llm.part_attempts, {1: 1, 2: 2, 3: 1, 4: 1})
        repair = [c[1] for c in llm.calls if c[0] == 'part' and 'feedback' in c[1]][0]
        self.assertTrue(repair['feedback']['failed_points'])
        self.assertIsNotNone(repair['previous_draft'])

    def test_section_cannot_cite_evidence_it_was_not_given(self):
        result, llm = self.run_tutor('foreign')
        self.assertTrue(result['length_validation']['valid'], result['length_validation'])
        self.assertNotIn('foreign section source', result['answer'])
        self.assertEqual(llm.part_attempts[1], 2)

    def test_all_empty_sections_stop_after_two_shared_repairs_and_keep_short_answer(self):
        result, llm = self.run_tutor('empty')
        self.assertFalse(result['length_validation']['valid'])
        self.assertEqual(len([c for c in llm.calls if c[0] == 'part']), 6)
        self.assertTrue(all(n <= 2 for n in llm.part_attempts.values()))
        self.assertIn('requested target was approximately 2000', result['answer'])
        self.assertNotEqual(result['citation_validation']['response_mode'], 'extractive')

    def test_plan_keeps_native_ocr_and_vision_from_same_slide_together(self):
        sources = [{'source_id': 7, 'slide': i, 'content': 'Fixture'} for i in range(1, 40)] * 2
        plan = summary_plan(sources, 2000)
        positions = {n: p['index'] for p in plan for n in p['source_ids']}
        self.assertTrue(all(positions[n] == positions[n + 39] for n in range(1, 40)))
        self.assertEqual(sum(p['target_words'] for p in plan), 2000)
        self.assertLessEqual(len(summary_plan(sources, 5000)), 8)

    def test_step_deadline_prevents_new_generation_calls(self):
        llm = SectionLLM()
        rag = RAG(DocumentRetriever(llm.rows), llm)
        sources = rag._build_sources(llm.rows)
        with patch('backend.ai.long_summary.time.monotonic', side_effect=[0, 181, 182]):
            result = expand_summary(rag, llm, sources, 'summarize the ppt',
                response_request('in 2000 words'), {}, _schema_errors)
        self.assertIsNone(result)
        self.assertFalse(any(c[0] == 'part' for c in llm.calls))

    def test_unavailable_verifier_stops_expansion_without_approving_output(self):
        llm = SectionLLM()
        rag = RAG(DocumentRetriever(llm.rows), llm)
        sources = rag._build_sources(llm.rows)
        with patch.object(rag, '_validate_answer', return_value={
                'valid': False, 'stage': 'verification_unavailable'}):
            result = expand_summary(rag, llm, sources, 'summarize the ppt',
                response_request('in 2000 words'), {}, _schema_errors)
        self.assertIsNone(result)
        self.assertEqual(len([c for c in llm.calls if c[0] == 'part']), 1)


if __name__ == '__main__':
    unittest.main()
