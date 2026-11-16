from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError

from src.llm import PAID_MODEL, OpenRouterController
from src.openrouter_paid import (PaidBudget,validate_key_metadata,verify_key_budget,
    validate_paid_resume,MAX_FOUR_CALL_COST)
from scripts.milestone4b_paid_smoke import PaidController
from scripts import milestone4b_paid_smoke as paid
from scripts.milestone4b_smoke import MODEL as FREE_MODEL


def key_data(**changes):
    return dict(dict(limit=1,limit_remaining=1,usage=0,limit_reset=None),**changes)


def chain(directory):
    original = directory/'old.json'
    original.write_text(json.dumps(dict(kind='milestone4b_smoke_not_benchmark',mode='run',
        provider='openrouter',requested_model=FREE_MODEL,status='FAIL',llm_calls=1,
        cases=[dict(case_id='A',status='error',llm_calls=1,retrieval_calls=0,
            events=[dict(llm=dict(http_status=401))])])),encoding='utf-8')
    current=directory/'resume1.json'
    current.write_text(json.dumps(dict(kind='milestone4b_smoke_not_benchmark',mode='run',
        provider='openrouter',requested_model=FREE_MODEL,status='FAIL',llm_calls=2,
        inherited_llm_calls=1,llm_calls_this_run=1,resume_from=str(original),
        resume_parent_sha256=hashlib.sha256(original.read_bytes()).hexdigest(),
        cases=[dict(case_id='A',status='error',llm_calls=1,retrieval_calls=0,
            events=[dict(llm=dict(http_status=404))])])),encoding='utf-8')
    Path(str(original)+'.resume-claim.json').write_text(json.dumps(dict(output=str(current),inherited_calls=1)))
    Path(str(current)+'.requests.jsonl').write_text('{"inherited_calls":1}\n{"reserved_total":2}\n')
    return current


@patch.dict(os.environ, {'OPENROUTER_API_KEY':'mock-private-key'})
class PaidSmokeTests(unittest.TestCase):
    def test_key_budget_validation(self):
        self.assertEqual(validate_key_metadata(key_data())['status'],'PASS')
        self.assertEqual(validate_key_metadata(key_data(limit=9,limit_remaining=9))['status'],'PASS')
        self.assertEqual(validate_key_metadata(key_data(limit_remaining=.2))['status'],'PASS')
        for changes in [dict(limit=None),dict(limit=float('nan')),dict(limit=True),
                dict(limit_reset='daily'),dict(limit_remaining=.199),dict(limit_remaining=2),
                dict(usage=-1),dict(usage=.5),dict(usage=.1)]:
            with self.assertRaises(RuntimeError): validate_key_metadata(key_data(**changes))
        data=key_data();del data['limit_reset']
        with self.assertRaises(RuntimeError):validate_key_metadata(data)

    @patch('src.openrouter_paid.build_opener')
    def test_key_metadata_get_sanitized(self,opener):
        opener.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(
            dict(data=dict(key_data(),label='private-label',hash='private-hash'))).encode()
        result=verify_key_budget()
        req=opener.return_value.open.call_args.args[0]
        self.assertEqual(req.get_method(),'GET')
        self.assertEqual(req.full_url,'https://openrouter.ai/api/v1/key')
        self.assertNotIn('private',json.dumps(result))
        self.assertEqual(opener.return_value.open.call_count,1)

    @patch('src.openrouter_paid.build_opener')
    def test_key_missing_or_http_error_no_retry(self,opener):
        with patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'OPENROUTER_KEY_MISSING'): verify_key_budget()
        opener.assert_not_called()
        opener.return_value.open.side_effect=HTTPError('url',401,'private',{},None)
        with self.assertRaisesRegex(RuntimeError,'KEY_METADATA_REQUEST_FAILED'):verify_key_budget()
        self.assertEqual(opener.return_value.open.call_count,1)

    @patch('src.llm.build_opener')
    def test_paid_model_requires_guard_and_allowlist(self,opener):
        with self.assertRaises(RuntimeError):OpenRouterController(PAID_MODEL).decide('q',[])
        opener.assert_not_called()
        for model in ['other/model:free','openai/gpt-4.1-nano','qwen/qwen3-30b-a3b-instruct-2507:free']:
            with self.assertRaises(ValueError):OpenRouterController(model)

    @patch('src.llm.build_opener')
    def test_paid_http_cap_and_four_remaining_calls(self,opener):
        response=dict(model=PAID_MODEL,choices=[dict(finish_reason='stop',message=dict(
            content='{"action":"search","query":"q"}'))],usage=dict(cost=.0001,prompt_tokens=100,completion_tokens=10))
        opener.return_value.open.return_value.__enter__.return_value.read.return_value=json.dumps(response).encode()
        with tempfile.TemporaryDirectory() as directory:
            journal=Path(directory)/'journal';journal.write_text('')
            verify=MagicMock(return_value=validate_key_metadata(key_data()))
            budget=PaidBudget(journal,verify=verify)
            controller=PaidController(budget)
            for _ in range(4):controller.decide('q',[])
            with self.assertRaises(RuntimeError):controller.decide('q',[])
            self.assertEqual((budget.calls,opener.return_value.open.call_count),(6,4))
            self.assertEqual(budget.reserved_usd,Decimal('.20'))
            self.assertEqual(budget.actual_usd,Decimal('.0004'))
            payload=json.loads(opener.return_value.open.call_args.args[0].data)
            self.assertEqual(payload['model'],PAID_MODEL)
            self.assertEqual(payload['provider']['max_price'],dict(prompt=.12,completion=.36))
            self.assertFalse(payload['provider']['allow_fallbacks'])
            self.assertNotIn('models',payload)
            self.assertEqual(payload['max_tokens'],512)
            self.assertEqual(opener.return_value.open.call_args.kwargs['timeout'],60)
            self.assertEqual(verify.call_count,4)
            self.assertEqual(MAX_FOUR_CALL_COST,Decimal('.01321728'))

    def test_reservation_exists_before_network_and_never_refunded(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=Path(directory)/'journal';journal.write_text('')
            budget=PaidBudget(journal,verify=lambda required:validate_key_metadata(key_data(),required))
            with patch('src.llm.build_opener') as opener:
                def fail(*args,**kwargs):
                    self.assertEqual(json.loads(journal.read_text().splitlines()[-1])['reserved_total'],3)
                    raise TimeoutError()
                opener.return_value.open.side_effect=fail
                controller=PaidController(budget)
                with self.assertRaises(TimeoutError):controller.decide('q',[])
                with self.assertRaises(RuntimeError):controller.decide('q',[])
                self.assertEqual(opener.return_value.open.call_count,1)
                self.assertEqual(budget.reserved_usd,Decimal('.05'))
                self.assertEqual(budget.calls,3)

    def test_fail_closed_for_usd_cap_key_change_and_key_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            journal=Path(directory)/'journal';journal.write_text('')
            budget=PaidBudget(journal,verify=MagicMock(side_effect=RuntimeError('KEY_LIMIT_NOT_SAFE')))
            with self.assertRaises(RuntimeError):budget.before_request()
            self.assertEqual(budget.calls,2)
            self.assertEqual(journal.read_text(),'')
            budget.reserved_usd=Decimal('1.00')
            with self.assertRaises(RuntimeError):budget.before_request()
            budget.reserved_usd=Decimal('0')
            with patch.dict(os.environ,{'OPENROUTER_API_KEY':'changed'}):
                with self.assertRaisesRegex(RuntimeError,'PAID_KEY_CHANGED'):budget.before_request()

    def test_missing_excessive_usage_and_model_mismatch_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            for usage in [{},dict(cost=.06,prompt_tokens=10,completion_tokens=10),
                    dict(cost=.001,prompt_tokens=26001,completion_tokens=10),
                    dict(cost=.001,prompt_tokens=10,completion_tokens=513)]:
                budget=PaidBudget(Path(directory)/'journal',verify=lambda _:None)
                with self.assertRaises(RuntimeError):budget.record_usage(dict(usage=usage))
                self.assertTrue(budget.stopped)
            with self.assertRaises(RuntimeError):
                budget.record_usage(dict(actual_model='other',usage=dict(cost=0,prompt_tokens=1,completion_tokens=1)))

    def test_resume_chain_and_journal_integrity(self):
        with tempfile.TemporaryDirectory() as directory:
            path=chain(Path(directory));before=path.read_bytes()
            self.assertEqual(validate_paid_resume(path),hashlib.sha256(before).hexdigest())
            self.assertEqual(path.read_bytes(),before)
            journal=Path(str(path)+'.requests.jsonl')
            journal.write_text('{"inherited_calls":1}\n{"reserved_total":3}\n')
            with self.assertRaises(RuntimeError):validate_paid_resume(path)

    @patch('src.llm.build_opener')
    def test_preflight_only_metadata_never_inference_or_claim(self,opener):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);parent=chain(directory);output=directory/'preflight.json'
            argv=['paid','--mode','preflight','--resume-from',str(parent),'--day6-root',str(directory),'--output',str(output)]
            with patch('sys.argv',argv),patch.object(paid,'verify_key_budget',return_value=validate_key_metadata(key_data())), \
                    patch.object(paid,'prepare',return_value=(MagicMock(),{})),patch.object(paid,'database_fingerprint',return_value={}):
                self.assertEqual(paid.main(),0)
            result=json.loads(output.read_text())
            self.assertEqual((result['llm_calls'],result['llm_calls_this_run']),(2,0))
            self.assertFalse(Path(str(parent)+'.resume-claim.json').exists())
            opener.assert_not_called()

    @patch('src.llm.build_opener')
    def test_failed_key_preflight_blocks_prepare_and_http(self,opener):
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);parent=chain(directory);output=directory/'fail.json'
            argv=['paid','--mode','run','--approve-paid-inference','--resume-from',str(parent),
                  '--day6-root',str(directory),'--output',str(output)]
            with patch('sys.argv',argv),patch.object(paid,'verify_key_budget',side_effect=RuntimeError('KEY_LIMIT_NOT_SAFE')), \
                    patch.object(paid,'prepare') as prepare:
                self.assertEqual(paid.main(),1)
                prepare.assert_not_called()
            self.assertFalse(Path(str(parent)+'.resume-claim.json').exists())
            opener.assert_not_called()

    def test_paid_run_requires_explicit_approval(self):
        with patch('sys.argv',['paid','--mode','run','--resume-from','old','--day6-root','unused','--output','unused']):
            with self.assertRaises(SystemExit):paid.main()

    @patch('src.llm.build_opener')
    def test_two_case_paid_resume_end_to_end_mock_http(self,opener):
        actions=[dict(action='search',query='foreign key'),
                 dict(action='answer',answer='Evidence [chunk]',citations=['chunk']),
                 dict(action='search',query='orchid'),
                 dict(action='answer',answer='Insufficient evidence',citations=[])]
        responses=[json.dumps(dict(model=PAID_MODEL,usage=dict(cost=.0001,prompt_tokens=100,completion_tokens=10),
            choices=[dict(finish_reason='stop',message=dict(content=json.dumps(action)))])).encode() for action in actions]
        opener.return_value.open.return_value.__enter__.return_value.read.side_effect=responses
        with tempfile.TemporaryDirectory() as directory:
            directory=Path(directory);parent=chain(directory);output=directory/'paid.json'
            originals={p:p.read_bytes() for p in directory.iterdir()}
            backend=MagicMock();backend.last_trace=None
            backend.search.return_value=[dict(id='chunk',source_id='doc',source='public.pdf',page=1,
                text='Evidence',metadata={},score=.9)]
            argv=['paid','--mode','run','--approve-paid-inference','--resume-from',str(parent),
                  '--day6-root',str(directory),'--output',str(output)]
            with patch('sys.argv',argv),patch.object(paid,'verify_key_budget',return_value=validate_key_metadata(key_data())), \
                    patch.object(paid,'prepare',return_value=(backend,{})),patch.object(paid,'database_fingerprint',return_value={}):
                self.assertEqual(paid.main(),0)
            result=json.loads(output.read_text())
            self.assertEqual(result['llm_calls'],6)
            self.assertEqual(result['llm_calls_this_run'],4)
            self.assertEqual(result['reserved_usd'],'0.20')
            self.assertEqual([c['status'] for c in result['cases']],['answered','abstain'])
            self.assertEqual([c['retrieval_calls'] for c in result['cases']],[1,1])
            self.assertEqual(opener.return_value.open.call_count,4)
            self.assertEqual(result['status'],'PENDING_MANUAL_REVIEW')
            self.assertTrue(result['database_unchanged'])
            for path,before in originals.items():self.assertEqual(path.read_bytes(),before)

    @patch('src.llm.build_opener')
    def test_failed_reservation_journal_write_blocks_http(self,opener):
        with tempfile.TemporaryDirectory() as directory:
            budget=PaidBudget(Path(directory)/'missing'/'journal',verify=lambda _:validate_key_metadata(key_data()))
            with self.assertRaises(RuntimeError):PaidController(budget).decide('q',[])
            self.assertEqual(budget.calls,2)
            opener.return_value.open.assert_not_called()
