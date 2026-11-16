from decimal import Decimal as D
import json
import os
from pathlib import Path
import tempfile
import unittest
from urllib.error import HTTPError
from unittest.mock import MagicMock,patch

from scripts.milestone5c_remaining import derive_phase,phase_state,RemainingBudget,checkpoint
from scripts.milestone5c_pilot import HEADER,append_record,PilotController
from scripts.dev_agent_evaluation import CONFIG,evaluate_agent_dev
from src.llm import PAID_MODEL
from tests.test_dev_pilot import dev_cases
from tests.test_dev_readiness import CHUNK
from tests.test_dev_agent_evaluation import MockController


class RemainingTests(unittest.TestCase):
    def fixture(self,root):
        rows=dev_cases();ids=['dev-06','dev-04','dev-17'];ledger=Path(root)/'pilot'
        records=[HEADER];traces=[];seq=0
        for cid,n in zip(ids,[2,2,3]):
            events=[]
            for _ in range(n):
                seq+=1
                records.extend([dict(event='reserve',request=seq,case_id=cid,reserved_usd=str(D('.004')*seq)),
                    dict(event='outcome',request=seq,status='ok',cost_usd='0.0001')])
                events.append(dict(event='decision',llm=dict(status='ok',actual_model=PAID_MODEL,
                    usage=dict(cost=.0001))))
            traces.append(dict(query_id=cid,status='abstain' if cid=='dev-17' else 'answered',
                               llm_requests=n,events=events))
        ledger.write_text('\n'.join(json.dumps(r) for r in records)+'\n')
        pilot=dict(case_results=traces,config=dict(CONFIG,model=PAID_MODEL,case_ids=ids),
                   known_cost_usd='0.0007',reserved_usd='0.028',accounted_llm_requests=7)
        with patch('scripts.milestone5c_remaining.score_reviewed',return_value={}):
            header=derive_phase(rows,pilot,[],dict(official_metrics={}),ledger)
        phase=Path(root)/'phase';phase.write_text(json.dumps(header)+'\n')
        return rows,header,phase,pilot,ledger

    def good(self):
        return dict(status='ok',actual_model=PAID_MODEL,usage=dict(cost=.0001,prompt_tokens=100,completion_tokens=10))

    def test_set_difference_and_parent_accounting(self):
        with tempfile.TemporaryDirectory() as root:
            rows,h,_,pilot,ledger=self.fixture(root)
            self.assertEqual(h['case_ids'],[r['id'] for r in rows if r['id'] not in pilot['config']['case_ids']])
            self.assertEqual(len(h['case_ids']),14)
            self.assertEqual(h['inherited_calls'],7)
            self.assertEqual(h['inherited_reserved_usd'],'0.028')
            pilot['known_cost_usd']='0.003'
            with patch('scripts.milestone5c_remaining.score_reviewed',return_value={}):
                with self.assertRaisesRegex(RuntimeError,'PILOT_TOTALS_MISMATCH'):
                    derive_phase(rows,pilot,[],dict(official_metrics={}),ledger)

    def test_resume_skips_completed_with_verified_checkpoint(self):
        with tempfile.TemporaryDirectory() as root:
            rows,h,path,_,_=self.fixture(root)
            b=RemainingBudget(path,h,verify=MagicMock());cid=h['case_ids'][0];b.case_id=cid
            for _ in range(2):b.before_request();b.outcome(self.good())
            checkpoint(path,dict(query_id=cid,status='answered',llm_requests=2),Path(root)/'records')
            state=phase_state(path,h)
            self.assertEqual(list(state['completed']),[cid])
            resumed=RemainingBudget(path,h,verify=MagicMock())
            self.assertEqual(resumed.calls,9)
            resumed.case_id=cid
            with self.assertRaises(RuntimeError):resumed.before_request()
            pending=[i for i in h['case_ids'] if i not in state['completed']]
            controller=MockController();retriever=MagicMock(spec=['search','last_trace'])
            retriever.last_trace=None;retriever.search.return_value=[CHUNK]
            with patch('scripts.dev_agent_evaluation.LexicalRetriever',return_value=retriever):
                result=evaluate_agent_dev(rows,[CHUNK],controller,output=Path(root)/'run',
                    request_count=lambda:controller.calls,case_ids=pending,
                    completed_case_ids=h['pilot_ids']+[cid])
            self.assertEqual(len(result['cases']),13)
            self.assertNotIn(cid,[t['query_id'] for t in result['cases']])

    def test_uncertain_request_and_missing_checkpoint_block_resume(self):
        with tempfile.TemporaryDirectory() as root:
            _,h,path,_,_=self.fixture(root);b=RemainingBudget(path,h,verify=MagicMock());b.case_id=h['case_ids'][0]
            b.before_request()
            with self.assertRaisesRegex(RuntimeError,'UNRESOLVED_REQUEST'):RemainingBudget(path,h)
            b.outcome(self.good())
            with self.assertRaisesRegex(RuntimeError,'WITHOUT_CASE_CHECKPOINT'):RemainingBudget(path,h)

    def test_unknown_cost_or_error_cannot_resume(self):
        with tempfile.TemporaryDirectory() as root:
            _,h,path,_,_=self.fixture(root);b=RemainingBudget(path,h,verify=MagicMock());b.case_id=h['case_ids'][0]
            b.before_request()
            with self.assertRaises(RuntimeError):b.outcome(dict(status='error',http_status=401))
            self.assertEqual(b.calls,8)
            self.assertTrue(b.stopped)
            with self.assertRaisesRegex(RuntimeError,'COST_UNKNOWN'):phase_state(path,h)

    def test_42_shared_cap_and_3_per_case_and_inherited_reservations(self):
        with tempfile.TemporaryDirectory() as root:
            _,h,path,_,_=self.fixture(root);b=RemainingBudget(path,h,verify=MagicMock())
            for cid in h['case_ids']:
                b.case_id=cid
                for _ in range(3):b.before_request();b.outcome(self.good())
                with self.assertRaises(RuntimeError):b.before_request()
                checkpoint(path,dict(query_id=cid,status='abstain',llm_requests=3),Path(root)/'records')
            state=phase_state(path,h)
            self.assertEqual(b.calls,49);self.assertEqual(state['calls'],42)
            self.assertEqual(state['reserved']+D(h['inherited_reserved_usd']),D('.196'))
            with self.assertRaises(RuntimeError):b.before_request()
            self.assertEqual(b.verify.call_count,42)

    def test_tampered_checkpoint_blocks_resume(self):
        with tempfile.TemporaryDirectory() as root:
            _,h,path,_,_=self.fixture(root);cid=h['case_ids'][0]
            checkpoint(path,dict(query_id=cid,status='abstain',llm_requests=0),Path(root)/'records')
            (Path(root)/'records'/f'{cid}.json').write_text('{}')
            with self.assertRaises(RuntimeError):phase_state(path,h)

    def test_reservation_fsync_failure_blocks_http_and_key_check(self):
        with tempfile.TemporaryDirectory() as root:
            _,h,path,_,_=self.fixture(root);b=RemainingBudget(path,h,verify=MagicMock());b.case_id=h['case_ids'][0]
            with patch('scripts.milestone5c_remaining.append_record',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):b.before_request()
            self.assertEqual(b.calls,7)
            self.assertEqual(phase_state(path,h)['calls'],0)

    def test_phase_and_global_usd_guards(self):
        with tempfile.TemporaryDirectory() as root:
            _,h,path,_,_=self.fixture(root);b=RemainingBudget(path,h,verify=MagicMock());b.case_id=h['case_ids'][0]
            with patch('scripts.milestone5c_remaining.PHASE_USD',D('.003')):
                with self.assertRaisesRegex(RuntimeError,'USD_LIMIT'):b.before_request()
            with patch('scripts.milestone5c_remaining.DEV_USD',D('.031')):
                with self.assertRaisesRegex(RuntimeError,'USD_LIMIT'):b.before_request()
            self.assertEqual(b.calls,7);b.verify.assert_not_called()

    @patch.dict(os.environ,{'OPENROUTER_API_KEY':'mock-only'})
    @patch('src.llm.build_opener')
    def test_continuation_controller_reserves_before_http_and_counts_errors(self,opener):
        for error in (HTTPError('https://openrouter.ai',401,'private',None,None),
                      HTTPError('https://openrouter.ai',429,'private',None,None),TimeoutError('private')):
            with tempfile.TemporaryDirectory() as root:
                rows,h,path,_,_=self.fixture(root)
                b=RemainingBudget(path,h,verify=MagicMock())
                c=PilotController(b,rows,allowed_case_ids=h['case_ids'])
                question=next(row['question'] for row in rows if row['id']==h['case_ids'][0])
                def open_http(*args,**kwargs):
                    self.assertEqual(json.loads(path.read_text().splitlines()[-1])['event'],'reserve')
                    raise error
                opener.return_value.open.side_effect=open_http
                before=opener.return_value.open.call_count
                with self.assertRaises(RuntimeError):c.decide(question,[])
                self.assertEqual(b.calls,8)
                with self.assertRaises(RuntimeError):c.decide(question,[])
                self.assertEqual(opener.return_value.open.call_count,before+1)
                self.assertNotIn('private',path.read_text())

    def test_resume_selection_cannot_omit_unfinished_case_or_repeat_pilot(self):
        with tempfile.TemporaryDirectory() as root:
            rows,h,_,_,_=self.fixture(root);c=MockController()
            for selection in [h['case_ids'][:-1],h['case_ids']+h['pilot_ids'][:1]]:
                with self.assertRaises(ValueError):evaluate_agent_dev(rows,[CHUNK],c,
                    output=Path(root)/'unused',request_count=lambda:c.calls,case_ids=selection,
                    completed_case_ids=h['pilot_ids'])
            self.assertEqual(c.calls,0)
