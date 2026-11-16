import json
import os
import sys
from contextlib import redirect_stderr
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts.dev_agent_evaluation import evaluate_agent_dev
from scripts.milestone5c_pilot import (CASE_IDS, HEADER, PilotBudget, PilotController,
    ledger_state, validate_catalog, main, offline_preflight)
from src.llm import PAID_MODEL
from src.openrouter_paid import validate_key_metadata
from tests.test_dev_readiness import CHUNK, cases
from tests.test_dev_agent_evaluation import MockController


def dev_cases():
    rows=cases()
    for i,row in enumerate(rows,1):row['id']=f'dev-{i:02d}'
    return rows


class PilotTests(unittest.TestCase):
    def test_paid_cli_requires_approval_and_fixed_ids_before_any_api(self):
        base=['pilot','--mode','run','--dev','unused','--day6-root','unused','--output','unused']
        with patch('scripts.milestone5c_pilot.offline_preflight') as offline:
            for argv in [base,base+['--approve-paid-pilot','--case-ids','dev-06','dev-04','test-07']]:
                with patch.object(sys,'argv',argv),redirect_stderr(StringIO()):
                    with self.assertRaises(SystemExit):main()
            offline.assert_not_called()

    @patch('scripts.milestone5c_pilot.verify_key_budget')
    @patch('scripts.milestone5c_pilot.check_catalog')
    @patch('scripts.milestone5c_pilot.load_offline_snapshot')
    @patch('scripts.milestone5c_pilot.load_frozen_dev')
    def test_offline_preflight_creates_new_unspent_ledger_without_network(self,frozen,snapshot,catalog,key):
        frozen.return_value=(b'',dev_cases(),dict(identity={}))
        snapshot.return_value=([CHUNK],{}, {})
        with tempfile.TemporaryDirectory() as root:
            ledger=Path(root)/'new5c.jsonl'
            report,_=offline_preflight(Path('dev.json'),Path('unused'),Path(root)/'report',ledger)
            self.assertEqual(report['accounted_llm_requests'],0)
            self.assertEqual(report['key_budget_verification'],'NOT_RUN_OFFLINE')
            self.assertEqual(report['live_price_verification'],'NOT_RUN_OFFLINE')
            self.assertEqual(ledger_state(ledger)['calls'],0)
        key.assert_not_called();catalog.assert_not_called()

    def budget(self,root):
        return PilotBudget(Path(root)/'new5c.jsonl',verify=MagicMock(return_value=dict(status='PASS')))

    def test_exact_three_case_ids_and_order_only(self):
        with tempfile.TemporaryDirectory() as root:
            c=MockController();retriever=MagicMock(spec=['search','last_trace'])
            retriever.search.return_value=[CHUNK];retriever.last_trace=None
            with patch('scripts.dev_agent_evaluation.LexicalRetriever',return_value=retriever):
                result=evaluate_agent_dev(dev_cases(),[CHUNK],c,output=Path(root)/'cases',
                    request_count=lambda:c.calls,case_ids=CASE_IDS)
            self.assertEqual([r['query_id'] for r in result['cases']],list(CASE_IDS))
            self.assertEqual(c.calls,6)
            self.assertEqual(retriever.search.call_count,3)
            for bad in [('dev-06','dev-04','test-07'),('dev-06',)*3,('dev-06',)]:
                with self.assertRaises(ValueError):
                    evaluate_agent_dev(dev_cases(),[CHUNK],c,output=Path(root)/'unused',
                        request_count=lambda:c.calls,case_ids=bad)
            self.assertEqual(c.calls,6)

    def test_shared_hard_nine_and_per_case_three_include_unsettled_requests(self):
        with tempfile.TemporaryDirectory() as root:
            b=self.budget(root)
            for cid in CASE_IDS:
                b.case_id=cid
                for _ in range(3):b.before_request()
                with self.assertRaises(RuntimeError):b.before_request()
            self.assertEqual(b.calls,9)
            self.assertEqual(str(ledger_state(b.path)['reserved']),'0.036')
            self.assertEqual(ledger_state(b.path)['reported_cost_calls'],0)
            with self.assertRaises(RuntimeError):b.before_request()
            self.assertEqual(b.verify.call_count,9)
            resumed=PilotBudget(b.path,verify=MagicMock())
            self.assertEqual(resumed.calls,9)
            resumed.case_id=CASE_IDS[0]
            with self.assertRaises(RuntimeError):resumed.before_request()

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':'mock-only-never-real'})
    @patch('src.llm.build_opener')
    def test_http_guard_before_post_failure_counted_once_no_retry(self,opener):
        for status in (401,402,429,500):
            with tempfile.TemporaryDirectory() as root:
                b=self.budget(root);c=PilotController(b,dev_cases())
                def failed_http(*args,**kwargs):
                    self.assertEqual(ledger_state(b.path)['calls'],1)
                    raise HTTPError('https://openrouter.ai/api/v1/chat/completions',status,'private',None,None)
                opener.return_value.open.side_effect=failed_http
                before=opener.return_value.open.call_count
                with self.assertRaises(RuntimeError):c.decide(dev_cases()[5]['question'],[])
                self.assertEqual(b.calls,1)
                self.assertEqual(opener.return_value.open.call_count,before+1)
                self.assertEqual(c.last_trace['http_status'],status)
                with self.assertRaises(RuntimeError):c.decide(dev_cases()[5]['question'],[])
                self.assertEqual(opener.return_value.open.call_count,before+1)
                text=b.path.read_text()
                self.assertNotIn('mock-only',text)
                self.assertNotIn('private',text)

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':'mock-only'})
    @patch('src.llm.build_opener')
    def test_timeout_is_reserved_and_stops(self,opener):
        with tempfile.TemporaryDirectory() as root:
            b=self.budget(root);c=PilotController(b,dev_cases())
            opener.return_value.open.side_effect=TimeoutError('private')
            with self.assertRaises(RuntimeError):c.decide(dev_cases()[5]['question'],[])
            self.assertEqual(b.calls,1)
            self.assertEqual(c.last_trace['error'],'LLM_TIMEOUT')
            self.assertTrue(b.stopped)

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':'mock-only'})
    @patch('src.llm.build_opener')
    def test_ledger_write_failure_or_key_verification_failure_blocks_http(self,opener):
        with tempfile.TemporaryDirectory() as root:
            b=self.budget(root);c=PilotController(b,dev_cases())
            with patch('scripts.milestone5c_pilot.append_record',side_effect=OSError('private')):
                with self.assertRaises(RuntimeError):c.decide(dev_cases()[5]['question'],[])
            self.assertEqual(b.calls,0)
            opener.return_value.open.assert_not_called()
        with tempfile.TemporaryDirectory() as root:
            b=self.budget(root);b.verify.side_effect=RuntimeError('unsafe key')
            c=PilotController(b,dev_cases())
            with self.assertRaises(RuntimeError):c.decide(dev_cases()[5]['question'],[])
            opener.return_value.open.assert_not_called()
            self.assertEqual(b.calls,0)

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':'mock-only'})
    @patch('src.llm.build_opener')
    def test_exact_model_caps_timeout_output_tokens_and_usage(self,opener):
        with tempfile.TemporaryDirectory() as root:
            b=self.budget(root);c=PilotController(b,dev_cases())
            body=dict(model=PAID_MODEL,usage=dict(prompt_tokens=100,completion_tokens=10,cost=.0001),
                choices=[dict(finish_reason='stop',message=dict(content='{"action":"search","query":"q"}'))])
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(body).encode()
            self.assertEqual(c.decide(dev_cases()[5]['question'],[])['action'],'search')
            request=opener.return_value.open.call_args.args[0];payload=json.loads(request.data)
            self.assertEqual(payload['model'],PAID_MODEL)
            self.assertEqual(payload['max_tokens'],512)
            self.assertEqual(payload['provider']['max_price'],dict(prompt=.12,completion=.36))
            self.assertFalse(payload['provider']['allow_fallbacks'])
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],60)
            self.assertEqual(str(ledger_state(b.path)['known_cost']),'0.0001')
            body['usage'].pop('cost')
            opener.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(body).encode()
            with self.assertRaises(RuntimeError):c.decide(dev_cases()[5]['question'],[])
            self.assertEqual(b.calls,2)
            self.assertTrue(b.stopped)
            self.assertEqual(c.last_trace['error'],'PILOT_USAGE_OR_RESPONSE_UNVERIFIED')

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':'mock-only'})
    @patch('src.llm.build_opener')
    def test_input_limit_and_unknown_case_block_before_http(self,opener):
        with tempfile.TemporaryDirectory() as root:
            b=self.budget(root);c=PilotController(b,dev_cases())
            with self.assertRaises(RuntimeError):c.decide('not an allowed DEV case',[])
            opener.return_value.open.assert_not_called()
        with tempfile.TemporaryDirectory() as root:
            b=self.budget(root);c=PilotController(b,dev_cases())
            with self.assertRaises(RuntimeError):c.decide(dev_cases()[5]['question'],[dict(context='x'*25000)])
            opener.return_value.open.assert_not_called()
            self.assertEqual(b.calls,0)

    def test_catalog_and_key_policy_fail_closed(self):
        entry=dict(id=PAID_MODEL,context_length=262144,top_provider=dict(max_completion_tokens=8192),
            pricing=dict(prompt='0.00000006',completion='0.00000024',request='0'))
        self.assertEqual(validate_catalog(entry)['status'],'PASS')
        for field,value in [('prompt','0.00000013'),('completion',None),('request','0.01')]:
            bad=dict(entry,pricing=dict(entry['pricing'],**{field:value}))
            with self.assertRaises(RuntimeError):validate_catalog(bad)
        with self.assertRaises(RuntimeError):validate_catalog(dict(entry,context_length=20000))
        for data in [dict(limit=None,limit_remaining=9,usage=0,limit_reset=None),
                     dict(limit=10,limit_remaining=.001,usage=0,limit_reset=None),
                     dict(limit=10,limit_remaining=9,usage=1,limit_reset='daily')]:
            with self.assertRaises(RuntimeError):validate_key_metadata(data,required=.036)

    def test_ledger_does_not_accept_smoke_header_or_corrupt_reservation(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/'ledger';p.write_text('{"inherited_calls":6}\n')
            with self.assertRaises(RuntimeError):PilotBudget(p,verify=MagicMock())
            p.write_text(json.dumps(HEADER)+'\n'+json.dumps(dict(event='reserve',request=2,
                case_id=CASE_IDS[0],reserved_usd='0.004'))+'\n')
            with self.assertRaises(RuntimeError):PilotBudget(p,verify=MagicMock())

    def test_usd_guard_is_checked_before_reservation(self):
        from decimal import Decimal
        with tempfile.TemporaryDirectory() as root:
            b=self.budget(root);b.case_id=CASE_IDS[0]
            with patch('scripts.milestone5c_pilot.PILOT_USD',Decimal('0.003')):
                with self.assertRaisesRegex(RuntimeError,'PILOT_USD_LIMIT_STOP'):b.before_request()
            self.assertEqual(b.calls,0)
            b.verify.assert_not_called()
