"""Controlled terminal interaction tests, never labels for real collected files."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from evaluation.review_calibration import review


def packet():
    fixture = json.loads(Path(__file__).with_name('calibration_cases.json').read_text())
    return {'mode': 'live_synthetic', 'model': 'controlled-test', 'passages': fixture['passages'],
            'records': [{**row, 'predicted': row['reference_label'], 'human_label': None,
                         'reviewed_by': None, 'decision': {'reason': 'HIDDEN_MODEL_REASON'}} for row in fixture['cases']]}


class HumanReview(unittest.TestCase):
    def test_every_saved_label_requires_input_and_model_verdicts_remain_hidden(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'
            original = packet(); path.write_text(json.dumps(original))
            # These are controlled test choices, not independent human judgments.
            answers = iter(['n']*30); output = []
            with patch('backend.ai.llm.LLM') as llm, patch('backend.agents.sandbox.execute') as execute:
                result = review(path, ask=lambda prompt: next(answers), write=output.append)
            llm.assert_not_called(); execute.assert_not_called()
            saved = json.loads(path.read_text())
            self.assertEqual(result['reviewed'], 30)
            self.assertFalse(result['ready'])  # The tool does not replace choices with references.
            self.assertTrue(all(row['human_label']=='not_covered' and row['reviewed_by']=='human' and row['reviewed_at'] for row in saved['records']))
            for before, after in zip(original['records'], saved['records']):
                self.assertEqual({k:v for k,v in after.items() if k not in ('human_label','reviewed_by','reviewed_at')},
                                 {k:v for k,v in before.items() if k not in ('human_label','reviewed_by','reviewed_at')})
            displayed = '\n'.join(output)
            self.assertNotIn('HIDDEN_MODEL_REASON', displayed)
            self.assertNotIn('reference_label', displayed)
            self.assertNotIn('predicted', displayed)
            self.assertIn(original['passages'][0]['text'], displayed)

    def test_quit_resumes_without_relabelling_saved_cases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'; path.write_text(json.dumps(packet()))
            choices = iter(['f', 'q'])
            first = review(path, ask=lambda prompt: next(choices), write=lambda value: None)
            self.assertEqual(first['reviewed'], 1)
            saved = json.loads(path.read_text())['records'][0]
            output = []; choices = iter(['p', 'q'])
            second = review(path, ask=lambda prompt: next(choices), write=output.append)
            self.assertEqual(second['reviewed'], 2)
            self.assertEqual(json.loads(path.read_text())['records'][0], saved)
            self.assertNotIn('Question cal-01:', '\n'.join(output))
            self.assertIn('Question cal-02:', '\n'.join(output))

    def test_eof_and_interrupt_do_not_invent_labels_or_change_the_file(self):
        for error in (EOFError, KeyboardInterrupt):
            with self.subTest(error=error), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'packet.json'; path.write_text(json.dumps(packet()))
                original = path.read_bytes()
                result = review(path, ask=Mock(side_effect=error), write=lambda value: None)
                self.assertEqual(result['reviewed'], 0)
                self.assertEqual(path.read_bytes(), original)

    def test_invalid_input_never_defaults_to_a_reference_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'; path.write_text(json.dumps(packet()))
            original = path.read_bytes(); choices = iter(['', 'yes', 'supported', 'q'])
            review(path, ask=lambda prompt: next(choices), write=lambda value: None)
            self.assertEqual(path.read_bytes(), original)

    def test_incomplete_duplicate_or_changed_fixture_is_rejected_before_input(self):
        values = []
        short = packet(); short['records'].pop(); values.append(short)
        duplicate = packet(); duplicate['records'][-1]['id'] = 'cal-01'; values.append(duplicate)
        changed = packet(); changed['passages'][0]['text'] = 'Changed context'; values.append(changed)
        changed = packet(); changed['records'][0]['question'] = 'Changed question'; values.append(changed)
        changed = packet(); changed['mode'] = 'controlled_offline'; values.append(changed)
        for value in values:
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory)/'packet.json'; path.write_text(json.dumps(value)); original = path.read_bytes()
                ask = Mock()
                with self.assertRaises(ValueError): review(path, ask=ask, write=lambda value: None)
                ask.assert_not_called(); self.assertEqual(path.read_bytes(), original)

    def test_external_change_is_preserved_instead_of_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'; value = packet(); path.write_text(json.dumps(value))
            external = copy.deepcopy(value); external['note'] = 'Changed in another editor'
            def choose(prompt):
                path.write_text(json.dumps(external)); return 'f'
            with self.assertRaises(ValueError): review(path, ask=choose, write=lambda value: None)
            self.assertEqual(json.loads(path.read_text()), external)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])

    def test_failed_checkpoint_preserves_last_successful_judgment(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'; path.write_text(json.dumps(packet())); original = path.read_bytes()
            with patch('evaluation.review_calibration.os.replace', side_effect=OSError('not writable')):
                with self.assertRaises(OSError): review(path, ask=lambda prompt: 'f', write=lambda value: None)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(list(Path(directory).glob('*.tmp')), [])
