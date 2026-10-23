"""No-credit audit checks with controlled reviewer responses, never code execution."""
import json
import copy
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from backend.agents.code_review import REVIEW_SYSTEM, Review, review_payload
from evaluation import code_quality as audit


class ReviewerAudit(unittest.TestCase):
    def client(self, response=None):
        return Mock(model_name='test-model', reasoning_effort='none',
                    generate_json=Mock(return_value=response or dict.fromkeys(Review.model_fields, True)))

    def test_eight_bounded_requests_separate_model_and_guard_misses(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'
            client = self.client()
            with patch('backend.agents.sandbox.execute') as execute:
                packet = audit.collect(path, lambda model: client)
            execute.assert_not_called()
            self.assertEqual(client.generate_json.call_count, 8)
            self.assertEqual(packet, json.loads(path.read_text()))
            self.assertEqual(packet['version'], 2)
            self.assertTrue(all(row['human_label'] is None for row in packet['records']))
            for call in client.generate_json.call_args_list:
                self.assertEqual(call.kwargs, {'max_retries': 1, 'system_prompt': REVIEW_SYSTEM})
                payload = json.loads(call.args[0])
                self.assertFalse(payload['artifact_contents_available'])
                self.assertEqual(payload['output_schema'], Review.model_json_schema())
            scores = audit.scores(packet)
            self.assertEqual(scores['model_verdict']['false_acceptances'], 4)
            # CSV arithmetic requires the model; local search-pattern checks do not prove it.
            self.assertEqual(scores['effective_verdict']['false_acceptances'], 1)
            self.assertEqual(scores['effective_verdict']['agreement'], 7/8)
            self.assertEqual(audit.scores(packet, 'human_label')['labelled'], 0)

    def test_existing_packet_is_preserved_before_client_setup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'
            path.write_text('keep this')
            factory = Mock()
            with self.assertRaises(FileExistsError):
                audit.collect(path, factory)
            factory.assert_not_called()
            self.assertEqual(path.read_text(), 'keep this')

    def test_duplicate_reference_distinguishes_linear_first_match_from_binary_any(self):
        rows = {row['id']: row for row in audit.cases()}
        answer = rows['duplicates-good']['request']['draft_answer']
        self.assertIn('linear scan returns the first matching index', answer)
        self.assertIn('binary search can return any matching index', answer)
        self.assertNotIn('neither guarantees', answer)
        self.assertEqual(audit.fixture_warnings({'records': list(rows.values())}), [])

    def test_legacy_flawed_reference_is_disclosed_without_rewriting_or_human_labels(self):
        packet = {'version': 1, 'records': audit.cases()}
        row = next(row for row in packet['records'] if row['id'] == 'duplicates-good')
        row['request']['draft_answer'] = 'The algorithms accept duplicates; neither guarantees the first or last occurrence.'
        before = copy.deepcopy(packet)
        self.assertTrue(audit.fixture_warnings(packet))
        self.assertEqual(packet, before)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'
            path.write_text(json.dumps(packet))
            raw = path.read_text()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(audit.main(['--packet', str(path)]), 0)
            summary = json.loads(output.getvalue())
            self.assertEqual(summary['fixture_reference_status'], 'known_flawed')
            self.assertEqual(summary['human_comparison']['labelled'], 0)
            self.assertEqual(path.read_text(), raw)

    def test_errors_and_invalid_model_payload_are_redacted_and_checkpointed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'
            client = self.client()
            client.generate_json.side_effect = [RuntimeError('SECRET https://private.example'),
                                                {'results': 'SECRET'}] + [dict.fromkeys(Review.model_fields, True)]*6
            packet = audit.collect(path, lambda model: client)
            self.assertNotIn('SECRET', path.read_text())
            self.assertNotIn('private.example', path.read_text())
            self.assertEqual([row.get('error') for row in packet['records'][:2]], ['review_unavailable']*2)
            self.assertEqual(audit.scores(packet)['model_verdict']['unknown'], 2)
            self.assertEqual(client.generate_json.call_count, 8)

    def test_each_request_has_a_checkpoint_before_the_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'
            client = self.client()
            counts = []
            def respond(*args, **kwargs):
                packet = json.loads(path.read_text())
                counts.append(sum('model_verdict' in row for row in packet['records']))
                return dict.fromkeys(Review.model_fields, True)
            client.generate_json.side_effect = respond
            audit.collect(path, lambda model: client)
            self.assertEqual(counts, list(range(8)))

    def test_human_labels_require_explicit_valid_case_and_label(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'
            audit.collect(path, lambda model: self.client())
            before = path.read_text()
            for case_id, label in [('missing', 'supported'), ('csv-bad', 'invented')]:
                with self.assertRaises(ValueError):
                    audit.label_case(path, case_id, label)
                self.assertEqual(path.read_text(), before)
            packet = audit.label_case(path, 'csv-bad', 'unsupported')
            self.assertEqual(audit.scores(packet, 'human_label')['labelled'], 1)
            self.assertEqual(audit.scores(packet, 'human_label')['model_verdict']['false_acceptances'], 1)
            self.assertIsNotNone(next(row for row in packet['records'] if row['id']=='csv-bad')['human_reviewed_at'])

    def test_setup_failure_has_no_raw_configuration_or_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'packet.json'
            packet = audit.collect(path, Mock(side_effect=RuntimeError('SECRET')))
            self.assertEqual(packet['setup_error'], 'client_configuration_failed')
            self.assertNotIn('SECRET', path.read_text())
            self.assertEqual(audit.scores(packet)['model_verdict']['unknown'], 8)

    def test_payload_uses_the_production_compaction_and_latest_execution(self):
        old = {'tool':'code_execute', 'executed_program':'old', 'data':{'stdout':'old'}}
        new = {'tool':'code_execute', 'executed_program':'x'*6001,
               'data':{'stdout':'y'*4097, 'artifacts':[{'name':'out.json','data':'SECRET'}]}}
        payload = review_payload('No result claimed.', 'Goal', [old, new])
        self.assertEqual(len(payload['evidence']), 1)
        evidence = payload['evidence'][0]
        self.assertTrue(evidence['program_truncated'])
        self.assertTrue(evidence['data']['stdout_truncated'])
        self.assertNotIn('SECRET', json.dumps(payload))

    def test_production_configuration_bounds_requests_and_output(self):
        client = self.client()
        client.read_timeout = 120
        client.for_task.return_value = client
        client.for_summary.return_value = client
        client.for_verification.return_value = client
        client.with_output_budget.return_value = client
        with patch('backend.ai.llm.LLM', return_value=client):
            result = audit.production_client('chosen-model')
        self.assertEqual(result.model_name, 'chosen-model')
        self.assertEqual(result.read_timeout, 30)
        client.for_task.assert_called_once_with('answer')
        client.with_output_budget.assert_called_once_with(1024, exact=True)
