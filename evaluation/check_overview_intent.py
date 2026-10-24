"""Regressions for live whole-summary topic rejection before source checks."""
import copy
import json
import unittest
from unittest.mock import Mock

from backend.ai.rag import RAG
from backend.ai.source_aware import SourceAwareTutor
from backend.ai.summary_answer import SummaryDraft
from backend.ai.summary_intent import generic_material_summary
from backend.ai.response_request import word_count
from evaluation.check_long_answers import LengthLLM, DocumentRetriever, long_fixture, HISTORY
from evaluation.check_phase2 import Retriever, FakeLLM
from evaluation.check_sectioned_summaries import scoped_fixture_points


CONTEXT = {'scope': 'selected_material_overview', 'source_id': 7}
SOURCES = [{'source_id': 7, 'source_name': 'fixture.ppt',
            'content': 'Biological membranes define cell boundaries.'}]
POINTS = [{'text': 'Membranes delimit cells', 'citation_ids': [1]}]


class RejectedOverviewLLM(LengthLLM):
    """Two 916-word / 21-point drafts, then source-scoped additional detail."""
    def __init__(self):
        super().__init__()
        self.rows, original = long_fixture()
        first = original['sentences'][:36]
        merged = [{'text': first[i]['text'] + '. ' + first[i + 1]['text'],
                   'citation_ids': first[i]['citation_ids'] + first[i + 1]['citation_ids']}
                  for i in range(0, 32, 2)] + copy.deepcopy(first[32:])
        extra = {'text': 'The recorded membrane samples contain labeled proteins and lipids under the experimental conditions described in material',
                 'citation_ids': [9]}
        assert word_count(extra['text']) == 16
        self.rows[8].chunk.content += '\n' + extra['text'] + '.'
        self.seed = {'sentences': merged + [extra]}
        self.full = {'sentences': copy.deepcopy(original['sentences']) + [extra]}

    def generate_json(self, data, max_retries=2, system_prompt=None):
        if 'SELECTED uploaded material' in (system_prompt or ''):
            payload = json.loads(data)
            if 'section_request' not in payload:
                self.calls.append(('whole', payload))
                return copy.deepcopy(self.seed)
            self.calls.append(('supplement', payload))
            existing = {p['text'] for p in payload['already_explained']}
            return {'sentences': scoped_fixture_points(payload, [p for p in self.full['sentences']
                                  if p['text'] not in existing])}
        if 'answers_question' in data:
            payload = json.loads(data.split('DATA: ', 1)[1])
            self.calls.append(('intent', payload))
            # Reproduce the old veto on the whole-file draft; still judge local
            # section intent instead of silently accepting arbitrary answers.
            return {'answers_question': bool(payload['intent_context']),
                    'reason': 'Controlled whole-summary rejection.'}
        return super().generate_json(data, max_retries, system_prompt)


class OverviewIntentChecks(unittest.TestCase):
    def validate(self, llm, question='summarize the ppt', sources=None, points=None, context=None, answer=None):
        points = POINTS if points is None else points
        text = answer or SummaryDraft.model_validate({'sentences': points}).render(len(sources or SOURCES))
        return RAG(Retriever(), llm)._validate_answer(text, sources or SOURCES, question,
            structured_points=points, intent_context=CONTEXT if context is None else context)

    def test_generic_recognizer_keeps_only_whole_file_and_presentation_modifiers(self):
        for question in ('summarize the ppt', 'Please summarize the entire presentation in 2000 words',
                         'Explain the selected material.', 'give me a detailed summary of my PDF',
                         'summarize the ppt\nAnswer format requested now: in 2000 words',
                         'summarize the ppt in Hindi', 'What does the file cover?', 'give me a summary'):
            with self.subTest(question=question):
                self.assertTrue(generic_material_summary(question))
        for question in ('Explain ChatGPT in 2000 words', 'summarize the ppt focusing on membrane proteins',
                         'summarize the ppt and compare it with ChatGPT', 'explain slide 4',
                         'summarize the ppt\nAnswer format requested now: Explain ChatGPT',
                         'summarize the ppt about photosynthesis', 'summary of membrane proteins'):
            with self.subTest(question=question):
                self.assertFalse(generic_material_summary(question))

    def test_two_916_word_drafts_reach_checks_and_expansion_instead_of_quote_fallback(self):
        llm = RejectedOverviewLLM()
        self.assertEqual(len(llm.seed['sentences']), 21)
        self.assertEqual(sum(word_count(p['text']) for p in llm.seed['sentences']), 916)
        result = SourceAwareTutor(RAG(DocumentRetriever(llm.rows), llm)).answer(
            'in 2000 words', course_id=3, source_id=7, history=HISTORY)
        self.assertTrue(result['length_validation']['valid'], result['length_validation'])
        self.assertEqual(result['length_validation']['actual_words'], 2016)
        self.assertNotEqual(result['citation_validation']['response_mode'], 'extractive')
        self.assertEqual(len([c for c in llm.calls if c[0] == 'whole']), 2)
        self.assertEqual(len([c for c in llm.calls if c[0] == 'supplement']), 6)
        self.assertTrue(all(c[1]['intent_context']['scope'] == 'selected_material_section'
                            for c in llm.calls if c[0] == 'intent'))
        for point in llm.full['sentences']:
            self.assertIn(point['text'], result['answer'])

    def test_generic_summary_still_requires_positive_factual_support(self):
        llm = FakeLLM(supported=False)
        result = self.validate(llm)
        self.assertFalse(result['valid'])
        self.assertEqual(result['stage'], 'grounding')
        self.assertEqual(result['question_validation']['method'], 'bound_material_overview')
        self.assertFalse(result['grounding_validation']['results'][0]['supported'])
        self.assertTrue(any('supported' in call[3] for call in llm.calls))

    def test_literal_selected_file_content_needs_no_semantic_model_call(self):
        llm = Mock()
        points = [{'text': 'Biological membranes define cell boundaries', 'citation_ids': [1]}]
        result = self.validate(llm, points=points)
        self.assertTrue(result['valid'])
        self.assertEqual(result['question_validation']['method'], 'bound_material_overview')
        llm.generate_json.assert_not_called()

    def test_foreign_answer_cannot_pass_by_using_selected_file_citation(self):
        llm = FakeLLM(supported=False)
        result = self.validate(llm, points=[{'text': 'ChatGPT is an AI chatbot', 'citation_ids': [1]}])
        self.assertFalse(result['valid'])
        self.assertEqual(result['stage'], 'grounding')

    def test_focused_and_named_requests_keep_semantic_intent_rejection(self):
        for question in ('Explain ChatGPT', 'summarize the ppt focusing on membrane proteins'):
            llm = Mock()
            llm.generate_json.return_value = {'answers_question': False, 'reason': 'Wrong requested topic.'}
            result = self.validate(llm, question=question)
            self.assertFalse(result['valid'])
            self.assertEqual(result['stage'], 'question_relevance')
            llm.generate_json.assert_called_once()

    def test_mixed_or_mismatched_file_bindings_do_not_skip_intent(self):
        for sources, context in ((SOURCES, {**CONTEXT, 'source_id': 8}),
                                 (SOURCES + [{**SOURCES[0], 'source_id': 8}], CONTEXT),
                                 ([{'content': SOURCES[0]['content']}], CONTEXT),
                                 (SOURCES, {**CONTEXT, 'source_id': True})):
            llm = Mock()
            llm.generate_json.return_value = {'answers_question': False, 'reason': 'No selected-file match.'}
            result = self.validate(llm, sources=sources, context=context)
            self.assertFalse(result['valid'])
            self.assertEqual(result['stage'], 'question_relevance')
            llm.generate_json.assert_called_once()

    def test_unavailable_source_verification_does_not_approve_generic_overview(self):
        llm = Mock()
        llm.generate_json.side_effect = RuntimeError('Unavailable fixture verifier')
        result = self.validate(llm)
        self.assertFalse(result['valid'])
        self.assertEqual(result['stage'], 'verification_unavailable')

    def test_no_unstructured_answer_shortcut(self):
        llm = Mock()
        llm.generate_json.return_value = {'answers_question': False, 'reason': 'Wrong topic.'}
        result = RAG(Retriever(), llm)._validate_answer('A statement [1].', SOURCES,
            'summarize the ppt', intent_context=CONTEXT)
        self.assertFalse(result['valid'])
        self.assertEqual(result['stage'], 'question_relevance')

    def test_rendered_mismatch_and_invalid_source_ids_fail_before_task_binding(self):
        for answer in ('An invented claim [1].', 'Membranes delimit cells [8].'):
            result = self.validate(Mock(), answer=answer)
            self.assertFalse(result['valid'])
            self.assertEqual(result['stage'], 'structured_answer_mismatch')


if __name__ == '__main__':
    unittest.main()
