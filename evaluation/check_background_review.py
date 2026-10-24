"""Bounded background review/length checks; verdicts are controlled, not accuracy scores."""
import json
import unittest
from unittest.mock import Mock

from backend.ai.background_review import BackgroundReview
from backend.ai.summary_background import background_lesson, bounded_background
from backend.ai.response_request import response_request, word_count
from evaluation.check_quality_profile import prose

ACCEPT = {'accurate': True, 'relevant': True, 'appropriately_scoped': True, 'issues': []}
REJECT = {'accurate': False, 'relevant': True, 'appropriately_scoped': True,
          'issues': ['Correct the technical claim or remove it.']}


class BackgroundReviewChecks(unittest.TestCase):
    def client(self, texts, verdicts=None):
        client = Mock()
        client.with_output_budget.return_value = client
        client.generate.side_effect = texts
        client.generate_json.side_effect = verdicts or [ACCEPT]
        return client

    def test_reported_1105_plus_1238_word_shape_stays_inside_the_total_range(self):
        # Same measured shape as the uploaded run, without private material.
        source = prose(1105)
        paragraphs = [prose(n) for n in (150, 200, 200, 150, 200, 180, 158)]
        raw = '\n\n'.join(paragraphs)
        self.assertEqual(word_count(raw), 1238)
        client = self.client([raw])
        section = background_lesson(client, 'summarize in 2000 words', source, response_request('in 2000 words'))
        self.assertEqual(word_count(source) + word_count(section.text), 2005)
        self.assertEqual(section.text, '\n\n'.join(paragraphs[:5]))
        self.assertEqual(client.generate.call_count, 1)
        self.assertEqual(client.generate_json.call_count, 1)
        reviewed = json.loads(client.generate_json.call_args.args[0].split('\nDATA: ', 1)[1])
        self.assertEqual(reviewed['draft'], section.text)
        self.assertFalse(reviewed['external_sources_available'])
        self.assertFalse(section.verified)

    def test_overlong_single_paragraph_is_not_sliced_into_a_fragment(self):
        client = self.client([prose(1500), prose(1500)])
        result = background_lesson(client, 'in 2000 words', prose(1100), response_request('in 2000 words'))
        self.assertIsNone(result)
        client.generate_json.assert_not_called()
        self.assertEqual(client.generate.call_count, 2)

    def test_fenced_code_is_never_cut_at_a_blank_line_inside_the_fence(self):
        intro = prose(200)
        raw = intro + '\n\n```python\n' + prose(500) + '\n\n' + prose(100) + '\n```'
        trimmed = bounded_background(raw, prose(1800), response_request('in 2000 words'))
        self.assertEqual(trimmed, intro)
        self.assertNotIn('```', trimmed)

    def test_no_orphaned_heading_is_left_by_trimming(self):
        intro = prose(200)
        raw = intro + '\n\n## A different topic\n\n' + prose(600)
        trimmed = bounded_background(raw, prose(1800), response_request('in 2000 words'))
        self.assertEqual(trimmed, intro)

    def test_wrong_runtime_claim_must_be_revised_before_publication(self):
        bad = 'A compact index array means CPython uses separate chaining.'
        correction = 'An index array and an entry array describe storage layout; collision resolution is a separate design choice.'
        client = self.client([bad, correction], [REJECT, ACCEPT])
        result = background_lesson(client, 'Explain hashing in 2000 words', prose(1100), response_request('in 2000 words'))
        self.assertEqual(result.text, correction)
        self.assertNotIn('CPython uses separate chaining', result.text)
        self.assertEqual(client.generate_json.call_count, 2)
        feedback = json.loads(client.generate.call_args.args[0])['feedback']
        self.assertTrue(feedback['corrections'])
        self.assertFalse(result.verified)

    def test_multiple_reported_claim_types_are_withheld_on_negative_reviews(self):
        # Authored examples based on the manually inspected failure; these
        # assertions test enforcement of a verdict, not a model detecting errors.
        for bad in ('Every dictionary lookup always takes constant time.',
                    'All Python dictionary keys must be immutable objects.',
                    'A normal Python list can be inserted as a dictionary key.',
                    'SipHash is a non-cryptographic hash function.'):
            with self.subTest(bad=bad):
                client = self.client([bad, bad], [REJECT])
                result = background_lesson(client, 'Explain hashing in 2000 words', prose(1100), response_request('in 2000 words'))
                self.assertIsNone(result)
                self.assertEqual(client.generate.call_count, 2)
                self.assertEqual(client.generate_json.call_count, 1)

    def test_different_rejected_revision_is_not_retried_for_approval(self):
        client = self.client(['A technical error.', 'A different technical error.'], [REJECT, REJECT])
        self.assertIsNone(background_lesson(client, 'in 2000 words', prose(1100), response_request('in 2000 words')))
        self.assertEqual(client.generate.call_count, 2)
        self.assertEqual(client.generate_json.call_count, 2)

    def test_bad_or_unavailable_review_cannot_publish_a_background(self):
        for verdict in ({**ACCEPT, 'accurate': 'yes'}, {**ACCEPT, 'issues': ['Conflicting review.']},
                        {**REJECT, 'issues': []}, RuntimeError('PRIVATE_PROVIDER_DETAILS')):
            with self.subTest(verdict=verdict):
                client = self.client([prose(800)], [verdict])
                with self.assertLogs('backend.ai.summary_background', 'WARNING') as logs:
                    result = background_lesson(client, 'in 2000 words', prose(1100), response_request('in 2000 words'))
                self.assertIsNone(result)
                self.assertNotIn('PRIVATE', '\n'.join(logs.output))
                self.assertEqual(client.generate.call_count, 1)

    def test_depth_and_untrusted_context_reach_the_reviewer(self):
        client = self.client([prose(900)])
        background_lesson(client, 'in 2000 words', prose(1100), response_request('in 2000 words'), depth='beginner')
        prompt = client.generate_json.call_args.args[0]
        payload = json.loads(prompt.split('\nDATA: ', 1)[1])
        self.assertEqual(payload['depth'], 'beginner')
        self.assertIn('untrusted data', prompt)
        self.assertIn('not verification against external sources', prompt)
        self.assertTrue(BackgroundReview.model_validate(ACCEPT).acceptable)
