"""Controlled regressions for length/style follow-ups and long cited answers."""
import copy
import json
import os
import unittest
from unittest.mock import Mock, patch

from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor
from backend.ai.response_request import (resolve_format_followup, response_request,
    is_format_followup, word_count, length_check)
from backend.ai.summary_answer import SummaryDraft, recover_summary
from backend.ai.citation_grounding import CitationGrounding
from backend.ai.llm import LLM
from evaluation.check_phase2 import Retriever, chunk, verdict
from evaluation.check_summary_recovery import SummaryLLM


HISTORY = [{'role': 'user', 'content': 'summarize the ppt'},
           {'role': 'assistant', 'content': 'A brief source-backed summary.'}]


class RequestChecks(unittest.TestCase):
    def test_length_followup_is_deterministic_and_keeps_subject(self):
        llm = Mock()
        q = RAG(Retriever(), llm)._resolve_followup('in 2000 words', HISTORY)
        self.assertTrue(q.startswith('summarize the ppt\n'))
        self.assertEqual(response_request(q)['target_words'], 2000)
        llm.generate_json.assert_not_called()

    def test_length_spellings(self):
        for text in ('in 2000 words', 'make it 2k words', 'in 2,000 words', 'in two thousand words', 'a 2000-word version', 'tell me in 2000 words', 'I want it in 2k words', 'write a full explanation in 2000 words with all details'):
            with self.subTest(text=text):
                q = resolve_format_followup(text, HISTORY)
                self.assertTrue(q.startswith('summarize the ppt\n'))
                self.assertEqual(response_request(q)['target_words'], 2000)

    def test_named_new_topics_do_not_inherit_old_summary(self):
        for q in ('Explain ChatGPT in 2000 words', 'Explain Hindi in 2000 words', 'Explain membrane proteins in a table', 'Translate the paragraph about photosynthesis into Hindi'):
            self.assertFalse(is_format_followup(q))
            self.assertEqual(resolve_format_followup(q, HISTORY), q)

    def test_chained_modifiers_preserve_subject_and_latest_length(self):
        history = HISTORY + [{'role': 'user', 'content': 'in 2000 words'},
                             {'role': 'assistant', 'content': 'Earlier output.'}]
        q = resolve_format_followup('in 1000 words', history)
        self.assertTrue(q.startswith('summarize the ppt\n'))
        self.assertEqual(response_request(q)['target_words'], 1000)

    def test_style_modifier_keeps_prior_length(self):
        history = HISTORY + [{'role': 'user', 'content': 'in 2000 words'}]
        q = resolve_format_followup('in Hindi', history)
        self.assertEqual(response_request(q)['target_words'], 2000)
        self.assertIn('in Hindi', q)

    def test_shorter_modifier_clears_prior_word_count(self):
        q = resolve_format_followup('make it shorter', HISTORY + [{'role': 'user', 'content': 'in 2000 words'}])
        self.assertIsNone(response_request(q)['target_words'])

    def test_common_format_and_depth_modifiers(self):
        for text in ('make a table', 'in bullet points', 'in paragraph form', 'Explain simply', 'go deeper', 'give me examples', 'in five sentences', 'in three paragraphs'):
            self.assertTrue(resolve_format_followup(text, HISTORY).startswith('summarize the ppt\n'), text)

    def test_word_count_ignores_citations(self):
        self.assertEqual(word_count('The membrane contains lipids [2][3].'), 4)

    def test_paragraph_target_can_coexist_with_word_target(self):
        q = resolve_format_followup('in three paragraphs', HISTORY + [{'role': 'user', 'content': 'in 2000 words'}])
        request = response_request(q)
        self.assertEqual(request['target_words'], 2000)
        self.assertEqual(request['target_paragraphs'], 3)

    def test_sentence_target_is_measured(self):
        request = response_request('in two sentences')
        self.assertFalse(length_check('One point [1].', request)['valid'])
        self.assertTrue(length_check('One point [1]. Another point [2][3].', request)['valid'])

    def test_deeper_request_expands_default_sentence_budget(self):
        request = response_request(resolve_format_followup('go deeper', HISTORY))
        self.assertTrue(request['long_form'])
        self.assertEqual(request['max_sentences'], 24)

    def test_budget_grows_only_for_requested_length(self):
        self.assertEqual(response_request('summarize the ppt')['max_sentences'], 8)
        self.assertGreater(response_request('in 2000 words')['max_sentences'], 80)
        self.assertEqual(response_request('in 2000 words')['token_budget'], 8192)
        self.assertEqual(response_request('in 100000 words')['target_words'], 5000)


def long_fixture():
    texts = []
    for i in range(80):
        texts.append(f'In example {i}, the observed membrane sample contains labelled proteins and lipids, while its recorded transport measurement is {i + 10} units under the stated experimental conditions')
    rows, sentences = [], []
    for slide in range(1, 40):
        claims = [t for i, t in enumerate(texts) if i % 39 + 1 == slide]
        row = chunk('\n'.join(t + '.' for t in claims), id=str(slide))
        row.chunk.page, row.chunk.slide = None, slide
        rows.append(row)
    for i, t in enumerate(texts):
        sentences.append({'text': t, 'citation_ids': [i % 39 + 1]})
    return rows, {'sentences': sentences}


class DocumentRetriever(Retriever):
    def document_context(self, **scope):
        self.calls.append(('document', None, scope))
        return {'results': self.rows, 'scope': 'all_available_locations',
                'locations_selected': len(self.rows), 'locations_available': len(self.rows),
                'all_chunks_included': True}


class LengthLLM(SummaryLLM):
    def generate_json(self, data, max_retries=2, system_prompt=None):
        if (system_prompt or '').startswith('AURA_LESSON_OUTLINE:'):
            payload = json.loads(data)
            self.calls.append(('outline', payload))
            groups = payload['locations']
            count = payload['section_count']
            size, extra = divmod(len(groups), count)
            parts, start = [], 0
            for index in range(count):
                end = start + size + (index < extra)
                parts.append({'title': f'Teaching topic {index+1}',
                              'focus': 'Explain the assigned recorded experimental observations.',
                              'location_ids': [g['id'] for g in groups[start:end]]})
                start = end
            return {'sections': parts}
        return super().generate_json(data, max_retries, system_prompt)

    def with_output_budget(self, tokens, *, exact=False):
        self.calls.append(('budget', tokens))
        return copy.copy(self)


class LongPipelineChecks(unittest.TestCase):
    def test_reported_2000_word_followup_produces_long_cited_explanation(self):
        rows, draft = long_fixture()
        llm = LengthLLM(draft=draft)
        retriever = DocumentRetriever(rows)
        r = SourceAwareTutor(RAG(retriever, llm)).answer('in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertEqual(r['retrieval_question'], 'summarize the ppt')
        self.assertEqual(r['response_request']['target_words'], 2000)
        self.assertTrue(r['length_validation']['valid'], r['length_validation'])
        self.assertGreaterEqual(r['length_validation']['actual_words'], 1800)
        self.assertLessEqual(r['length_validation']['actual_words'], 2200)
        self.assertEqual(r['length_validation']['actual_words'], 2000)
        self.assertEqual(len(r['sources']), 39)
        self.assertIn(39, r['sections'][0]['citation_ids'])
        self.assertIn('\n\n', r['sections'][0]['text'])
        self.assertTrue(all(s['kind'] == 'sourced' for s in r['sections']))
        self.assertFalse(any(c[1] == 'text' for c in llm.calls))
        self.assertIn(('budget', 8192), llm.calls)
        self.assertTrue(all(c[0] == 'document' and c[2]['course_id'] == 3 and c[2]['source_id'] == 7 for c in retriever.calls))

    def test_first_turn_length_request_uses_selected_file(self):
        r = SourceAwareTutor(RAG(Retriever(), LengthLLM())).answer('in 2000 words', course_id=3, source_id=7)
        self.assertEqual(r['retrieval_question'], 'Explain the selected material.')
        self.assertTrue(r['sections'])

    def test_short_draft_is_revised_with_measured_length_feedback(self):
        rows, draft = long_fixture()
        class ImprovingLLM(LengthLLM):
            def generate_json(self, data, max_retries=2, system_prompt=None):
                if 'SELECTED uploaded material' in (system_prompt or ''):
                    self.calls.append((self.task, 'summary_json', system_prompt, data))
                    if sum(c[1] == 'summary_json' for c in self.calls) == 1:
                        return {'sentences': [draft['sentences'][0]]}
                    self.latest_feedback = json.loads(data).get('feedback')
                    return draft
                return super().generate_json(data, max_retries, system_prompt)
        llm = ImprovingLLM()
        r = SourceAwareTutor(RAG(DocumentRetriever(rows), llm)).answer('in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertTrue(r['length_validation']['valid'])
        calls = [c for c in llm.calls if c[1] == 'summary_json']
        self.assertEqual(len(calls), 2)
        self.assertFalse(json.loads(calls[1][3])['feedback']['length_validation']['valid'])

    def test_still_short_checked_answer_is_honest_not_replaced_by_refusal(self):
        r = SourceAwareTutor(RAG(Retriever(), LengthLLM())).answer('in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertTrue(r['sections'])
        self.assertFalse(r['length_validation']['valid'])
        self.assertIn('requested target was approximately 2000', r['answer'])
        self.assertNotIn('Beyond your material', r['answer'])

    def test_quote_fallback_also_reports_unmet_word_target(self):
        llm = LengthLLM(draft=RuntimeError('provider unavailable'))
        r = SourceAwareTutor(RAG(Retriever(), llm)).answer('in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertEqual(r['citation_validation']['response_mode'], 'extractive')
        self.assertFalse(r['length_validation']['valid'])
        self.assertIn('requested target was approximately 2000', r['answer'])

    def test_long_checked_subset_is_not_cut_back_to_six_points(self):
        rows, draft = long_fixture()
        sources = RAG(DocumentRetriever(rows), LengthLLM())._build_sources(rows)
        checks = [{'grounding_validation': {'results': [
            {'claim': item['text'], 'citations': item['citation_ids'], 'supported': True}
            for item in draft['sentences']]}}]
        section, validation = recover_summary(sources, checks, 'summarize', response_request('in 2000 words'))
        self.assertTrue(validation['length_validation']['valid'])
        self.assertGreater(validation['supported_sentence_count'], 8)

    def test_bullet_and_table_rendering_keep_source_numbers(self):
        d = SummaryDraft.model_validate({'sentences': [{'text': 'A supported point', 'citation_ids': [1]}]})
        self.assertTrue(d.render(1, response_request('in bullet points')).startswith('- '))
        self.assertIn('| 1 | A supported point [1]. |', d.render(1, response_request('make a table')))

    def test_output_budget_does_not_mutate_shared_client(self):
        with patch.dict(os.environ, {'NEBIUS_API_KEY': 'fixture-key', 'NEBIUS_MODEL': 'fixture-model'}, clear=True):
            client = LLM()
            bigger = client.with_output_budget(8192)
        self.assertEqual(client.json_max_tokens, 4096)
        self.assertEqual(bigger.json_max_tokens, 8192)


class BatchGroundingChecks(unittest.TestCase):
    def setup_checker(self, broken=None):
        llm = Mock()
        def generate(data, **kwargs):
            rows = json.loads(data.split('BATCH_CLAIMS_DATA: ', 1)[1])
            if broken == 'missing': rows = rows[:-1]
            result = [{'id': r['id'], 'supported': r['claim'] != 'Claim 5', 'reason': 'Fixture judgement'} for r in rows]
            if broken == 'duplicate' and len(result) > 1: result[1]['id'] = result[0]['id']
            if broken == 'boolean' and result: result[0]['supported'] = 'true'
            return {'results': result}
        llm.generate_json.side_effect = generate
        return llm, CitationGrounding(llm)

    def test_long_answers_get_independent_bounded_claim_batches(self):
        llm, checker = self.setup_checker()
        r = checker.verify_answer(' '.join(f'Claim {i} [1].' for i in range(25)), [{'content': 'Evidence supplied for checking.'}])
        self.assertEqual(llm.generate_json.call_count, 3)
        self.assertFalse(r['valid'])
        self.assertFalse(r['results'][5]['supported'])
        self.assertEqual(sum(x['supported'] for x in r['results']), 24)

    def test_malformed_batches_cannot_approve_claims(self):
        for broken in ('missing', 'duplicate', 'boolean'):
            _, checker = self.setup_checker(broken)
            r = checker.verify_answer(' '.join(f'Claim {i} [1].' for i in range(13)), [{'content': 'Evidence.'}])
            self.assertFalse(r['valid'])
            self.assertTrue(any(x.get('error') == 'verification_unavailable' for x in r['results']))

    def test_literal_long_answers_need_no_batch_model_calls(self):
        llm, checker = self.setup_checker()
        claims = [f'This is literal source statement number {i}' for i in range(20)]
        r = checker.verify_answer(' '.join(c + ' [1].' for c in claims), [{'content': '\n'.join(claims)}])
        self.assertTrue(r['valid'])
        llm.generate_json.assert_not_called()


if __name__ == '__main__':
    unittest.main()
