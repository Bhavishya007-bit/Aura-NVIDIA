"""Malformed visual output recovery; no local/hosted model or student images."""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException
from PIL import Image
import requests

from backend.figure_tools import interpret_image, vision_json
from backend.multi_image_tutor import images_tutor_answer
from backend.vision_contracts import ImageDraft, VisionOutputError


QUESTION = 'Explain the relationship shown in this authored image.'


def answer():
    return {'answerable': True, 'observations': ['A points to B.'],
            'explanation': 'The arrow connects A to B.', 'limitations': []}


def response(content, *, done_reason='stop'):
    value = Mock()
    value.json.return_value = {'message': {'content': content}, 'done_reason': done_reason}
    return value


class VisionContractChecks(unittest.TestCase):
    def test_http_transport_supplies_required_schema_instead_of_only_json_mode(self):
        schema = ImageDraft.model_json_schema()
        with patch.dict('os.environ', {'OLLAMA_VISION_MODEL': 'fixture'}), \
             patch('backend.figure_tools.requests.post', return_value=response(json.dumps(answer()))) as post:
            self.assertEqual(vision_json(b'fixture-image', QUESTION, output_schema=schema), answer())
        sent = post.call_args.kwargs['json']
        self.assertEqual(sent['format'], schema)
        self.assertEqual(set(sent['format']['required']), {'answerable', 'observations', 'explanation', 'limitations'})
        self.assertEqual(sent['format']['properties']['answerable']['type'], 'boolean')
        self.assertFalse(sent['format']['additionalProperties'])

    def test_missing_fields_repair_and_then_review_with_same_image_and_question(self):
        for field in ('answerable', 'observations', 'explanation', 'limitations'):
            bad = answer(); bad.pop(field)
            with self.subTest(field=field), patch('backend.figure_tools.vision_json',
                    side_effect=[bad, answer(), {'supported': True}]) as model:
                result = interpret_image(b'fixture-image', QUESTION)
            self.assertTrue(result['answerable'])
            self.assertEqual(model.call_count, 3)
            for call in model.call_args_list:
                self.assertEqual(call.args[0], b'fixture-image')
                self.assertIn(QUESTION, call.args[1])
                self.assertIsInstance(call.kwargs['output_schema'], dict)
            self.assertIn(field, model.call_args_list[1].args[1])

    def test_wrong_types_and_empty_evidence_are_repaired_not_coerced(self):
        variants = []
        bad = answer(); bad['answerable'] = 'true'; variants.append(bad)
        bad = answer(); bad['observations'] = [{'text': 'A points to B.'}]; variants.append(bad)
        bad = answer(); bad['observations'] = []; variants.append(bad)
        bad = answer(); bad['explanation'] = '   '; variants.append(bad)
        bad = answer(); bad['limitations'] = None; variants.append(bad)
        for bad in variants:
            with self.subTest(bad=bad), patch('backend.figure_tools.vision_json',
                    side_effect=[bad, answer(), {'supported': True}]) as model:
                result = interpret_image(b'fixture-image', QUESTION)
            self.assertEqual(model.call_count, 3)
            self.assertEqual(result['observations'], ['A points to B.'])

    def test_two_invalid_outputs_stop_without_publishing_or_inventing_evidence(self):
        with patch('backend.figure_tools.vision_json', return_value={'explanation': 'Unapproved answer'}) as model:
            with self.assertRaises(HTTPException) as error:
                interpret_image(b'fixture-image', QUESTION)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(model.call_count, 2)
        self.assertNotIn('Unapproved answer', error.exception.detail)

    def test_schema_and_sql_repair_share_one_retry_budget(self):
        incomplete = answer(); incomplete.pop('answerable')
        with patch('backend.figure_tools.vision_json', side_effect=[incomplete, answer()]) as model:
            with self.assertRaises(HTTPException):
                interpret_image(b'fixture-image', 'Write an SQL statement to find the matching row.')
        self.assertEqual(model.call_count, 2)

    def test_malformed_json_is_recovered_through_real_http_serialization(self):
        replies = [response('{"explanation":'), response(json.dumps(answer())), response('{"supported":true}')]
        with patch.dict('os.environ', {'OLLAMA_VISION_MODEL': 'fixture'}), \
             patch('backend.figure_tools.requests.post', side_effect=replies) as post:
            result = interpret_image(b'fixture-image', QUESTION)
        self.assertTrue(result['answerable'])
        self.assertEqual(post.call_count, 3)
        payloads = [call.kwargs['json'] for call in post.call_args_list]
        self.assertEqual(payloads[0]['messages'][0]['images'], payloads[1]['messages'][0]['images'])
        self.assertEqual(payloads[0]['format'], payloads[1]['format'])
        self.assertEqual(payloads[2]['format']['properties']['supported']['type'], 'boolean')

    def test_truncated_valid_json_is_retried_instead_of_accepted(self):
        replies = [response(json.dumps(answer()), done_reason='length'),
                   response(json.dumps(answer())), response('{"supported":true}')]
        with patch.dict('os.environ', {'OLLAMA_VISION_MODEL': 'fixture'}), \
             patch('backend.figure_tools.requests.post', side_effect=replies) as post:
            result = interpret_image(b'fixture-image', QUESTION)
        self.assertTrue(result['answerable'])
        self.assertEqual(post.call_count, 3)

    def test_transport_failures_are_not_misdiagnosed_as_schema_errors(self):
        with patch.dict('os.environ', {'OLLAMA_VISION_MODEL': 'fixture'}), \
             patch('backend.figure_tools.requests.post', side_effect=requests.Timeout()) as post:
            with self.assertRaises(HTTPException) as error:
                interpret_image(b'fixture-image', QUESTION)
        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(post.call_count, 1)

    def test_review_boolean_is_never_defaulted_or_coerced_to_approval(self):
        for bad in ({'reason': 'Looks plausible'}, {'supported': 'true'}):
            with self.subTest(bad=bad), patch('backend.figure_tools.vision_json',
                    side_effect=[answer(), bad, bad]) as model:
                with self.assertRaises(HTTPException):
                    interpret_image(b'fixture-image', QUESTION)
            self.assertEqual(model.call_count, 3)
        with patch('backend.figure_tools.vision_json',
                side_effect=[answer(), {'reason': 'missing verdict'}, {'supported': False}]):
            result = interpret_image(b'fixture-image', QUESTION)
        self.assertFalse(result['answerable'])
        self.assertNotIn('The arrow connects A to B.', result['explanation'])

    def test_safe_diagnostics_contain_field_types_without_source_or_response_content(self):
        secret = 'PRIVATE-QUESTION-AND-MODEL-CONTENT'
        bad = {'answerable': 'yes', 'explanation': secret, secret: secret}
        with self.assertLogs('backend.vision_contracts', level='WARNING') as logs, \
             patch('backend.figure_tools.vision_json', return_value=bad):
            with self.assertRaises(HTTPException) as error:
                interpret_image(b'fixture-image', secret)
        output = '\n'.join(logs.output)
        self.assertIn('failure_code=schema_invalid', output)
        self.assertIn('answerable', output)
        self.assertIn('bool_type', output)
        self.assertIn('<field>', output)
        self.assertNotIn(secret, output + error.exception.detail)

    def test_grouped_images_recover_schema_without_losing_an_original(self):
        with tempfile.TemporaryDirectory() as folder:
            paths = [Path(folder) / f'authored-{n}.png' for n in (1, 2)]
            for path, color in zip(paths, ('red', 'blue')): Image.new('RGB', (20, 20), color).save(path)
            sources = [{'path': path, 'title': path.name} for path in paths]
            good = answer(); good['observations'] = [
                {'image': 1, 'text': 'The first source has A.'},
                {'image': 2, 'text': 'The second source has B.'}]
            bad = copy.deepcopy(good); bad.pop('answerable')
            with patch('backend.multi_image_tutor.owned_original', side_effect=sources), \
                 patch('backend.multi_image_tutor.vision_json',
                    side_effect=[bad, good, {'supported': True}]) as model:
                result = images_tutor_answer([7, 8], QUESTION, 42)
        self.assertEqual(model.call_count, 3)
        for call in model.call_args_list:
            self.assertEqual(len(call.args[0]), 2)
            self.assertEqual(Image.open(io.BytesIO(call.args[0][0])).getpixel((0, 0)), (255, 0, 0))
            self.assertEqual(Image.open(io.BytesIO(call.args[0][1])).getpixel((0, 0)), (0, 0, 255))
            self.assertIn(QUESTION, call.args[1])
            self.assertIsInstance(call.kwargs['output_schema'], dict)
        self.assertEqual([source['source_id'] for source in result['sources']], [7, 8])

    def test_invalid_envelope_is_an_output_error_not_an_attribute_error(self):
        reply = Mock(); reply.json.return_value = []
        with patch.dict('os.environ', {'OLLAMA_VISION_MODEL': 'fixture'}), \
             patch('backend.figure_tools.requests.post', return_value=reply):
            with self.assertRaises(VisionOutputError) as error:
                vision_json(b'fixture-image', QUESTION)
        self.assertEqual(error.exception.failure_code, 'invalid_json')
