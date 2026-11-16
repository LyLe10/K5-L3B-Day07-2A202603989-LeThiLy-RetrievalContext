"""Offline design, real recorded-action replay and mock-HTTP contract checks."""
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.prepare_improvement_experiments import (
    ROOT, E1_SYSTEM, SYSTEM, experiment_config, prepare, read, reconcile_ledger, replay)
from scripts.milestone4b_smoke import ByteBudget
from src.agent import run_agent
from src.llm import OpenRouterController, PAID_MODEL
from tests.test_dev_readiness import CHUNK


class ImprovementExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest, cls.readiness = prepare()

    def test_disjoint_changes_and_exact_paired_dev_ids(self):
        m = self.manifest
        self.assertFalse(m['combine_e1_e2'])
        self.assertEqual(len(set(m['case_ids'])), 17)
        for name, config in m['experiments'].items():
            self.assertEqual(config['case_ids'], m['case_ids'])
            self.assertEqual(config['paired_against'], 'reviewed_DEV17_5C3C')
        self.assertEqual(experiment_config('E1'), experiment_config('E2') | {'max_searches': 2})
        self.assertEqual(m['experiments']['E1']['config']['max_searches'], 2)
        self.assertNotEqual(E1_SYSTEM, SYSTEM)
        self.assertEqual(m['experiments']['E2']['system_prompt'], SYSTEM)
        with self.assertRaises(ValueError): experiment_config('E1+E2')

    def test_replay_seventeen_cases_is_not_new_inference_or_grading(self):
        r = self.readiness
        self.assertEqual(r['baseline_replay_cases'], 17)
        self.assertEqual(r['new_api_calls'], 0)
        self.assertFalse(r['paid_execution_ready'])
        rows = {x['query_id']: x for x in r['replay']}
        self.assertEqual(rows['dev-02']['baseline_replay']['termination'], 'invalid_or_missing_citations')
        self.assertEqual(rows['dev-09']['baseline_replay']['status'], 'answered')
        self.assertNotIn('answer_grade', json.dumps(r))
        for row in rows.values():
            self.assertLessEqual(row['e2_conditional_replay']['replayed_retrievals'], 1)
            self.assertLessEqual(row['e2_conditional_replay']['replayed_decisions'], 2)
        self.assertEqual(rows['dev-01']['baseline_replay']['status'], 'answered')
        self.assertEqual(rows['dev-01']['e2_conditional_replay']['termination'], 'search_limit')
        for case in ('dev-16', 'dev-17'):
            self.assertEqual(rows[case]['e2_conditional_replay']['termination'], 'search_limit')

    def test_replay_fails_on_changed_recorded_question_prefix(self):
        t = deepcopy(read(ROOT/'results/milestone5c3c_dev17_traces.json')[0])
        next(e for e in t['events'] if e['event'] == 'search')['query'] = 'tampered'
        with self.assertRaisesRegex(ValueError, 'REPLAY_FAILED'): replay(t, 2)

    def test_accounting_separates_actual_and_retained_reservation(self):
        a = self.manifest['accounting']
        self.assertEqual(a['baseline_requests'], 37)
        self.assertEqual(a['actual_provider_cost_usd'], '0.00432165')
        self.assertEqual(a['retained_reservations_usd'], '0.148')
        self.assertEqual(a['old_remaining_after_reservations_usd'], '0.102')
        self.assertEqual(a['proposed_separate_experiment_budget_usd'], '0.340')
        self.assertFalse(a['approved'])
        self.assertFalse(a['old_reservations_released'])
        for name, cap in [('E1', 51), ('E2', 34)]:
            self.assertEqual(self.manifest['experiments'][name]['limits']['requests'], cap)

    def test_unresolved_duplicate_and_unknown_cost_fail_closed(self):
        allocation = dict(event='allocation')
        reserve = dict(event='reserve', request=1, reserved_usd='0.004')
        outcome = dict(event='outcome', request=1, cost_usd='0.001', status='error')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'journal.jsonl'
            for rows, message in [([allocation, reserve], 'UNRESOLVED'),
                ([allocation, reserve, reserve, outcome], 'DUPLICATE'),
                ([allocation, reserve, dict(outcome, cost_usd=None)], 'UNKNOWN')]:
                path.write_text('\n'.join(json.dumps(r) for r in rows))
                with self.assertRaisesRegex(ValueError, message): reconcile_ledger(path)
            path.write_text('\n'.join(json.dumps(r) for r in [allocation, reserve, outcome]))
            # Error requests consume accounting too; no retry or refund inferred.
            self.assertEqual(reconcile_ledger(path)['calls'], 1)

    def test_unchanged_validator_rejects_format_but_does_not_prove_semantics(self):
        def run(action, failure=None):
            class Controller:
                calls = 0
                def decide(self, question, history):
                    self.calls += 1
                    if failure: raise failure
                    return dict(action='search', query='unit') if not history else action
            class Retriever:
                def search(self, query, **kwargs): return [CHUNK]
            return run_agent('unit question', Controller(), Retriever(), max_searches=2,
                top_k=3, budget=12000, count_tokens=ByteBudget())
        invalid = run(dict(action='answer', answer='Claim without inline citation', citations=['synthetic']))
        self.assertEqual(invalid['events'][-1]['event'], 'invalid_or_missing_citations')
        unknown = run(dict(action='answer', answer='Claim [unknown]', citations=['unknown']))
        self.assertEqual(unknown['status'], 'abstain')
        semantic = run(dict(action='answer', answer='Unsupported extra detail [synthetic]', citations=['synthetic']))
        self.assertEqual(semantic['status'], 'answered')  # Manual review must still reject support.
        insufficient = run(dict(action='answer', answer='', citations=[]))
        self.assertEqual(insufficient['events'][-1]['event'], 'insufficient_evidence')
        self.assertEqual(run({}, TimeoutError())['status'], 'error')
        self.assertEqual(run({}, RuntimeError())['status'], 'error')

    @patch.dict(os.environ, {'OPENROUTER_API_KEY': 'offline-mock-only'})
    @patch('src.llm.build_opener')
    def test_mock_http_prompt_is_only_payload_difference(self, opener):
        body = dict(choices=[dict(finish_reason='stop', message=dict(content=json.dumps(
            dict(action='search', query='unit query'))))], usage=dict(cost=0))
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(body).encode()
        payloads = []
        for prompt in (SYSTEM, E1_SYSTEM):
            guard_calls = []
            def guard(): guard_calls.append(True)
            with patch('src.llm.SYSTEM', prompt):  # Scoped test override, not a production runner.
                OpenRouterController(PAID_MODEL, request_guard=guard).decide('unit question', [])
            self.assertEqual(len(guard_calls), 1)
            payloads.append(json.loads(opener.return_value.open.call_args.args[0].data))
        self.assertEqual(payloads[1]['messages'][0]['content'], E1_SYSTEM)
        payloads[1]['messages'][0]['content'] = SYSTEM
        self.assertEqual(payloads[0], payloads[1])
        self.assertEqual(opener.return_value.open.call_count, 2)
        self.assertEqual(payloads[0]['max_tokens'], 512)
        self.assertFalse(payloads[0]['provider']['allow_fallbacks'])


if __name__ == '__main__':
    unittest.main()
