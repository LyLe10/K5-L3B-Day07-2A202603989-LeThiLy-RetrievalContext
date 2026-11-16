"""Remaining DEV phase; default preparation is offline, paid execution opt-in."""
import argparse
from collections import Counter
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.dev_agent_evaluation import CONFIG, evaluate_agent_dev, score_reviewed
from scripts.dev_retrieval_benchmark import load_frozen_dev, validate_dev
from scripts.milestone5c_pilot import (LEDGER as PILOT_LEDGER, ledger_state as pilot_state,
    PilotController, append_record, number, check_catalog, RESERVATION)
from scripts.dense_smoke import database_fingerprint
from src.benchmark_data import load_offline_snapshot
from src.openrouter_paid import verify_key_budget
from src.llm import PAID_MODEL, MODEL_PRICE_CAPS
from src import dense as d
from src.retrieval import load_snapshot

LEDGER=ROOT/'results/milestone5c3a_remaining_requests.jsonl'
PILOT=ROOT/'results/milestone5c2_paid_pilot.json'
REVIEWS=ROOT/'results/milestone5c2_manual_reviews.json'
SUMMARY=ROOT/'results/milestone5c2_reviewed_summary.json'
PHASE_USD=D('.20');DEV_USD=D('.25')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8'))


def derive_phase(cases,pilot,reviews,summary,pilot_ledger=PILOT_LEDGER):
    ids=[c['id'] for c in cases];traces=pilot['case_results'];done=[t['query_id'] for t in traces]
    if (len(ids)!=17 or len(set(ids))!=17 or len(done)!=3 or len(set(done))!=3
            or not set(done)<=set(ids) or done!=pilot['config']['case_ids']
            or any(t['status'] not in ('answered','abstain') for t in traces)):
        raise RuntimeError('PILOT_CASE_ACCOUNTING_INVALID')
    if any(pilot['config'].get(k)!=v for k,v in CONFIG.items()) or pilot['config']['model']!=PAID_MODEL:
        raise RuntimeError('PILOT_CONFIGURATION_MISMATCH')
    selected=[c for c in cases if c['id'] in done]
    if score_reviewed(selected,traces,reviews)!=summary['official_metrics']:
        raise RuntimeError('PILOT_REVIEW_MISMATCH')
    state=pilot_state(pilot_ledger)
    ledger_rows=[json.loads(line) for line in pilot_ledger.read_text().splitlines()]
    reservations=[r for r in ledger_rows if r['event']=='reserve']
    outcomes=[r for r in ledger_rows if r['event']=='outcome']
    if (len(outcomes)!=state['calls'] or state['reported_cost_calls']!=state['calls']
            or any(o['status']!='ok' or o['cost_usd'] is None for o in outcomes)):
        raise RuntimeError('PILOT_ACCOUNTING_UNCERTAIN')
    usage=[(t['query_id'],e['llm']) for t in traces for e in t['events'] if e['event']=='decision']
    if len(usage)!=state['calls'] or sum(t['llm_requests'] for t in traces)!=state['calls']:
        raise RuntimeError('PILOT_USAGE_COUNT_MISMATCH')
    for i,((cid,llm),reserve,outcome) in enumerate(zip(usage,reservations,outcomes),1):
        if (reserve['request']!=i or outcome['request']!=i or reserve['case_id']!=cid
                or llm['status']!='ok' or llm.get('actual_model')!=PAID_MODEL
                or number(llm['usage'].get('cost'))!=number(outcome['cost_usd'])):
            raise RuntimeError('PILOT_USAGE_LEDGER_MISMATCH')
    if (number(pilot['known_cost_usd'])!=state['known_cost'] or number(pilot['reserved_usd'])!=state['reserved']
            or pilot['accounted_llm_requests']!=state['calls']):
        raise RuntimeError('PILOT_TOTALS_MISMATCH')
    # Exact set difference, retaining frozen DEV order; no question-ID literals.
    remaining=[cid for cid in ids if cid not in set(done)]
    if len(remaining)!=14:raise RuntimeError('EXACT_14_REMAINING_REQUIRED')
    return dict(event='allocation',scope='DEV_REMAINING',case_ids=remaining,pilot_ids=done,
        inherited_calls=state['calls'],inherited_reserved_usd=str(state['reserved']),
        inherited_actual_usd=str(state['known_cost']),parent_ledger_sha256=sha(pilot_ledger),
        max_new_calls=42,max_calls_per_case=3,max_retrievals_per_case=2,
        phase_usd=str(PHASE_USD),dev_usd=str(DEV_USD),model=PAID_MODEL,config=dict(CONFIG))


def phase_state(path,header,*,require_checkpoints=True):
    rows=[json.loads(line) for line in path.read_text().splitlines()]
    if not rows or rows[0]!=header:raise RuntimeError('PHASE_LEDGER_IDENTITY_MISMATCH')
    calls=0;per_case=Counter();outcomes=set();completed={};actual=D('0');errors=False
    for row in rows[1:]:
        event=row.get('event')
        if event=='reserve':
            if len(outcomes)!=calls:raise RuntimeError('UNRESOLVED_REQUEST')
            calls+=1;cid=row.get('case_id');per_case[cid]+=1
            if (cid not in header['case_ids'] or cid in completed or per_case[cid]>3 or row.get('request')!=calls
                    or row.get('reserved_usd')!=str(calls*RESERVATION)):
                raise RuntimeError('PHASE_RESERVATION_INVALID')
        elif event=='outcome':
            if row.get('request')!=calls or calls in outcomes:raise RuntimeError('PHASE_OUTCOME_INVALID')
            outcomes.add(calls)
            if row.get('cost_usd') is None:raise RuntimeError('REQUEST_COST_UNKNOWN')
            actual+=number(row['cost_usd'])
            errors=errors or row.get('status')!='ok'
        elif event=='case_complete':
            cid=row.get('case_id')
            if cid in completed or cid not in header['case_ids'] or len(outcomes)!=calls:
                raise RuntimeError('CASE_CHECKPOINT_INVALID')
            trace=read(Path(row['trace_file']))
            if (digest(trace)!=row['trace_sha256'] or trace['query_id']!=cid
                    or trace['status'] not in ('answered','abstain') or trace['llm_requests']!=per_case[cid]):
                raise RuntimeError('CASE_CHECKPOINT_MISMATCH')
            completed[cid]=trace
        elif event=='case_error':errors=True
        else:raise RuntimeError('PHASE_LEDGER_EVENT_INVALID')
    if len(outcomes)!=calls:raise RuntimeError('UNRESOLVED_REQUEST')
    if errors:raise RuntimeError('PHASE_ERROR_REQUIRES_MANUAL_REVIEW')
    if require_checkpoints and set(per_case)-set(completed):
        raise RuntimeError('REQUESTS_WITHOUT_CASE_CHECKPOINT')
    reserved=calls*RESERVATION
    if (calls>42 or reserved>PHASE_USD or actual>PHASE_USD
            or number(header['inherited_reserved_usd'])+reserved>DEV_USD
            or number(header['inherited_actual_usd'])+actual>DEV_USD
            or header['inherited_calls']+calls>51):
        raise RuntimeError('PHASE_OR_DEV_LIMIT_EXCEEDED')
    return dict(calls=calls,per_case=per_case,completed=completed,reserved=reserved,actual=actual)


class RemainingBudget:
    def __init__(self,path,header,*,verify=verify_key_budget):
        self.path=path;self.header=header;self.verify=verify;self.case_id=None;self.stopped=False
        state=phase_state(path,header)
        self.calls=header['inherited_calls']+state['calls']
        self.key_hash=hashlib.sha256(os.environ.get('OPENROUTER_API_KEY','').encode()).digest()

    def before_request(self):
        state=phase_state(self.path,self.header,require_checkpoints=False)
        if (self.stopped or self.calls!=self.header['inherited_calls']+state['calls'] or state['calls']>=42
                or self.case_id not in self.header['case_ids'] or self.case_id in state['completed']
                or state['per_case'][self.case_id]>=3):raise RuntimeError('PHASE_REQUEST_LIMIT_STOP')
        reserved=state['reserved']+RESERVATION
        if (reserved>PHASE_USD or number(self.header['inherited_reserved_usd'])+reserved>DEV_USD
                or state['actual']+RESERVATION>PHASE_USD
                or number(self.header['inherited_actual_usd'])+state['actual']+RESERVATION>DEV_USD):
            raise RuntimeError('PHASE_USD_LIMIT_STOP')
        if self.key_hash!=hashlib.sha256(os.environ.get('OPENROUTER_API_KEY','').encode()).digest():
            raise RuntimeError('PHASE_KEY_CHANGED')
        self.verify((42-state['calls'])*RESERVATION)
        append_record(self.path,dict(event='reserve',request=state['calls']+1,case_id=self.case_id,
                                    reserved_usd=str(reserved)))
        self.calls+=1

    def outcome(self,trace):
        usage=trace.get('usage',{});cost=None;valid=False
        try:
            cost=number(usage['cost'])
            valid=(trace.get('status')=='ok' and trace.get('actual_model')==PAID_MODEL
                and cost<=RESERVATION and number(usage['prompt_tokens'])<=26000
                and number(usage['completion_tokens'])<=512)
        except Exception:pass
        append_record(self.path,dict(event='outcome',request=self.calls-self.header['inherited_calls'],
            status='ok' if valid else 'error',cost_usd=str(cost) if cost is not None else None,
            error=trace.get('error'),http_status=trace.get('http_status')))
        if not valid:self.stopped=True;raise RuntimeError('PHASE_RESPONSE_OR_USAGE_UNVERIFIED')


def checkpoint(path,row,directory):
    if row['status']=='NOT_RUN_GLOBAL_STOP':return
    if row['status']=='error':
        append_record(path,dict(event='case_error',case_id=row['query_id']));return
    directory.mkdir(parents=True,exist_ok=True)
    file=directory/(row['query_id']+'.json')
    with file.open('x',encoding='utf-8') as stream:
        json.dump(row,stream,ensure_ascii=False);stream.flush();os.fsync(stream.fileno())
    append_record(path,dict(event='case_complete',case_id=row['query_id'],
        trace_file=str(file.resolve()),trace_sha256=digest(row)))


def prepare(dev,day6_root,output,*,resume=False,ledger=LEDGER):
    if output.exists() or Path(str(output)+'.cases.jsonl').exists():raise RuntimeError('OUTPUT_EXISTS')
    if Path(str(ledger)+'.lock').exists():raise RuntimeError('PHASE_BUSY_OR_STALE_LOCK')
    _,cases,frozen=load_frozen_dev(dev)
    pilot=read(PILOT);reviews=read(REVIEWS);summary=read(SUMMARY)
    for name,value in summary['protected_input_sha256'].items():
        if sha(Path(name))!=value:raise RuntimeError('PILOT_REVIEWED_INPUT_CHANGED')
    if frozen!=pilot['frozen']:raise RuntimeError('FROZEN_DATASET_CHANGED')
    header=derive_phase(cases,pilot,reviews,summary)
    chunks,_,identity=load_offline_snapshot(day6_root)
    if identity!=frozen['identity']:raise RuntimeError('SNAPSHOT_IDENTITY_MISMATCH')
    validate_dev(cases,chunks)
    header.update(frozen=frozen,pilot_trace_sha256=sha(PILOT),reviews_sha256=sha(REVIEWS),
        code_sha256={name:sha(ROOT/name) for name in ('src/agent.py','src/llm.py','src/retrieval.py',
            'src/context.py','scripts/dev_agent_evaluation.py','scripts/milestone5c_pilot.py',
            'scripts/milestone5c_remaining.py')})
    output.parent.mkdir(parents=True,exist_ok=True);ledger.parent.mkdir(parents=True,exist_ok=True)
    if not ledger.exists():
        if resume:raise RuntimeError('RESUME_LEDGER_MISSING')
        with ledger.open('x') as stream:
            stream.write(json.dumps(header)+'\n');stream.flush();os.fsync(stream.fileno())
    state=phase_state(ledger,header)
    if state['calls'] and not resume:raise RuntimeError('EXPLICIT_RESUME_REQUIRED')
    pending=[cid for cid in header['case_ids'] if cid not in state['completed']]
    report=dict(kind='milestone5c_remaining',status='OFFLINE_PASS_PENDING_APPROVAL',header=header,
        pending_case_ids=pending,completed_case_ids=list(state['completed']),snapshot_chunks=len(chunks),
        inherited_requests=header['inherited_calls'],phase_requests=state['calls'],
        cumulative_requests=header['inherited_calls']+state['calls'],
        actual_provider_cost_usd=str(number(header['inherited_actual_usd'])+state['actual']),
        cumulative_reserved_usd=str(number(header['inherited_reserved_usd'])+state['reserved']),
        remaining_dev_after_actual_usd=str(DEV_USD-number(header['inherited_actual_usd'])-state['actual']),
        remaining_dev_after_reservation_usd=str(DEV_USD-number(header['inherited_reserved_usd'])-state['reserved']),
        remaining_phase_envelope_usd=str(PHASE_USD-state['reserved']),
        max_new_reservation_usd=str((42-state['calls'])*RESERVATION),
        estimated_max_42_request_cost_usd='0.13878144',
        key_budget_verification='NOT_RUN_OFFLINE',pricing_verification='NOT_RUN_OFFLINE',
        key_present=bool(os.environ.get('OPENROUTER_API_KEY','').strip()),
        new_llm_requests=0,database_accessed=False,errors=[])
    return report,cases


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['offline-preflight','run'],required=True)
    parser.add_argument('--dev',type=Path,required=True);parser.add_argument('--day6-root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--resume',action='store_true')
    parser.add_argument('--approve-paid-dev',action='store_true')
    args=parser.parse_args()
    if args.mode=='run' and not args.approve_paid_dev:parser.error('Explicit paid DEV approval required')
    if args.output.exists() or Path(str(args.output)+'.cases.jsonl').exists():
        parser.error('Output exists; preserve evidence')
    report=None;lock=None;lock_owned=False;dense=None;before=None;initial=0
    try:
        report,cases=prepare(args.dev,args.day6_root,args.output,resume=args.resume)
        initial=report['phase_requests'];header=report['header']
        if args.mode=='run' and report['pending_case_ids']:
            lock=Path(str(LEDGER)+'.lock')
            # A stale crash lock is never removed automatically by another run.
            with lock.open('x') as stream:stream.write(str(os.getpid()));stream.flush();os.fsync(stream.fileno())
            lock_owned=True
            report['key_budget']=verify_key_budget((42-initial)*RESERVATION)
            report['key_budget_verification']='PASS';report['catalog']=check_catalog();report['pricing_verification']='PASS'
            dense=d.DenseRetriever(d.Config(args.day6_root),d.load_embedder(d.Config(args.day6_root)))
            before=database_fingerprint(dense);chunks=load_snapshot(dense);validate_dev(cases,chunks)
            report['database_accessed']=True
            budget=RemainingBudget(LEDGER,header)
            controller=PilotController(budget,cases,allowed_case_ids=header['case_ids'])
            done=header['pilot_ids']+report['completed_case_ids']
            result=evaluate_agent_dev(cases,chunks,controller,output=Path(str(args.output)+'.cases.jsonl'),
                request_count=lambda:budget.calls,case_ids=report['pending_case_ids'],completed_case_ids=done,
                case_sink=lambda row:checkpoint(LEDGER,row,Path(str(args.output)+'.case-records')))
            report.update(status=result['status'],case_results=result['cases'])
        elif args.mode=='run':report['status']='ALREADY_COMPLETE_NO_REQUESTS'
    except Exception as error:
        code=str(error) if isinstance(error,RuntimeError) else ''
        if report is None:report=dict(status='FAIL',new_llm_requests=0)
        report.update(status='FAIL',errors=[code if code.isupper() and code.replace('_','').isalnum() else 'PHASE_PREFLIGHT_OR_RUN_ERROR'])
    finally:
        if report is not None:
            if 'header' in report:
                try:
                    state=phase_state(LEDGER,report['header'])
                    report.update(phase_requests=state['calls'],new_llm_requests=state['calls']-initial,
                        cumulative_requests=report['header']['inherited_calls']+state['calls'],
                        actual_provider_cost_usd=str(number(report['header']['inherited_actual_usd'])+state['actual']),
                        cumulative_reserved_usd=str(number(report['header']['inherited_reserved_usd'])+state['reserved']),
                        remaining_dev_after_actual_usd=str(DEV_USD-number(report['header']['inherited_actual_usd'])-state['actual']),
                        remaining_dev_after_reservation_usd=str(DEV_USD-number(report['header']['inherited_reserved_usd'])-state['reserved']),
                        remaining_phase_envelope_usd=str(PHASE_USD-state['reserved']))
                except Exception:
                    # An attempted request may exist even when settlement or a
                    # checkpoint is missing. Never report stale zero-cost/counts.
                    report.update(status='FAIL',errors=['ACCOUNTING_OR_CHECKPOINT_REQUIRES_REVIEW'],
                        accounting_verification='UNRESOLVED_STOP',new_llm_requests=None,
                        phase_requests=None,cumulative_requests=None,actual_provider_cost_usd=None,
                        cumulative_reserved_usd=None,remaining_dev_after_actual_usd=None,
                        remaining_dev_after_reservation_usd=None,remaining_phase_envelope_usd=None)
                try:
                    if load_frozen_dev(args.dev)[2]!=report['header']['frozen']:raise RuntimeError()
                    for name,value in read(SUMMARY)['protected_input_sha256'].items():
                        if sha(Path(name))!=value:raise RuntimeError()
                    report['dataset_and_pilot_unchanged']=True
                except Exception:report.update(status='FAIL',errors=['PROTECTED_INPUT_CHANGED'])
            if before is not None:
                try:
                    after=database_fingerprint(dense);report['database_unchanged']=before==after
                    if before!=after:report.update(status='FAIL',errors=['DATABASE_CHANGED'])
                except Exception:report.update(status='FAIL',errors=['DATABASE_POSTCHECK_FAILED'])
            with args.output.open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
        # A crash leaves a stale lock requiring manual inspection, never theft.
        if lock_owned:lock.unlink()
    print(json.dumps(dict(status=report['status'],output=str(args.output),new_llm_requests=report.get('new_llm_requests',0))))
    return 1 if report['status']=='FAIL' else 0


if __name__=='__main__':sys.exit(main())
