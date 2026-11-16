import itertools
import json
import math
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from src.openrouter_paid import KeyBudgetError,validate_key_metadata,verify_key_budget
from scripts import milestone4b_paid_smoke as paid


def data(**changes):
    return dict(dict(limit=1,limit_remaining=1,usage=0,limit_reset=None),**changes)


class KeyBudgetDiagnosticTests(unittest.TestCase):
    def test_specific_codes_and_no_raw_values(self):
        scenarios=[
            (dict(limit=None),'KEY_LIMIT_UNCAPPED'),
            (dict(limit=0,limit_remaining=0),'KEY_LIMIT_ZERO'),
            (dict(limit_remaining=.199),'KEY_REMAINING_BUDGET_INSUFFICIENT'),
            (dict(limit_reset='daily'),'KEY_RESET_POLICY_NOT_ALLOWED'),
            (dict(limit_reset='null'),'KEY_RESET_POLICY_NOT_ALLOWED'),
            (dict(limit_reset=False),'KEY_RESET_POLICY_NOT_ALLOWED'),
            (dict(limit_remaining=1.1),'KEY_REMAINING_EXCEEDS_LIMIT'),
            (dict(usage=1.1),'KEY_USAGE_EXCEEDS_LIMIT'),
            (dict(usage=.01),'KEY_BUDGET_TOTAL_INCONSISTENT'),
            (dict(limit='0.10'),'KEY_LIMIT_METADATA_INVALID'),
            (dict(limit_remaining=None),'KEY_REMAINING_UNVERIFIABLE'),
            (dict(usage=None),'KEY_USAGE_UNVERIFIABLE'),
            (dict(limit=True),'KEY_LIMIT_METADATA_INVALID'),
            (dict(usage=-1),'KEY_USAGE_METADATA_INVALID'),
            (dict(limit=float('nan')),'KEY_LIMIT_METADATA_INVALID'),
            (dict(limit_remaining=float('inf')),'KEY_REMAINING_METADATA_INVALID'),
        ]
        for changes,code in scenarios:
            with self.subTest(changes=changes):
                with self.assertRaises(KeyBudgetError) as caught:
                    validate_key_metadata(dict(data(**changes),label='private-label',key='mock-secret'))
                self.assertEqual(str(caught.exception),code)
                self.assertNotIn('private',json.dumps(caught.exception.diagnostics))
                self.assertNotIn('mock-secret',json.dumps(caught.exception.diagnostics))

    def test_missing_fields_separate_from_null(self):
        for field,code in [('limit','KEY_LIMIT_METADATA_MISSING'),
                ('limit_remaining','KEY_REMAINING_METADATA_MISSING'),('usage','KEY_USAGE_METADATA_MISSING'),
                ('limit_reset','KEY_RESET_METADATA_MISSING')]:
            sample=data();del sample[field]
            with self.assertRaises(KeyBudgetError) as caught:validate_key_metadata(sample)
            self.assertEqual(str(caught.exception),code)
        self.assertEqual(validate_key_metadata(data())['status'],'PASS')

    def test_all_failed_original_predicates_preserved(self):
        with self.assertRaises(KeyBudgetError) as caught:
            validate_key_metadata(data(limit=1,limit_reset='monthly',limit_remaining=2,usage=2))
        self.assertEqual(caught.exception.diagnostics['failed_checks'],[
            'KEY_RESET_POLICY_NOT_ALLOWED',
            'KEY_REMAINING_EXCEEDS_LIMIT','KEY_USAGE_EXCEEDS_LIMIT','KEY_BUDGET_TOTAL_INCONSISTENT'])

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':'mock-secret'})
    @patch('src.openrouter_paid.build_opener')
    def test_json_null_and_string_null_round_trip(self,opener):
        response=opener.return_value.open.return_value.__enter__.return_value
        response.read.return_value=json.dumps(dict(data=data())).encode()
        self.assertIsNone(verify_key_budget()['limit_reset'])
        response.read.return_value=json.dumps(dict(data=data(limit_reset='null'))).encode()
        with self.assertRaises(KeyBudgetError) as caught:verify_key_budget()
        self.assertEqual(caught.exception.diagnostics['reset_state'],'string_null')
        response.read.return_value=json.dumps(dict(data=data(limit=None))).encode()
        with self.assertRaisesRegex(KeyBudgetError,'KEY_LIMIT_UNCAPPED'):verify_key_budget()

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':'mock-secret'})
    @patch('src.openrouter_paid.build_opener')
    def test_unverifiable_response_shapes(self,opener):
        response=opener.return_value.open.return_value.__enter__.return_value
        for body in ['invalid json','null','[]','{}','{"data":null}','{"data":[]}']:
            response.read.return_value=body.encode()
            with self.assertRaisesRegex(KeyBudgetError,'KEY_METADATA_RESPONSE_INVALID'):verify_key_budget()

    def test_approved_policy_boundary_combinations(self):
        # Updated authorization separates key cap from internal budget. Preserve
        # finite numbers, no-reset policy and the existing consistency tolerance.
        from decimal import Decimal
        def approved_accepts(sample):
            try:
                values=[sample.get(k) for k in ('limit','limit_remaining','usage')]
                if any(type(v) not in (int,float) or not math.isfinite(v) or v<0 for v in values):return False
                limit,remaining,usage=map(lambda v:Decimal(str(v)),values)
                return ('limit_reset' in sample and sample['limit_reset'] is None
                    and 0<limit and remaining<=limit and usage<=limit
                    and remaining+usage<=limit+Decimal('.000001') and remaining>=Decimal('.20'))
            except Exception:return False
        for limit,remaining,usage,reset in itertools.product(
                [None,0,.1,1,9,10,'0.1',True],
                [None,0,.199,.2,1,9],
                [0,.000001,.0000011,.01,.11], [None,'null','daily']):
            sample=data(limit=limit,limit_remaining=remaining,usage=usage,limit_reset=reset)
            try:validate_key_metadata(sample);accepted=True
            except RuntimeError:accepted=False
            self.assertEqual(accepted,approved_accepts(sample),sample)

    @patch('src.llm.build_opener')
    def test_runner_saves_diagnostics_without_raw_metadata(self,opener):
        with tempfile.TemporaryDirectory() as directory:
            output=Path(directory)/'diagnosis.json'
            argv=['paid','--mode','key-preflight','--resume-from','unused','--output',str(output)]
            def fail():
                return validate_key_metadata(dict(data(limit_reset='mock-secret'),label='private-label'))
            with patch('sys.argv',argv),patch.object(paid,'validate_paid_resume',return_value='digest'), \
                    patch.object(paid,'verify_key_budget',side_effect=fail),patch.object(paid,'prepare') as prepare:
                self.assertEqual(paid.main(),1)
                prepare.assert_not_called()
            report=json.loads(output.read_text())
            self.assertEqual(report['errors'],['KEY_RESET_POLICY_NOT_ALLOWED'])
            self.assertEqual(report['key_budget_diagnostics']['reset_state'],'non_null')
            self.assertEqual(report['llm_calls_this_run'],0)
            self.assertEqual(report['remaining_llm_calls'],4)
            self.assertNotIn('mock-secret',output.read_text())
            self.assertNotIn('private-label',output.read_text())
            opener.assert_not_called()
