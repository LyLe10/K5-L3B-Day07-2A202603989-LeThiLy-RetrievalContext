"""Synthetic TEST-shaped fixtures only. No frozen TEST content is parsed."""
from copy import deepcopy
from decimal import Decimal
import importlib
import io
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts import frozen_test_evaluation as runner


CHUNK = dict(id='synthetic',text='Synthetic evidence.',source_id='unit',source='unit.pdf',
             page=1,metadata={},score=.8)


def cases():
    return [dict(id=f'test-{i:02}',split='test',question=f'Synthetic question {i}',
        answerable=True,gold=[dict(chunk_id='synthetic',source_id='unit',page=1,
        evidence='Synthetic evidence.')]) for i in range(1,8)]


def header(variant='E1'):
    pin = runner.dev.validate_dependencies()
    return dict(event='allocation',scope='FROZEN_TEST',split='test',variant=variant,
        model=runner.dev.PAID_MODEL,case_ids=[c['id'] for c in cases()],
        config=dict(max_searches=2),limits=dict(cases=7,requests=21,
            requests_per_case=3,retrievals_per_case=2),envelope_usd='.084',
        code_sha256=pin['code_sha256'],day6_code_sha256=pin['day6_code_sha256'],
        dependency_pin_sha256=runner.dev.digest(runner.dev.DEPENDENCY_PIN),day6_root=pin['day6_root'])


class Retriever:
    last_trace = None

    def search(self,*a,**k):
        return [deepcopy(CHUNK)]


@patch.dict(os.environ,{'OPENROUTER_API_KEY':'synthetic-unit-key'})
class TestRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        # All synthetic executions use a fake HTTP opener; network primitives
        # independently raise if any mock is accidentally bypassed.
        for target in ('socket.socket.connect','socket.create_connection','socket.getaddrinfo'):
            patcher = patch(target,side_effect=AssertionError('NETWORK_FORBIDDEN'))
            self.addCleanup(patcher.stop); patcher.start()

    def initialize(self,h=None,name='E1'):
        h = h or header(name)
        d = self.root/name
        runner.initialize(d,h)
        return d,h

    def budget(self,d,h):
        with patch.object(runner,'validate_identity'):
            return runner.TestBudget(d,h,verify=MagicMock())

    def provider(self,max_searches=1):
        def response(request,**kwargs):
            payload = json.loads(request.data)
            history = json.loads(payload['messages'][1]['content'])['retrieval_history']
            count = len(history[0]['queries']) if history else 0
            action = (dict(action='search',query=f'synthetic search {count}') if count<max_searches
                else dict(action='answer',answer='Synthetic evidence [synthetic]',citations=['synthetic']))
            reply = MagicMock()
            reply.__enter__.return_value.read.return_value = json.dumps(dict(
                model=runner.dev.PAID_MODEL,choices=[dict(finish_reason='stop',
                    message=dict(content=json.dumps(action)))],
                usage=dict(cost=.00001,prompt_tokens=50,completion_tokens=10,total_tokens=60))).encode()
            return reply
        opener = MagicMock();opener.open.side_effect=response
        return opener

    def execute_mock(self,d,h,searches=1):
        b = self.budget(d,h)
        with patch.object(runner,'validate_identity'),patch.object(runner.dev,'build_opener',return_value=self.provider(searches)):
            result = runner.evaluate(cases(),Retriever(),runner.dev.ExperimentController(b,'Synthetic prompt'),b,d,h)
        return result,b

    def test_seven_synthetic_cases(self):
        d,h=self.initialize();rows,b=self.execute_mock(d,h)
        self.assertEqual(len(rows),7);self.assertEqual(b.calls,14)
        self.assertTrue(all(r['split']=='test' and r['status']=='answered' for r in rows))

    def test_request_limit_21(self):
        d,h=self.initialize();rows,b=self.execute_mock(d,h,2)
        self.assertEqual(b.calls,21)
        with patch.object(runner,'validate_identity'):
            b.case_id=h['case_ids'][-1]
            with self.assertRaisesRegex(RuntimeError,'REQUEST_LIMIT'):b.before_request()
        self.assertEqual(runner.state(d,h)['reserved'],Decimal('.084'))

    def test_combined_42_separate_variants(self):
        budgets=[]
        for variant in ('baseline','E1'):
            d,h=self.initialize(name=variant);_,b=self.execute_mock(d,h,2);budgets.append(b)
        self.assertEqual(sum(b.calls for b in budgets),42)
        self.assertEqual(sum(runner.state(b.directory,b.header)['reserved'] for b in budgets),Decimal('.168'))

    def test_per_case_limit(self):
        d,h=self.initialize();b=self.budget(d,h);b.case_id=h['case_ids'][0]
        with patch.object(runner,'validate_identity'):
            for _ in range(3):
                b.before_request();b.outcome(dict(status='ok',actual_model=runner.dev.PAID_MODEL,
                    usage=dict(cost=.00001,prompt_tokens=50,completion_tokens=10)))
            with self.assertRaisesRegex(RuntimeError,'REQUEST_LIMIT'):b.before_request()

    def test_budget_guard_before_metadata_or_request(self):
        h=header();h['envelope_usd']='.003';d,h=self.initialize(h);b=self.budget(d,h);b.case_id=h['case_ids'][0]
        with patch.object(runner,'validate_identity'):
            with self.assertRaisesRegex(RuntimeError,'USD_LIMIT'):b.before_request()
        b.verify.assert_not_called();self.assertEqual(b.calls,0)

    def test_split_and_duplicate_rejected(self):
        h=header()
        for changed in ('dev','duplicate','short'):
            cs=cases()
            if changed=='dev':cs[0]['split']='dev'
            elif changed=='duplicate':cs[1]['id']=cs[0]['id']
            else:cs.pop()
            with self.assertRaisesRegex(RuntimeError,'CASE_IDS_OR_SPLIT'):runner.validate_cases(cs,h)

    def test_variant_journal_isolation(self):
        d,h=self.initialize()
        other=deepcopy(h);other['variant']='baseline'
        with self.assertRaisesRegex(RuntimeError,'IDENTITY'):runner.state(d,other)

    def test_exact_real_lock_config_without_test_content(self):
        lock,config,_=runner.configuration()
        self.assertEqual(config,lock['verified_configuration'])
        self.assertEqual(config['retrieval']['max_searches'],2)
        self.assertEqual(config['system_prompt_sha256'],lock['prompt_sha256'])

    def test_missing_invalid_lock(self):
        with self.assertRaises(FileNotFoundError):runner.configuration(self.root)
        p=self.root/runner.LOCK;p.parent.mkdir();p.write_text('{}')
        with self.assertRaisesRegex(RuntimeError,'LOCK_INVALID'):runner.configuration(self.root)

    def test_namespace_rejected_even_before_pin(self):
        h=header()
        with patch.object(runner,'design',return_value=h):
            with self.assertRaisesRegex(RuntimeError,'NAMESPACE'):runner.validate_identity(h,self.root/'dev',self.root)

    def test_pin_required_and_changed_fails_closed(self):
        h=header();h['test_runner_sha256']=runner.LOADED_SHA
        d=runner.run_directory(h,self.root)
        with patch.object(runner,'design',return_value=h):
            with self.assertRaises(FileNotFoundError):runner.validate_identity(h,d,self.root)
            p=self.root/runner.PIN;p.parent.mkdir(parents=True)
            p.write_text(json.dumps(dict(status='PASS',code_sha256={runner.SELF:'changed'})))
            with self.assertRaisesRegex(RuntimeError,'PIN_MISSING_OR_CHANGED'):runner.validate_identity(h,d,self.root)

    def test_valid_pin_and_identity_accept_new_and_resume(self):
        h=header();h['test_runner_sha256']=runner.LOADED_SHA
        d=runner.run_directory(h,self.root)
        p=self.root/runner.PIN;p.parent.mkdir(parents=True)
        p.write_text(json.dumps(dict(status='PASS',code_sha256={runner.SELF:runner.LOADED_SHA})))
        with patch.object(runner,'design',return_value=h):
            runner.validate_identity(h,d,self.root)
            d.parent.mkdir(parents=True);runner.initialize(d,h)
            runner.validate_identity(h,d,self.root)
            self.assertEqual(runner.state(d,h)['calls'],0)

    def test_baseline_and_e1_prompts_are_selected_independently(self):
        _,config,pin=runner.configuration()
        with patch.object(runner,'configuration',return_value=({},config,pin)),patch.object(runner,'metadata',return_value=header()['case_ids']):
            baseline=runner.design('baseline');e1=runner.design('E1')
        self.assertEqual(baseline['prompt'],runner.SYSTEM)
        self.assertEqual(e1['prompt'],config['system_prompt'])
        self.assertNotEqual(baseline['prompt'],e1['prompt'])
        self.assertNotEqual(runner.run_directory(baseline),runner.run_directory(e1))

    def test_identity_cannot_be_skipped_on_new_resume_or_before_request(self):
        d,h=self.initialize()
        with patch.object(runner,'validate_identity',side_effect=RuntimeError('identity failed')):
            with self.assertRaisesRegex(RuntimeError,'identity failed'):runner.TestBudget(d,h,verify=MagicMock())
        b=self.budget(d,h)
        with patch.object(runner,'validate_identity',side_effect=RuntimeError('identity failed')):
            with self.assertRaisesRegex(RuntimeError,'identity failed'):b.before_request()
        self.assertEqual(b.calls,0)

    def test_provider_failure_records_error_and_stops(self):
        d,h=self.initialize();b=self.budget(d,h);b.case_id=h['case_ids'][0]
        opener=MagicMock();opener.open.side_effect=HTTPError('https://unit.invalid',429,'rate',{},None)
        with patch.object(runner,'validate_identity'),patch.object(runner.dev,'build_opener',return_value=opener):
            ctrl=runner.dev.ExperimentController(b,'Synthetic prompt')
            with self.assertRaisesRegex(RuntimeError,'RATE_LIMIT'):ctrl.decide('Synthetic question',[])
        self.assertEqual(b.calls,1);self.assertTrue(b.stopped);opener.open.assert_called_once()
        with self.assertRaises(RuntimeError):runner.state(d,h)

    def test_unknown_cost_stops(self):
        d,h=self.initialize();b=self.budget(d,h);b.case_id=h['case_ids'][0]
        with patch.object(runner,'validate_identity'):b.before_request()
        with self.assertRaisesRegex(RuntimeError,'RESPONSE_UNVERIFIED'):
            b.outcome(dict(status='ok',actual_model=runner.dev.PAID_MODEL,usage={}))
        with self.assertRaisesRegex(RuntimeError,'COST_UNKNOWN'):runner.state(d,h)

    def test_partial_case_cannot_resume(self):
        d,h=self.initialize();b=self.budget(d,h);b.case_id=h['case_ids'][0]
        with patch.object(runner,'validate_identity'):b.before_request()
        with self.assertRaisesRegex(RuntimeError,'UNRESOLVED'):runner.state(d,h)
        b.outcome(dict(status='ok',actual_model=runner.dev.PAID_MODEL,
            usage=dict(cost=.00001,prompt_tokens=50,completion_tokens=10)))
        with self.assertRaisesRegex(RuntimeError,'PARTIAL_CASE'):runner.state(d,h)

    def test_resume_skips_all_completed_no_http(self):
        d,h=self.initialize();first,b=self.execute_mock(d,h)
        with patch.object(runner,'validate_identity'),patch.object(runner.dev,'build_opener',side_effect=AssertionError('HTTP')):
            b2=runner.TestBudget(d,h,verify=MagicMock())
            result=runner.evaluate(cases(),Retriever(),MagicMock(),b2,d,h)
        self.assertEqual(result,first);self.assertEqual(b2.calls,14)

    def test_tampered_checkpoint_and_duplicate_event_rejected(self):
        d,h=self.initialize();self.execute_mock(d,h)
        p=d/'checkpoints'/('test-01.json');p.write_text('{}')
        with self.assertRaises(RuntimeError):runner.state(d,h)

    def test_duplicate_journal_event_rejected(self):
        d,h=self.initialize();self.execute_mock(d,h)
        rows=[json.loads(s) for s in (d/'requests.jsonl').read_text().splitlines()]
        runner.dev.append_record(d/'requests.jsonl',rows[-1])
        with self.assertRaisesRegex(RuntimeError,'CASE_SEQUENCE'):runner.state(d,h)

    def test_no_overwrite(self):
        d,h=self.initialize();before=(d/'identity.json').read_bytes()
        with self.assertRaises(FileExistsError):runner.initialize(d,h)
        with self.assertRaises(FileExistsError):runner.dev.write_new(d/'identity.json',{})
        self.assertEqual(before,(d/'identity.json').read_bytes())

    def test_default_cli_never_executes(self):
        h=header()
        with patch.object(runner,'design',return_value=h),patch.object(runner,'validate_identity'),patch.object(runner,'execute') as execute,patch('sys.stdout',new=io.StringIO()):
            runner.main(['--variant','E1'])
            execute.assert_not_called()

    def test_approval_required_before_test_parse(self):
        with patch.object(runner,'read',side_effect=AssertionError('must not parse')):
            with self.assertRaisesRegex(RuntimeError,'EXPLICIT_APPROVAL'):runner.execute({},approved=False)
        with patch('sys.stderr',new=io.StringIO()):
            with self.assertRaises(SystemExit):runner.main(['--variant','E1','--mode','run'])

    def test_approved_entrypoint_with_synthetic_inputs_only(self):
        h=header();h['prompt']='Synthetic prompt'
        fixture=self.root/'data/benchmark/test.json';fixture.parent.mkdir(parents=True)
        fixture.write_text(json.dumps(cases()))
        (self.root/'results').mkdir()
        directory=self.root/'results/milestone6_test_run/E1'
        original_budget=runner.TestBudget
        def budget(d,h):return original_budget(d,h,verify=MagicMock())
        with patch.object(runner,'ROOT',self.root),patch.object(runner,'run_directory',return_value=directory),patch.object(runner,'validate_identity'),patch.object(runner,'TestBudget',side_effect=budget),patch.object(runner.dev,'verify_key_budget') as key,patch.object(runner.dev,'check_catalog') as catalog,patch.object(runner.dev.dense_module,'Config'),patch.object(runner.dev.dense_module,'load_embedder'),patch.object(runner.dev.dense_module,'DenseRetriever'),patch.object(runner.dev,'database_fingerprint',return_value='synthetic-db-fingerprint'),patch.object(runner.dev,'load_snapshot',return_value=[CHUNK]),patch.object(runner.dev,'LexicalRetriever',return_value=Retriever()),patch.object(runner.dev,'build_opener',return_value=self.provider()):
            runner.execute(h,approved=True,approved_envelope='.084')
            key.assert_called_once();catalog.assert_called_once()
            # Existing output must stop a second invocation before any metadata.
            with self.assertRaisesRegex(RuntimeError,'OUTPUT_EXISTS'):
                runner.execute(h,approved=True,approved_envelope='.084',resume=True)
            key.assert_called_once()
        raw=json.loads((self.root/'results/milestone6_test_e1_raw.json').read_text())
        self.assertEqual(len(raw['case_results']),7)
        self.assertEqual(raw['requests'],14)
        self.assertFalse((self.root/'results/milestone6_test_execution.lock').exists())

    def test_metadata_synthetic_only_and_drift(self):
        d=self.root/'data/benchmark';d.mkdir(parents=True)
        (d/'test.json').write_text(json.dumps(cases()));(d/'dev.json').write_text('opaque DEV')
        (d/'manifest.json').write_text('{}');(d/'manifest.sha256').write_text('pin')
        c=dict(frozen_benchmark=dict(manifest_sha256=runner.dev.digest(d/'manifest.json'),
            manifest_pin_sha256=runner.dev.digest(d/'manifest.sha256'),
            files_sha256={p:runner.dev.digest(d/p) for p in ('dev.json','test.json')}))
        with patch.object(runner,'read',side_effect=AssertionError('no content parse')):
            self.assertEqual(runner.metadata(c,self.root),header()['case_ids'])
        (d/'test.json').write_text('changed')
        with self.assertRaisesRegex(RuntimeError,'FROZEN_HASH'):runner.metadata(c,self.root)

    def test_import_does_not_run_or_write(self):
        original=Path.open
        def readonly(path,mode='r',*args,**kwargs):
            if any(c in mode for c in 'wax+'):
                raise AssertionError('write')
            return original(path,mode,*args,**kwargs)
        with patch.object(runner.dev,'run_agent',side_effect=AssertionError('Agent')),patch.object(Path,'open',readonly),patch.object(runner.dev,'verify_key_budget',side_effect=AssertionError('HTTP')):
            importlib.reload(runner)

    def test_reports_do_not_expose_synthetic_key(self):
        d,h=self.initialize();rows,b=self.execute_mock(d,h)
        self.assertNotIn('synthetic-unit-key',json.dumps(rows))
        self.assertNotIn('Authorization',(d/'requests.jsonl').read_text())


if __name__=='__main__':
    unittest.main()
