"""DEV Agent evaluation preparation. CLI is offline-only; no inference entrypoint."""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.dev_retrieval_benchmark import load_frozen_dev, validate_dev
from scripts.milestone4b_smoke import ByteBudget
from src.agent import run_agent
from src.benchmark_data import load_offline_snapshot
from src.llm import PAID_MODEL, MODEL_PRICE_CAPS, SYSTEM
from src.retrieval import LexicalRetriever
from starter.agent_metrics import aggregate
from starter.baseline import hit

CONFIG = dict(method='lexical', top_k=3, max_searches=2, context_budget=12000,
              context_budget_unit=ByteBudget.name)


def cost_plan():
    """Proposal using configured provider price caps, not a current price quote."""
    caps = MODEL_PRICE_CAPS[PAID_MODEL]
    per_call = (Decimal(26000)*Decimal(str(caps['prompt'])) +
                Decimal(512)*Decimal(str(caps['completion'])))/Decimal(1000000)
    return dict(status='PROPOSED_NOT_AUTHORIZED', provider='openrouter', model=PAID_MODEL,
        cases=17, typical_llm_requests=34, max_llm_requests=51,
        max_requests_per_case=3, max_retrievals_per_case=2, timeout_seconds=60,
        max_output_tokens=512, retries=0, fallback=False,
        price_caps_usd_per_million=caps, assumed_input_token_upper_bound=26000,
        estimated_max_cost_usd=str(per_call*51), proposed_budget_usd='0.25',
        proposed_reservation_per_request_usd='0.004', proposed_total_reservation_usd='0.204',
        paid_execution_enabled=False,
        limitation='Estimate requires full-message input guard, price caps and new durable request/USD ledger before paid execution; framing is not measured by ByteBudget.')


def review_template(case, trace=None):
    citations = trace['citations'] if trace else []
    return dict(query_id=case['id'], status='PENDING_MANUAL_REVIEW',
        answer_correctness_grade=None, answer_grade=None, context_grade=None,
        citation_support=[None for _ in citations], citation_reasons=[None for _ in citations],
        abstention_correct=None, rationale=None)


def automatic_checks(case, trace):
    """Membership and frozen-gold coverage only: never semantic grading."""
    citations = trace['citations']
    context = json.loads(trace['context']) if trace['context'] else []
    attempts = [e for e in trace['events'] if e.get('event')=='decision' or
                (e.get('event')=='error' and e.get('stage')=='llm')]
    searches = [e for e in trace['events'] if e.get('event')=='search']
    usage = [e['llm'] for e in attempts if isinstance(e.get('llm'), dict)]
    totals = {}
    for field in ('prompt_tokens', 'completion_tokens', 'total_tokens'):
        values = [u.get('usage', {}).get(field) for u in usage]
        known = [v for v in values if type(v) in (int, float)]
        totals[field] = dict(known_sum=sum(known), reported_calls=len(known),
                            complete=len(known)==len(attempts))
    costs = [u.get('service_cost_usd') for u in usage]
    known_costs = [v for v in costs if type(v) in (int, float)]
    return dict(citation_membership=[c in trace['context_ids'] and c in trace['citation_map']
                                    for c in citations],
        citation_membership_rate=dict(n=sum(c in trace['citation_map'] and c in trace['context_ids']
                                            for c in citations), N=len(citations)),
        semantic_grounding='PENDING_MANUAL_REVIEW',
        context_gold_hit=(any(hit(c, case['gold']) for c in context) if case['answerable'] else None),
        retrieval_calls=len(searches),
        retrieval_attempts=len(searches)+sum(e.get('event')=='error' and
            e.get('stage')=='retrieval_context' for e in trace['events']),
        llm_decision_attempts=len(attempts), token_usage=totals,
        reported_cost_usd=dict(known_sum=sum(known_costs), reported_calls=len(known_costs),
                              complete=len(known_costs)==len(attempts)),
        errors=[dict(stage=e.get('stage'), error=e.get('error'))
                for e in trace['events'] if e.get('event')=='error'],
        termination=trace['events'][-1]['event'])


def evaluate_agent_dev(cases, chunks, controller, *, output, request_count, case_ids=None,
                       completed_case_ids=None, case_sink=None):
    """Reusable orchestration for later approval; tests inject mock controllers.

    Live caller must supply a newly authorized guarded controller and an actual
    pre-HTTP reservation counter. Decision attempts are NOT counted as HTTP calls.
    There is deliberately no CLI path that constructs a network controller here.
    chunks must be the existing load_snapshot() provenance-preserving rows.
    """
    validate_dev(cases, chunks)
    if len(cases)!=17 or sum(c['answerable'] for c in cases)!=15:
        raise ValueError('EXACT_17_DEV_REQUIRED')
    if case_ids is not None:
        by_id={c['id']:c for c in cases}
        if completed_case_ids is None:
            valid=len(case_ids)==3 and len(set(case_ids))==3
        else:
            done=set(completed_case_ids)
            valid=(len(done)==len(completed_case_ids) and done<=set(by_id)
                   and len(set(case_ids))==len(case_ids) and set(case_ids)==set(by_id)-done)
        if not valid or any(cid not in by_id for cid in case_ids):
            raise ValueError('INVALID_DEV_SELECTION_OR_COMPLETION_SET')
        cases=[by_id[cid] for cid in case_ids]
    # No method argument or Dense fallback: selected TF-IDF is constructed here.
    retriever = LexicalRetriever(chunks)
    traces = []
    stopped = False
    # Exclusive creation precedes the first controller call. Each case is flushed
    # immediately; a crash must never cause an automatic replay of paid calls.
    with Path(output).open('x', encoding='utf-8') as stream:
        for case in cases:
            if stopped:
                row = dict(query_id=case['id'], status='NOT_RUN_GLOBAL_STOP')
            else:
                before = request_count()
                if type(before) is not int or before<0:
                    raise ValueError('INVALID_REQUEST_COUNTER')
                result = run_agent(case['question'], controller, retriever,
                    filters=case.get('filter'), top_k=3, max_searches=2,
                    budget=12000, count_tokens=ByteBudget())
                after = request_count()
                if type(after) is not int or after<before:
                    raise ValueError('INVALID_REQUEST_COUNTER')
                row = dict(result, query_id=case['id'], split='dev', retrieval_method='lexical',
                    llm_requests=after-before, cumulative_llm_requests=after,
                    automatic=automatic_checks(case, result),
                    manual_review=review_template(case, result))
                stopped = result['status']=='error'
            traces.append(row)
            stream.write(json.dumps(row, ensure_ascii=False)+'\n')
            stream.flush()
            os.fsync(stream.fileno())
            if case_sink is not None:case_sink(row)
    return dict(status='PENDING_MANUAL_REVIEW' if not stopped else 'SYSTEM_ERROR',
        config=dict(CONFIG), cases=traces, system_errors=sum(t['status']=='error' for t in traces),
        not_run=sum(t['status']=='NOT_RUN_GLOBAL_STOP' for t in traces))


def score_reviewed(cases, traces, reviews):
    """Reuse rubric aggregator only after complete explicit human labels."""
    ids={c['id'] for c in cases}
    if (len(ids)!=len(cases) or len(traces)!=len(ids) or len(reviews)!=len(ids)
            or {t['query_id'] for t in traces}!=ids or {r['query_id'] for r in reviews}!=ids):
        raise ValueError('REVIEW_TRACE_CASE_IDS_MUST_MATCH')
    by_id={r['query_id']:r for r in reviews}
    trace_by_id={t['query_id']:t for t in traces}
    correctness=Counter(); contexts=Counter()
    for case in cases:
        t=trace_by_id[case['id']]; r=by_id[case['id']]
        if t['status']=='error':continue
        if t['status'] not in ('answered','abstain'):
            raise ValueError('INCOMPLETE_RUN_NO_FINAL_METRICS')
        if (r.get('status')!='REVIEWED' or not isinstance(r.get('rationale'),str)
                or not r['rationale'].strip()):
            raise ValueError('MANUAL_REVIEW_REQUIRED')
        support=r.get('citation_support'); reasons=r.get('citation_reasons')
        if (not isinstance(support,list) or len(support)!=len(t['citations'])
                or any(type(v) is not bool for v in support)
                or not isinstance(reasons,list) or len(reasons)!=len(support)
                or any(not isinstance(v,str) or not v.strip() for v in reasons)):
            raise ValueError('CITATION_SUPPORT_AND_REASONS_REQUIRED')
        if any(ok and (cid not in t['context_ids'] or cid not in t['citation_map'])
               for cid,ok in zip(t['citations'],support)):
            raise ValueError('SUPPORTED_CITATION_MUST_BE_IN_CONTEXT')
        if type(r.get('context_grade')) is not int or r['context_grade'] not in (0,1,2):
            raise ValueError('MANUAL_CONTEXT_GRADE_REQUIRED')
        if case['answerable']:
            contexts[str(r['context_grade'])]+=1
            grade=r.get('answer_correctness_grade')
            if type(grade) is not int or grade not in (0,1,2) or (t['status']=='abstain' and grade!=0):
                raise ValueError('MANUAL_ANSWER_CORRECTNESS_REQUIRED')
            correctness[str(grade)]+=1
    rubric=aggregate(cases,traces,reviews)
    # The starter labels ALL status=error as provider_errors. Clarify this name
    # here without changing its interface or hiding retrieval/context failures.
    rubric['system_errors']=rubric.pop('provider_errors')
    n=sum(correctness.values())
    rubric['answer_correctness']={str(g):correctness[str(g)] for g in (0,1,2)}
    rubric['answer_correctness'].update(N=n,
        mean=(correctness['1']+2*correctness['2'])/n if n else None,
        normalized_mean=(correctness['1']+2*correctness['2'])/(2*n) if n else None)
    rubric['grounded_answer']['normalized_mean']=(rubric['grounded_answer']['mean']/2
        if rubric['grounded_answer']['mean'] is not None else None)
    rubric['context_grades']={str(g):contexts[str(g)] for g in (0,1,2)}
    rubric['scheduled_cases']=len(cases)
    rubric['abstention_scheduled']=dict(n=rubric['abstention']['n'],
        N=sum(not c['answerable'] for c in cases))
    rubric['false_abstention_scheduled']=dict(n=rubric['false_abstention']['n'],
        N=sum(c['answerable'] for c in cases))
    rubric['retrieval_call_distribution']=dict(Counter(str(sum(e.get('event')=='search'
        for e in t.get('events',[]))) for t in traces))
    rubric['error_stages']=dict(Counter(e.get('stage','unknown') for t in traces
        for e in t.get('events',[]) if e.get('event')=='error'))
    return rubric


def prepare(dev, day6_root, output):
    if output.exists():raise ValueError('OUTPUT_EXISTS_PRESERVE_EVIDENCE')
    _,cases,frozen=load_frozen_dev(dev)
    chunks,_,identity=load_offline_snapshot(day6_root)
    if identity!=frozen['identity']:raise ValueError('FROZEN_SNAPSHOT_IDENTITY_MISMATCH')
    validate_dev(cases,chunks)
    if len(cases)!=17 or sum(c['answerable'] for c in cases)!=15:
        raise ValueError('EXACT_17_DEV_REQUIRED')
    report=dict(kind='milestone5c1_offline_readiness_not_agent_results',
        status='OFFLINE_READY_AWAITING_EXECUTION_APPROVAL', config=dict(CONFIG), frozen=frozen,
        snapshot_identity=identity, actual_llm_requests=0, retrieval_calls=0,
        database_accessed=False, live_database_preflight='NOT_RUN',
        key_budget_verification='NOT_RUN', cost_plan=cost_plan(),
        system_prompt_sha256=hashlib.sha256(SYSTEM.encode()).hexdigest(),
        code_sha256={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
            ('src/agent.py','src/llm.py','src/context.py','src/retrieval.py',
             'scripts/dev_agent_evaluation.py')},
        cases=[dict(query_id=c['id'], status='NOT_RUN', manual_review=review_template(c)) for c in cases])
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dev',required=True,type=Path)
    parser.add_argument('--day6-root',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    report=prepare(args.dev,args.day6_root,args.output)
    print(json.dumps(dict(status=report['status'],actual_llm_requests=0,output=str(args.output))))


if __name__=='__main__':main()
