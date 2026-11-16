import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from scripts import dev_improvement_experiment as runner
from scripts.prepare_improvement_experiments import E1_SYSTEM, SYSTEM
from scripts.dev_retrieval_benchmark import load_frozen_dev
from src.llm import OpenRouterController, PAID_MODEL
from tests.test_dev_readiness import CHUNK


def header(arm='E1', ids=('dev-unit-1', 'dev-unit-2')):
    pin = runner.validate_dependencies()
    return dict(event='allocation', experiment=arm, model=PAID_MODEL, case_ids=list(ids),
        code_sha256=pin['code_sha256'], day6_code_sha256=pin['day6_code_sha256'],
        day6_root=pin['day6_root'], dependency_pin_sha256=runner.digest(runner.DEPENDENCY_PIN),
        config=dict(max_searches=2 if arm == 'E1' else 1),
        limits=dict(requests=51 if arm == 'E1' else 34,
            requests_per_case=3 if arm == 'E1' else 2, retrievals_per_case=2 if arm == 'E1' else 1),
        envelope_usd='0.204' if arm == 'E1' else '0.136')


def initialize(directory, h):
    directory = Path(directory)
    (directory/'checkpoints').mkdir()
    runner.write_new(directory/'identity.json', h)
    runner.append_record(directory/'requests.jsonl', h)


@patch.dict(os.environ, {'OPENROUTER_API_KEY': 'synthetic-unit-key'})
class ImprovementRunnerTests(unittest.TestCase):
    def test_e1_prompt_is_generic_addition_without_dev_gold_or_examples(self):
        self.assertTrue(E1_SYSTEM.startswith(SYSTEM+'\n'))
        _, cases, _ = load_frozen_dev(runner.ROOT/'data/benchmark/dev.json')
        for case in cases:
            self.assertNotIn(case['id'], E1_SYSTEM)
            self.assertNotIn(case['question'], E1_SYSTEM)
            if case.get('expected_answer'):
                self.assertNotIn(case['expected_answer'], E1_SYSTEM)
            for gold in case.get('gold', []):
                self.assertNotIn(gold['chunk_id'], E1_SYSTEM)
                self.assertNotIn(gold['evidence'], E1_SYSTEM)

    def budget(self, directory, h):
        b = runner.ExperimentBudget(directory, h, verify=MagicMock())
        b.case_id = h['case_ids'][0]
        return b

    def settle(self, b, **changes):
        trace = dict(status='ok', actual_model=PAID_MODEL,
            usage=dict(cost=.00001, prompt_tokens=50, completion_tokens=10, total_tokens=60))
        trace.update(changes)
        b.outcome(trace)

    def opener_response(self, opener):
        def respond(request, **kwargs):
            p = json.loads(request.data)
            history = json.loads(p['messages'][1]['content'])['retrieval_history']
            action = dict(action='answer', answer='Evidence [synthetic]', citations=['synthetic']) if history else dict(action='search', query='unit query')
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(dict(model=PAID_MODEL,
                choices=[dict(finish_reason='stop', message=dict(content=json.dumps(action)))],
                usage=dict(cost=.00001, prompt_tokens=50, completion_tokens=10, total_tokens=60))).encode()
            return response
        opener.return_value.open.side_effect = respond

    def test_e1_e2_request_and_reservation_limits(self):
        for arm, requests, envelope in [('E1', 51, '0.204'), ('E2', 34, '0.136')]:
            h = header(arm)
            self.assertEqual(h['limits']['requests'], requests)
            self.assertEqual(h['envelope_usd'], envelope)
            with tempfile.TemporaryDirectory() as directory:
                initialize(directory, h)
                b = self.budget(directory, h)
                for _ in range(h['limits']['requests_per_case']):
                    b.before_request(); self.settle(b)
                with self.assertRaisesRegex(RuntimeError, 'REQUEST_LIMIT'):
                    b.before_request()
                self.assertEqual(b.calls, h['limits']['requests_per_case'])

    def test_global_request_and_usd_guards(self):
        for change, reason in [(dict(limits=dict(requests=0, requests_per_case=3)), 'REQUEST_LIMIT'),
                               (dict(envelope_usd='0.003'), 'USD_LIMIT')]:
            h = header(); h.update(change)
            with tempfile.TemporaryDirectory() as directory:
                initialize(directory, h)
                b = self.budget(directory, h)
                with self.assertRaisesRegex(RuntimeError, reason): b.before_request()
                self.assertEqual(b.calls, 0)
                b.verify.assert_not_called()

    def test_key_check_failure_and_key_change_do_not_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            h = header(); initialize(directory, h); b = self.budget(directory, h)
            b.verify.side_effect = RuntimeError('KEY_LIMIT_UNCAPPED')
            with self.assertRaisesRegex(RuntimeError, 'KEY_LIMIT'): b.before_request()
            self.assertEqual(b.calls, 0)
            with patch.dict(os.environ, {'OPENROUTER_API_KEY':'different-synthetic-key'}):
                with self.assertRaisesRegex(RuntimeError, 'KEY_CHANGED'): b.before_request()

    def test_resume_blocks_unknown_request_or_partial_case(self):
        with tempfile.TemporaryDirectory() as directory:
            h = header(); initialize(directory, h); b = self.budget(directory, h)
            b.before_request()
            with self.assertRaisesRegex(RuntimeError, 'UNRESOLVED'):
                runner.ExperimentBudget(directory, h, verify=MagicMock())
            self.settle(b)
            with self.assertRaisesRegex(RuntimeError, 'PARTIAL_CASE'):
                runner.ExperimentBudget(directory, h, verify=MagicMock())
            self.assertEqual(runner.state(directory, h, active_case=b.case_id)['reserved'], runner.D('.004'))

    @patch('scripts.dev_improvement_experiment.build_opener')
    def test_reservation_is_durable_before_mock_http_and_payload_matches_baseline(self, opener):
        self.opener_response(opener)
        with tempfile.TemporaryDirectory() as directory:
            h = header(); initialize(directory, h); b = self.budget(directory, h)
            original = opener.return_value.open.side_effect
            def checked(request, **kwargs):
                rows = [json.loads(line) for line in (Path(directory)/'requests.jsonl').read_text().splitlines()]
                self.assertEqual(rows[-1]['event'], 'reserve')
                self.assertEqual(kwargs['timeout'], 60)
                return original(request, **kwargs)
            opener.return_value.open.side_effect = checked
            c = runner.ExperimentController(b, E1_SYSTEM)
            c.decide('unit question', [])
            payload = json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual(payload['messages'][0]['content'], E1_SYSTEM)
            self.assertEqual(payload['max_tokens'], 512)
            self.assertEqual(payload['temperature'], 0)
            self.assertFalse(payload['provider']['allow_fallbacks'])
            with patch('src.llm.build_opener') as baseline:
                self.opener_response(baseline)
                OpenRouterController(PAID_MODEL, request_guard=lambda:None).decide('unit question', [])
                base_payload = json.loads(baseline.return_value.open.call_args.args[0].data)
            payload['messages'][0]['content'] = SYSTEM
            self.assertEqual(payload, base_payload)

    @patch('scripts.dev_improvement_experiment.build_opener')
    def test_input_budget_stops_before_http_or_reservation(self, opener):
        with tempfile.TemporaryDirectory() as directory:
            h = header(); initialize(directory, h); b = self.budget(directory, h)
            c = runner.ExperimentController(b, E1_SYSTEM)
            with self.assertRaisesRegex(RuntimeError, 'INPUT_BUDGET'):
                c.decide('x'*24001, [])
            opener.return_value.open.assert_not_called()
            self.assertEqual(b.calls, 0)

    @patch('scripts.dev_improvement_experiment.build_opener')
    def test_provider_errors_no_retry_and_no_resume(self, opener):
        for failure in [HTTPError('unit', 401, 'synthetic-unit-key', {}, io.BytesIO()),
                        HTTPError('unit', 402, 'unit', {}, io.BytesIO()),
                        HTTPError('unit', 429, 'unit', {}, io.BytesIO()),
                        HTTPError('unit', 503, 'unit', {}, io.BytesIO()), TimeoutError()]:
            opener.return_value.open.reset_mock()
            opener.return_value.open.side_effect = failure
            with tempfile.TemporaryDirectory() as directory:
                h = header(); initialize(directory, h); b = self.budget(directory, h)
                c = runner.ExperimentController(b, SYSTEM)
                with self.assertRaises((RuntimeError, TimeoutError)): c.decide('unit', [])
                self.assertEqual(b.calls, 1)
                self.assertTrue(b.stopped)
                self.assertEqual(opener.return_value.open.call_count, 1)
                self.assertNotIn('synthetic-unit-key', json.dumps(c.last_trace))
                with self.assertRaises(RuntimeError): runner.state(directory, h)
                with self.assertRaises(RuntimeError): c.decide('unit', [])
                self.assertEqual(opener.return_value.open.call_count, 1)

    @patch('scripts.dev_improvement_experiment.LexicalRetriever')
    @patch('scripts.dev_improvement_experiment.build_opener')
    def test_resume_skips_completed_cases_and_checkpoint_tamper_stops(self, opener, lexical):
        self.opener_response(opener)
        lexical.return_value.search.return_value = [CHUNK]
        lexical.return_value.last_trace = None
        with tempfile.TemporaryDirectory() as directory:
            h = header('E2'); initialize(directory, h); b = self.budget(directory, h)
            cases = [dict(id=cid, question=cid, answerable=True, split='dev',
                gold=[dict(source_id='unit', page=1, evidence='Synthetic evidence.')]) for cid in h['case_ids']]
            original = runner.checkpoint
            def stop_after_checkpoint(*args):
                original(*args)
                raise RuntimeError('SIMULATED_BETWEEN_CASE_INTERRUPTION')
            with patch.object(runner, 'checkpoint', side_effect=stop_after_checkpoint):
                with self.assertRaisesRegex(RuntimeError, 'SIMULATED'):
                    runner.evaluate(cases, [CHUNK], runner.ExperimentController(b, SYSTEM), b, directory, h)
            self.assertEqual(b.calls, 2)
            b2 = self.budget(directory, h)
            results = runner.evaluate(cases, [CHUNK], runner.ExperimentController(b2, SYSTEM), b2, directory, h)
            self.assertEqual(len(results), 2)
            self.assertEqual(b2.calls, 4)  # First completed case not executed/reserved again.
            self.assertEqual(runner.state(directory, h)['reserved'], runner.D('.016'))
            self.assertEqual(opener.return_value.open.call_count, 4)
            path = Path(directory)/'checkpoints'/(h['case_ids'][0]+'.json')
            path.write_text('{}')
            with self.assertRaises(Exception): runner.state(directory, h)

    def test_unknown_cost_overcharge_model_mismatch_stop(self):
        for changes in [dict(usage={}), dict(usage=dict(cost=.005, prompt_tokens=1, completion_tokens=1)),
                        dict(actual_model='unapproved')]:
            with tempfile.TemporaryDirectory() as directory:
                h = header(); initialize(directory, h); b = self.budget(directory, h)
                b.before_request()
                with self.assertRaisesRegex(RuntimeError, 'UNVERIFIED'): self.settle(b, **changes)
                self.assertTrue(b.stopped)
                with self.assertRaises(RuntimeError): runner.state(directory, h)

    def test_orphan_checkpoint_and_identity_mismatch_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            h = header(); initialize(directory, h)
            runner.write_new(Path(directory)/'checkpoints/orphan.json', {})
            with self.assertRaisesRegex(RuntimeError, 'ORPHAN'): runner.state(directory, h)
        with tempfile.TemporaryDirectory() as directory:
            h = header(); initialize(directory, h)
            other = header('E2')
            with self.assertRaisesRegex(RuntimeError, 'IDENTITY'): runner.state(directory, other)


if __name__ == '__main__':
    unittest.main()
