import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from scripts.milestone4b_smoke import CallBudget, GuardedController, LimitedRetriever, ByteBudget
from scripts import milestone4b_smoke as smoke


class SmokeLimitTests(unittest.TestCase):
    def prior_trace(self, path):
        trace = dict(kind='milestone4b_smoke_not_benchmark',mode='run',provider='openrouter',
            requested_model=smoke.MODEL,status='FAIL',llm_calls=1,cases=[dict(case_id='A',
            status='error',llm_calls=1,retrieval_calls=0,
            events=[dict(llm=dict(http_status=401))]),dict(case_id='B',status='NOT_RUN_GLOBAL_STOP')])
        path.write_text(json.dumps(trace))
        return trace

    @patch.dict(os.environ, {'OPENROUTER_API_KEY':'mock'})
    @patch('src.llm.build_opener')
    def test_resume_401_allows_only_five_more_http_requests(self, opener):
        response = dict(choices=[dict(finish_reason='stop',message=dict(content='{"action":"search","query":"q"}'))])
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
        with tempfile.TemporaryDirectory() as directory:
            parent, output = Path(directory)/'old.json', Path(directory)/'new.json'
            self.prior_trace(parent)
            before = parent.read_bytes()
            used, _ = smoke.read_resume(parent)
            journal = smoke.claim_resume(parent,output,used)
            budget = CallBudget(used,journal)
            controller = GuardedController(budget)
            for _ in range(5): controller.decide('q',[])
            with self.assertRaises(RuntimeError): controller.decide('q',[])
            self.assertEqual(opener.return_value.open.call_count,5)
            self.assertEqual(budget.calls,6)
            self.assertEqual(json.loads(journal.read_text().splitlines()[-1])['reserved_total'],6)
            self.assertEqual(parent.read_bytes(),before)
            with self.assertRaises(FileExistsError): smoke.claim_resume(parent,Path(directory)/'other.json',used)

    def test_invalid_resume_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'old.json'
            trace = self.prior_trace(path)
            for field,value in [('llm_calls',0),('llm_calls',7),('llm_calls',True),
                                ('requested_model','other/model:free')]:
                invalid = dict(trace,**{field:value})
                path.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError): smoke.read_resume(path)
            trace['cases'][0]['retrieval_calls']=1
            path.write_text(json.dumps(trace))
            with self.assertRaises(ValueError): smoke.read_resume(path)

    @patch.dict(os.environ, {'OPENROUTER_API_KEY':'mock'})
    def test_resume_main_cumulative_report_and_preserves_old_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            parent, output = Path(directory)/'old.json', Path(directory)/'new.json'
            self.prior_trace(parent)
            before = parent.read_bytes()
            def agent(question,controller,retriever,**kwargs):
                controller.budget.before_request()
                return dict(status='abstain',citations=[],citation_map={})
            argv=['smoke','--mode','run','--day6-root',directory,'--output',str(output),'--resume-from',str(parent)]
            with patch('sys.argv',argv), patch.object(smoke,'prepare',return_value=(MagicMock(),{})), \
                    patch.object(smoke,'database_fingerprint',return_value={}), patch.object(smoke,'run_agent',side_effect=agent):
                self.assertEqual(smoke.main(),0)
            report=json.loads(output.read_text())
            self.assertEqual((report['inherited_llm_calls'],report['llm_calls_this_run'],report['llm_calls']),(1,2,3))
            self.assertEqual(parent.read_bytes(),before)

    @patch.dict(os.environ, {'OPENROUTER_API_KEY':'mock'})
    @patch('src.llm.build_opener')
    def test_preflight_never_opens_http(self, opener):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'report.json'
            argv = ['smoke', '--mode','preflight','--day6-root',directory,'--output',str(output)]
            with patch('sys.argv',argv), patch.object(smoke,'prepare',return_value=(MagicMock(),{'db':'same'})), \
                    patch.object(smoke,'database_fingerprint',return_value={'db':'same'}):
                self.assertEqual(smoke.main(), 0)
            report = json.loads(output.read_text())
            self.assertEqual(report['llm_calls'], 0)
            self.assertEqual(report['status'], 'PASS')
            opener.assert_not_called()

    def test_shared_counter_stops_seventh_request(self):
        budget = CallBudget()
        for _ in range(6): budget.before_request()
        with self.assertRaises(RuntimeError): budget.before_request()
        self.assertEqual(budget.calls, 6)

    @patch.dict(os.environ, {'OPENROUTER_API_KEY':'mock'})
    @patch('src.llm.build_opener')
    def test_guard_at_http_boundary_across_controllers(self, opener):
        response = dict(choices=[dict(finish_reason='stop',message=dict(content='{"action":"search","query":"q"}'))])
        opener.return_value.open.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
        budget = CallBudget()
        for _ in range(2):
            controller = GuardedController(budget)
            for _ in range(3): controller.decide('q', [])
        with self.assertRaises(RuntimeError): controller.decide('q', [])
        self.assertEqual(opener.return_value.open.call_count, 6)

    @patch.dict(os.environ, {'OPENROUTER_API_KEY':'mock'})
    @patch('src.llm.build_opener')
    def test_stop_on_http_errors_and_timeout(self, opener):
        for error in [HTTPError('url',s,'private',{},None) for s in (401,402,429)] + [TimeoutError()]:
            opener.return_value.open.reset_mock()
            opener.return_value.open.side_effect = error
            budget = CallBudget()
            controller = GuardedController(budget)
            with self.assertRaises(Exception): controller.decide('q', [])
            with self.assertRaises(RuntimeError): GuardedController(budget).decide('q', [])
            self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertTrue(budget.stopped)

    def test_retrieval_cap_and_byte_bound(self):
        backend = MagicMock()
        retriever = LimitedRetriever(backend)
        for _ in range(2): retriever.search('q', filters=None, top_k=3)
        with self.assertRaises(RuntimeError): retriever.search('q', filters=None, top_k=3)
        self.assertEqual(backend.search.call_count, 2)
        self.assertEqual(ByteBudget()('é'), 2)

    @patch('src.llm.build_opener')
    def test_oversized_payload_stops_before_http(self, opener):
        budget = CallBudget()
        with self.assertRaises(RuntimeError): GuardedController(budget).decide('x'*24001, [])
        self.assertEqual(budget.calls, 0)
        opener.assert_not_called()
