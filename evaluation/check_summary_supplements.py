"""Regressions for live 1110-word output, section intent and small-claim latency."""
import copy
import json
import unittest
from unittest.mock import Mock

from backend.ai.citation_grounding import CitationGrounding
from backend.ai.rag import RAG
from backend.ai.response_request import word_count, response_request
from backend.ai.source_aware import SourceAwareTutor, _schema_errors
from backend.ai.summary_answer import SummaryDraft
from backend.ai.long_summary import expand_summary
from evaluation.check_long_answers import long_fixture, LengthLLM, DocumentRetriever, HISTORY
from evaluation.check_sectioned_summaries import scoped_fixture_points


class SupplementLLM(LengthLLM):
    def __init__(self, repeat=False):
        super().__init__()
        self.rows, self.full = long_fixture()
        extra = {'text': 'Membrane samples include labeled proteins under the recorded experimental conditions',
                 'citation_ids': [9]}
        self.rows[8].chunk.content += '\n' + extra['text'] + '.'
        self.full['sentences'].append(extra)
        self.seed = {'sentences': copy.deepcopy(self.full['sentences'][:44] + [extra])}
        self.repeat = repeat

    def generate_json(self, data, max_retries=2, system_prompt=None):
        if 'SELECTED uploaded material' in (system_prompt or ''):
            payload = json.loads(data)
            if 'section_request' not in payload:
                self.calls.append(('whole', payload))
                return copy.deepcopy(self.seed)
            self.calls.append(('supplement', payload))
            existing = {p['text'] for p in payload['already_explained']}
            points = scoped_fixture_points(payload, [p for p in self.full['sentences']
                if (p['text'] in existing) == self.repeat])
            return {'sentences': points}
        if 'answers_question' in data:
            payload = json.loads(data.split('DATA: ', 1)[1])
            self.calls.append(('intent', payload))
            # Reproduce the old full-request/partial-section mismatch without
            # bypassing the intent judge: a short portion fails a 2000-word task.
            on_topic = not ('2000' in payload['question'] and word_count(payload['answer']) < 500)
            return {'answers_question': on_topic, 'reason': 'Controlled full-versus-section intent check.'}
        return super().generate_json(data, max_retries, system_prompt)


class SupplementChecks(unittest.TestCase):
    def test_verified_1110_word_draft_is_retained_and_completed_by_additions(self):
        llm = SupplementLLM()
        self.assertEqual(sum(word_count(p['text']) for p in llm.seed['sentences']), 1110)
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertTrue(result['length_validation']['valid'], result['length_validation'])
        self.assertEqual(result['length_validation']['actual_words'], 2010)
        for point in llm.seed['sentences']:
            self.assertIn(point['text'], result['answer'])
        supplements = [c[1] for c in llm.calls if c[0] == 'supplement']
        self.assertEqual(len(supplements), 4)
        self.assertEqual(supplements[0]['section_request']['target_words'], 115)
        self.assertEqual(len(supplements[0]['already_explained']), 45)
        self.assertFalse(any(s['kind'] == 'beyond' for s in result['sections']))

    def test_section_intent_uses_local_question_and_assigned_passages(self):
        llm = SupplementLLM()
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        intents = [c[1] for c in llm.calls if c[0] == 'intent' and c[1]['intent_context']]
        self.assertEqual(len(intents), 4)
        for intent in intents:
            self.assertNotIn('2000', intent['question'])
            self.assertEqual(intent['intent_context']['scope'], 'selected_material_section')
            self.assertTrue(intent['intent_context']['passages'])
        self.assertTrue(result['length_validation']['valid'])

    def test_repeated_checked_points_do_not_pad_the_word_count(self):
        llm = SupplementLLM(repeat=True)
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertEqual(result['length_validation']['actual_words'], 1110)
        self.assertFalse(result['length_validation']['valid'])
        self.assertLessEqual(len([c for c in llm.calls if c[0] == 'supplement']), 6)

    def test_only_supported_seed_points_can_be_carried_forward(self):
        llm = SupplementLLM(repeat=True)
        rag = RAG(DocumentRetriever(llm.rows), llm)
        sources = rag._build_sources(llm.rows)
        seed = {'grounding_validation': {'results': [
            {'claim': 'The membrane contains pure gold', 'citations': [1], 'supported': False},
            {'claim': llm.seed['sentences'][0]['text'], 'citations': [1], 'supported': True}]}}
        result = expand_summary(rag, llm, sources, 'summarize in 2000 words',
            response_request('in 2000 words'), {}, _schema_errors, seed_check=seed)
        self.assertIsNotNone(result)
        self.assertNotIn('gold', result[0].text)
        self.assertIn(llm.seed['sentences'][0]['text'], result[0].text)

    def test_checked_seed_order_preserves_pronoun_antecedents(self):
        llm = SupplementLLM(repeat=True)
        rag = RAG(DocumentRetriever(llm.rows), llm)
        sources = rag._build_sources(llm.rows)
        claims = ['A membrane marks the cell boundary', 'It contains lipids']
        sources[0]['content'] += '\n' + '. '.join(claims) + '.'
        seed = {'grounding_validation': {'results': [
            {'claim': text, 'citations': [1], 'supported': True} for text in claims]}}
        section, _ = expand_summary(rag, llm, sources, 'summarize in 2000 words',
            response_request('in 2000 words'), {}, _schema_errors, seed_check=seed)
        self.assertIn(claims[1], section.text)
        self.assertLess(section.text.index(claims[0]), section.text.index(claims[1]))

    def test_local_intent_context_does_not_bypass_topic_rejection(self):
        llm = Mock()
        llm.generate_json.return_value = {'answers_question': False, 'reason': 'Wrong subject.'}
        points = [{'text': 'A statement about another subject', 'citation_ids': [1]}]
        answer = SummaryDraft.model_validate({'sentences': points}).render(1)
        result = RAG(DocumentRetriever([]), llm)._validate_answer(answer,
            [{'content': 'The assigned teaching material is about membranes.'}], 'summarize the ppt',
            structured_points=points, intent_context={'scope': 'selected_material_section',
                'section_question': 'Explain membrane structure.', 'passages': []})
        self.assertFalse(result['valid'])
        self.assertEqual(result['stage'], 'question_relevance')
        self.assertEqual(llm.generate_json.call_count, 1)


class SmallBatchChecks(unittest.TestCase):
    def checker(self, missing=False):
        llm = Mock()
        def decide(data, **kwargs):
            items = json.loads(data.split('BATCH_CLAIMS_DATA: ', 1)[1])
            if missing:
                items = items[:-1]
            return {'results': [{'id': p['id'], 'supported': p['claim'] != 'Teaching point 5',
                                 'reason': 'Controlled evidence decision.'} for p in items]}
        llm.generate_json.side_effect = decide
        return CitationGrounding(llm), llm

    def points(self, count):
        return [{'text': f'Teaching point {i}', 'citation_ids': [1]} for i in range(count)]

    def test_twelve_nonliteral_structured_points_use_one_independent_batch(self):
        checker, llm = self.checker()
        result = checker.verify_points(self.points(12), [{'content': 'Evidence for checking the teaching points.'}])
        self.assertEqual(llm.generate_json.call_count, 1)
        self.assertFalse(result['valid'])
        self.assertFalse(result['results'][5]['supported'])
        self.assertTrue(result['results'][4]['supported'])
        self.assertTrue(result['results'][6]['supported'])

    def test_two_structured_points_also_share_one_batch(self):
        checker, llm = self.checker()
        self.assertTrue(checker.verify_points(self.points(2), [{'content': 'Evidence for checking.'}])['valid'])
        self.assertEqual(llm.generate_json.call_count, 1)

    def test_missing_batch_decision_never_approves_the_section(self):
        checker, llm = self.checker(missing=True)
        result = checker.verify_points(self.points(12), [{'content': 'Evidence for checking.'}])
        self.assertFalse(result['valid'])
        self.assertTrue(all(p.get('error') == 'verification_unavailable' for p in result['results']))


if __name__ == '__main__':
    unittest.main()
