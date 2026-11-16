"""Paid terminal runner; preflight uses metadata GET, never inference POST."""
import argparse
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.llm import OpenRouterController, PAID_MODEL, MODEL_PRICE_CAPS, SYSTEM
from src.openrouter_paid import (PaidBudget, verify_key_budget, validate_paid_resume,
    PAID_ALLOWLIST, MAX_FOUR_CALL_COST, PER_REQUEST_RESERVATION, USD_LIMIT, KeyBudgetError)
from src.agent import run_agent
from scripts.milestone4b_smoke import (QUESTIONS, ByteBudget, LimitedRetriever,
    prepare, benchmark_hashes, claim_resume)
from scripts.dense_smoke import database_fingerprint


class PaidController:
    def __init__(self,budget):
        self.budget = budget
        if PAID_MODEL not in PAID_ALLOWLIST:
            raise RuntimeError('MODEL_NOT_APPROVED')
        self.backend = OpenRouterController(PAID_MODEL,timeout=60,max_output_tokens=512,
                                            request_guard=budget.before_request)
        self.last_trace = None

    def decide(self,question,history):
        if self.budget.stopped:
            raise RuntimeError('SMOKE_STOPPED')
        user = json.dumps(dict(question=question,retrieval_history=history),ensure_ascii=False)
        # Same context selection as before; additional transport/accounting guard.
        if len(user.encode()) > 24000 or len(SYSTEM.encode())+len(user.encode())+512 > 26000:
            self.budget.stopped = True
            raise RuntimeError('SMOKE_INPUT_BUDGET')
        try:
            action = self.backend.decide(question,history)
            self.budget.record_usage(self.backend.last_trace)
            return action
        except Exception:
            self.budget.stopped = True
            raise
        finally:
            self.last_trace = self.backend.last_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=['key-preflight','preflight','run'],required=True)
    parser.add_argument('--resume-from',type=Path,required=True)
    parser.add_argument('--day6-root',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--approve-paid-inference',action='store_true')
    args = parser.parse_args()
    if args.mode != 'key-preflight' and args.day6_root is None:
        parser.error('--day6-root required')
    if args.mode == 'run' and not args.approve_paid_inference:
        parser.error('Paid run requires --approve-paid-inference after review')
    if args.output.exists() or Path(str(args.output)+'.requests.jsonl').exists():
        parser.error('Output/evidence already exists; never overwrite')
    report = dict(kind='milestone4b_paid_smoke_not_benchmark',mode=args.mode,status='FAIL',
        requested_model=PAID_MODEL,provider='openrouter',resume_from=str(args.resume_from),
        inherited_llm_calls=2,llm_calls=2,llm_calls_this_run=0,remaining_llm_calls=4,
        config=dict(max_llm_calls=6,max_cases=2,max_retrieval_calls_per_case=2,
            timeout=60,max_tokens=512,retries=0,fallback=False,method='dense',top_k=3,
            price_caps_per_million=MODEL_PRICE_CAPS[PAID_MODEL],usd_limit=str(USD_LIMIT),
            reservation_per_request_usd=str(PER_REQUEST_RESERVATION),
            estimated_max_four_call_cost_usd=str(MAX_FOUR_CALL_COST),
            context_budget=12000,context_budget_unit=ByteBudget.name),
        cases=[],errors=[],key_budget_verification='NOT_VERIFIED',metadata_checks=0)
    backend,before_db,budget = None,None,None
    hashes = benchmark_hashes()
    try:
        report['resume_parent_sha256'] = validate_paid_resume(args.resume_from)
        # Metadata check before expensive DB/model work or any resume claim.
        report['metadata_checks'] += 1
        report['key_budget'] = verify_key_budget()
        report['key_budget_verification'] = 'PASS'
        if Path(str(args.resume_from)+'.resume-claim.json').exists():
            raise RuntimeError('RESUME_SOURCE_ALREADY_CLAIMED')
        if args.mode != 'key-preflight':
            backend,before_db = prepare(args.day6_root)
            report.update(snapshot_chunks=264,read_only=True,context_budget_check='PASS')
        if args.mode != 'run':
            report['status']='PASS'
        else:
            journal = claim_resume(args.resume_from,args.output,2)
            budget = PaidBudget(journal,verify=verify_key_budget)
            controller = PaidController(budget)
            for cid,question in QUESTIONS:
                if budget.stopped or budget.calls>=6:
                    report['cases'].append(dict(case_id=cid,status='NOT_RUN_GLOBAL_STOP'))
                    continue
                retriever = LimitedRetriever(backend)
                start = budget.calls
                result = run_agent(question,controller,retriever,count_tokens=ByteBudget(),
                                   budget=12000,max_searches=2,top_k=3)
                result.update(case_id=cid,llm_calls=budget.calls-start,retrieval_calls=retriever.calls,
                    retrieval_method='dense',semantic_grounding='PENDING_MANUAL_REVIEW',
                    citation_membership_valid=all(c in result['citation_map'] for c in result['citations']))
                report['cases'].append(result)
                if result['status']=='error':
                    budget.stopped=True
            report['status']=('PENDING_MANUAL_REVIEW' if len(report['cases'])==2
                and all(c['status'] in ('answered','abstain') for c in report['cases']) else 'FAIL')
    except Exception as error:
        # Only locally defined fixed codes can enter reports, never raw HTTP/DSN.
        safe = str(error) if isinstance(error,RuntimeError) else ''
        if isinstance(error,KeyBudgetError):
            report['key_budget_diagnostics'] = error.diagnostics
        report['errors'].append(safe if safe and safe.isupper() and safe.replace('_','').isalnum()
                                else 'PAID_PREFLIGHT_OR_RUNTIME_ERROR')
        report['status']='FAIL'
    finally:
        if budget is not None:
            report.update(llm_calls=budget.calls,llm_calls_this_run=budget.calls-2,
                remaining_llm_calls=6-budget.calls,reserved_usd=str(budget.reserved_usd),
                known_response_cost_sum_usd=str(budget.actual_usd),
                provider_reported_cost_usd=(str(budget.actual_usd)
                    if budget.settled_calls==budget.calls-2 else None),
                metadata_checks=report['metadata_checks']+budget.metadata_checks)
        report['benchmark_unchanged']=hashes==benchmark_hashes()
        if before_db is not None:
            report['database_before']=before_db
            try:
                report['database_after']=database_fingerprint(backend)
                report['database_unchanged']=before_db==report['database_after']
            except Exception:
                report['database_unchanged']=None
            if report['database_unchanged'] is not True:
                report['status']='FAIL'
        if not report['benchmark_unchanged']:
            report['status']='FAIL'
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump(report,stream,ensure_ascii=False,indent=2)
        print(json.dumps(dict(status=report['status'],llm_calls=report['llm_calls'],
            key_budget_verification=report['key_budget_verification'],errors=report['errors'],
            output=str(args.output))))
    return 0 if report['status'] in ('PASS','PENDING_MANUAL_REVIEW') else 1


if __name__=='__main__':
    sys.exit(main())
