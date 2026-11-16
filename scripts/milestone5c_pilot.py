"""Three-case paid DEV pilot. Offline preparation never makes network calls."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.request import Request, build_opener

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.dev_agent_evaluation import evaluate_agent_dev, CONFIG
from scripts.dev_retrieval_benchmark import load_frozen_dev, validate_dev
from scripts.dense_smoke import database_fingerprint
from src.benchmark_data import load_offline_snapshot
from src import dense as d
from src.retrieval import load_snapshot
from src.llm import OpenRouterController, PAID_MODEL, MODEL_PRICE_CAPS, SYSTEM, _NoRedirect
from src.openrouter_paid import verify_key_budget

CASE_IDS=('dev-06','dev-04','dev-17')
LEDGER=ROOT/'results/milestone5c_pilot_requests.jsonl'
RESERVATION=Decimal('0.004')
PILOT_USD=Decimal('0.05')
DEV_USD=Decimal('0.25')
HEADER=dict(event='allocation',milestone='5C',scope='DEV_PILOT',case_ids=list(CASE_IDS),
    model=PAID_MODEL,max_requests=9,pilot_usd=str(PILOT_USD),dev_usd=str(DEV_USD),
    reservation_usd=str(RESERVATION))


def append_record(path, record):
    with path.open('a',encoding='utf-8') as stream:
        stream.write(json.dumps(record)+'\n')
        stream.flush()
        os.fsync(stream.fileno())


def ledger_state(path):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    if not rows or rows[0]!=HEADER:raise RuntimeError('PILOT_LEDGER_IDENTITY_INVALID')
    calls=0;per_case=Counter();settled=set();known_cost=Decimal('0');cost_calls=0
    for row in rows[1:]:
        if row.get('event')=='reserve':
            calls+=1;cid=row.get('case_id');per_case[cid]+=1
            if (row.get('request')!=calls or cid not in CASE_IDS or per_case[cid]>3
                    or row.get('reserved_usd')!=str(RESERVATION*calls)):
                raise RuntimeError('PILOT_LEDGER_INVALID')
        elif row.get('event')=='outcome':
            seq=row.get('request')
            if seq!=calls or seq in settled:raise RuntimeError('PILOT_LEDGER_INVALID')
            settled.add(seq)
            if row.get('cost_usd') is not None:
                known_cost+=number(row['cost_usd']);cost_calls+=1
        else:raise RuntimeError('PILOT_LEDGER_INVALID')
    if calls>9 or RESERVATION*calls>PILOT_USD or known_cost>PILOT_USD:
        raise RuntimeError('PILOT_LEDGER_LIMIT_EXCEEDED')
    return dict(calls=calls,per_case=per_case,reserved=RESERVATION*calls,known_cost=known_cost,
                reported_cost_calls=cost_calls)


def initialize_ledger(path):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not path.exists():
        with path.open('x',encoding='utf-8') as stream:
            stream.write(json.dumps(HEADER)+'\n');stream.flush();os.fsync(stream.fileno())
    return ledger_state(path)


def number(value):
    if isinstance(value,bool) or value is None:raise RuntimeError('PILOT_NUMBER_INVALID')
    try:result=Decimal(str(value))
    except Exception:raise RuntimeError('PILOT_NUMBER_INVALID') from None
    if not result.is_finite() or result<0:raise RuntimeError('PILOT_NUMBER_INVALID')
    return result


def validate_catalog(entry):
    if not isinstance(entry,dict) or entry.get('id')!=PAID_MODEL:
        raise RuntimeError('PILOT_MODEL_NOT_AVAILABLE')
    caps=MODEL_PRICE_CAPS[PAID_MODEL];pricing=entry.get('pricing',{})
    for key in ('prompt','completion'):
        if number(pricing.get(key))*1000000>number(caps[key]):
            raise RuntimeError('PILOT_MODEL_PRICE_EXCEEDS_CAP')
    # Reject additional nonzero charge categories instead of assuming zero.
    for key,value in pricing.items():
        if key in ('input_cache_read','input_cache_write') and number(value)*1000000>number(caps['prompt']):
            raise RuntimeError('PILOT_CACHE_PRICE_UNSAFE')
        if key not in ('prompt','completion','input_cache_read','input_cache_write') and number(value)!=0:
            raise RuntimeError('PILOT_ADDITIONAL_PRICE_UNSAFE')
    if type(entry.get('context_length')) is not int or entry['context_length']<26512:
        raise RuntimeError('PILOT_MODEL_CONTEXT_UNSAFE')
    completion=entry.get('top_provider',{}).get('max_completion_tokens')
    if type(completion) is not int or completion<512:
        raise RuntimeError('PILOT_COMPLETION_LIMIT_UNVERIFIED')
    return dict(status='PASS',model=PAID_MODEL,pricing=pricing,context_length=entry['context_length'],
                max_completion_tokens=completion)


def check_catalog():
    try:
        request=Request('https://openrouter.ai/api/v1/models')
        with build_opener(_NoRedirect()).open(request,timeout=30) as response:data=json.load(response)
        entry=next((e for e in data['data'] if e.get('id')==PAID_MODEL),None)
    except Exception:raise RuntimeError('PILOT_CATALOG_CHECK_FAILED') from None
    return validate_catalog(entry)


class PilotBudget:
    def __init__(self,path,*,verify=verify_key_budget):
        state=initialize_ledger(path)
        self.path=path;self.calls=state['calls'];self.stopped=False;self.case_id=None
        self.verify=verify
        self.key_hash=hashlib.sha256(os.environ.get('OPENROUTER_API_KEY','').encode()).digest()

    def before_request(self):
        state=ledger_state(self.path)
        if (self.stopped or state['calls']!=self.calls or self.calls>=9
                or self.case_id not in CASE_IDS or state['per_case'][self.case_id]>=3):
            raise RuntimeError('PILOT_REQUEST_LIMIT_STOP')
        if (state['reserved']+RESERVATION>PILOT_USD or state['reserved']+RESERVATION>DEV_USD
                or state['known_cost']+RESERVATION>PILOT_USD):
            raise RuntimeError('PILOT_USD_LIMIT_STOP')
        if hashlib.sha256(os.environ.get('OPENROUTER_API_KEY','').encode()).digest()!=self.key_hash:
            raise RuntimeError('PILOT_KEY_CHANGED')
        self.verify(RESERVATION*(9-self.calls))
        # Durable reservation BEFORE HTTP. Unknown/error requests never refunded.
        append_record(self.path,dict(event='reserve',request=self.calls+1,case_id=self.case_id,
                                    reserved_usd=str(RESERVATION*(self.calls+1))))
        self.calls+=1

    def outcome(self,trace):
        row=dict(event='outcome',request=self.calls,status=trace.get('status'),
                 error=trace.get('error'),http_status=trace.get('http_status'),cost_usd=None)
        valid=False
        if trace.get('status')=='ok':
            try:
                usage=trace['usage'];cost=number(usage['cost'])
                valid=(cost<=RESERVATION and number(usage['prompt_tokens'])<=26000
                    and number(usage['completion_tokens'])<=512 and trace.get('actual_model')==PAID_MODEL)
                row['cost_usd']=str(cost)
            except Exception:valid=False
            if not valid:row.update(status='error',error='PILOT_USAGE_OR_RESPONSE_UNVERIFIED')
        append_record(self.path,row)
        if not valid:
            self.stopped=True
            raise RuntimeError('PILOT_USAGE_OR_RESPONSE_UNVERIFIED')


class PilotController:
    def __init__(self,budget,cases,*,allowed_case_ids=None):
        self.allowed_case_ids=frozenset(CASE_IDS if allowed_case_ids is None else allowed_case_ids)
        self.budget=budget;self.case_ids={c['question']:c['id'] for c in cases if c['id'] in self.allowed_case_ids}
        self.backend=OpenRouterController(PAID_MODEL,timeout=60,max_output_tokens=512,
                                          request_guard=budget.before_request)
        self.last_trace=None

    def decide(self,question,history):
        self.last_trace=dict(provider='openrouter',model=PAID_MODEL,status='error')
        self.backend.last_trace=None
        before=self.budget.calls
        try:
            if self.budget.stopped:raise RuntimeError('PILOT_STOPPED')
            self.budget.case_id=self.case_ids.get(question)
            if self.budget.case_id not in self.allowed_case_ids:raise RuntimeError('PILOT_CASE_NOT_ALLOWED')
            user=json.dumps(dict(question=question,retrieval_history=history),ensure_ascii=False)
            if len(user.encode())>24000 or len(SYSTEM.encode())+len(user.encode())+512>26000:
                raise RuntimeError('PILOT_INPUT_BUDGET_STOP')
            action=self.backend.decide(question,history)
            self.last_trace=dict(self.backend.last_trace)
        except Exception:
            self.budget.stopped=True
            self.last_trace=dict(self.backend.last_trace or self.last_trace)
            if self.budget.calls>before:self.budget.outcome(self.last_trace)
            raise RuntimeError('PILOT_CONTROLLER_ERROR') from None
        try:self.budget.outcome(self.last_trace)
        except Exception:
            self.budget.stopped=True
            self.last_trace.update(status='error',error='PILOT_USAGE_OR_RESPONSE_UNVERIFIED')
            raise RuntimeError('PILOT_USAGE_OR_RESPONSE_UNVERIFIED') from None
        return action


def offline_preflight(dev,day6_root,output,ledger=LEDGER):
    if output.exists():raise RuntimeError('OUTPUT_EXISTS_PRESERVE_EVIDENCE')
    _,cases,frozen=load_frozen_dev(dev)
    chunks,_,identity=load_offline_snapshot(day6_root)
    if identity!=frozen['identity']:raise RuntimeError('PILOT_SNAPSHOT_IDENTITY_MISMATCH')
    validate_dev(cases,chunks)
    if not all(cid in {c['id'] for c in cases} for cid in CASE_IDS):
        raise RuntimeError('PILOT_CASE_IDS_MISSING')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryFile(dir=output.parent) as probe:
        probe.write(b'trace-write-check');probe.flush();os.fsync(probe.fileno())
    state=initialize_ledger(ledger)
    report=dict(kind='milestone5c_pilot',status='OFFLINE_PASS_PENDING_ONLINE_APPROVAL',
        config=dict(CONFIG,model=PAID_MODEL,case_ids=list(CASE_IDS),max_llm_requests=9,
            max_requests_per_case=3,max_tokens=512,timeout=60,retries=0,fallback=False,
            price_caps_usd_per_million=MODEL_PRICE_CAPS[PAID_MODEL],pilot_usd=str(PILOT_USD),
            dev_usd=str(DEV_USD),remaining_dev_allocation_usd='0.20',
            reservation_per_request_usd=str(RESERVATION),max_reserved_usd='0.036',
            estimated_max_cost_usd='0.02973888',input_token_estimate_bound=26000),
        frozen=frozen,snapshot_chunks=len(chunks),snapshot_identity=identity,
        ledger=str(ledger),accounted_llm_requests=state['calls'],llm_requests_this_run=0,
        key_present=bool(os.environ.get('OPENROUTER_API_KEY','').strip()),
        key_budget_verification='NOT_RUN_OFFLINE',live_price_verification='NOT_RUN_OFFLINE',
        database_accessed=False,trace_writable=True,
        code_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('scripts/milestone5c_pilot.py','scripts/dev_agent_evaluation.py','src/agent.py',
             'src/llm.py','src/retrieval.py','src/context.py')},
        case_results=[],errors=[])
    return report,cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['offline-preflight','run'],required=True)
    parser.add_argument('--dev',required=True,type=Path)
    parser.add_argument('--day6-root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--case-ids',nargs=3,default=list(CASE_IDS))
    parser.add_argument('--approve-paid-pilot',action='store_true')
    args=parser.parse_args()
    if tuple(args.case_ids)!=CASE_IDS:parser.error('Only fixed pilot IDs dev-06 dev-04 dev-17 are allowed')
    if args.mode=='run' and not args.approve_paid_pilot:parser.error('Paid pilot requires approval flag after review')
    trace_path=Path(str(args.output)+'.cases.jsonl')
    if args.output.exists() or trace_path.exists():parser.error('Output exists; preserve evidence')
    report,cases=offline_preflight(args.dev,args.day6_root,args.output)
    initial_calls=report['accounted_llm_requests']
    dense=None;before=None
    try:
        if args.mode=='run':
            report['key_budget']=verify_key_budget(RESERVATION*9)
            report['key_budget_verification']='PASS'
            report['catalog']=check_catalog();report['live_price_verification']='PASS'
            dense=d.DenseRetriever(d.Config(args.day6_root),d.load_embedder(d.Config(args.day6_root)))
            before=database_fingerprint(dense)
            chunks=load_snapshot(dense);validate_dev(cases,chunks)
            report['database_accessed']=True
            # One execution claim for the fixed 5C pilot ledger, across outputs.
            # Retain even after error/crash. Never reset or auto-replay.
            with Path(str(LEDGER)+'.execution-claim.json').open('x') as claim:
                json.dump(dict(output=str(args.output),case_ids=list(CASE_IDS)),claim)
                claim.flush();os.fsync(claim.fileno())
            budget=PilotBudget(LEDGER)
            result=evaluate_agent_dev(cases,chunks,PilotController(budget,cases),output=trace_path,
                request_count=lambda:budget.calls,case_ids=CASE_IDS)
            report.update(status=result['status'],case_results=result['cases'])
    except Exception as error:
        code=str(error) if isinstance(error,RuntimeError) else ''
        report.update(status='FAIL',errors=[code if code.isupper() and code.replace('_','').isalnum()
                                          else 'PILOT_PREFLIGHT_OR_EXECUTION_ERROR'])
    finally:
        state=ledger_state(LEDGER)
        report.update(accounted_llm_requests=state['calls'],reserved_usd=str(state['reserved']),
                      known_cost_usd=str(state['known_cost']),reported_cost_calls=state['reported_cost_calls'],
                      reported_cost_complete=state['reported_cost_calls']==state['calls'])
        if args.mode=='run':report['llm_requests_this_run']=state['calls']-initial_calls
        if before is not None:
            try:
                after=database_fingerprint(dense)
                report.update(database_before=before,database_after=after,database_unchanged=before==after)
                if before!=after:report.update(status='FAIL',errors=['DATABASE_CHANGED'])
            except Exception:report.update(status='FAIL',errors=['DATABASE_POSTCHECK_FAILED'])
        _,_,after_frozen=load_frozen_dev(args.dev)
        report['dataset_unchanged']=after_frozen==report['frozen']
        if not report['dataset_unchanged']:report.update(status='FAIL',errors=['DATASET_CHANGED'])
        with args.output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps(dict(status=report['status'],llm_requests_this_run=report['llm_requests_this_run'],
                          output=str(args.output))))
    return 0 if report['status']!='FAIL' else 1


if __name__=='__main__':sys.exit(main())
