"""Guarded terminal entrypoint. Default preflight performs no HTTP requests."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.agent import run_agent
from src import dense as d
from src.llm import OpenRouterController
from src.retrieval import load_snapshot
from src.context import pack_context
from scripts.dense_smoke import database_fingerprint

MODEL = 'qwen/qwen3-next-80b-a3b-instruct:free'
QUESTIONS = (
    ('A', 'What must non-null foreign key values match in the referenced table in PostgreSQL?'),
    ('B', 'What is the recommended watering schedule for a potted orchid in a tropical apartment?'),
)


class ByteBudget:
    # Qwen's byte-level BPE cannot need more text tokens than UTF-8 bytes.
    # This conservative bound is NOT a measured tokenizer count.
    name = 'utf8_byte_upper_bound_not_measured_model_tokens'

    def __call__(self, text):
        return len(text.encode('utf-8'))


class CallBudget:
    def __init__(self, used=0, journal=None):
        if type(used) is not int or not 0 <= used <= 6:
            raise ValueError('INVALID_PRIOR_CALL_COUNT')
        self.calls = used
        self.journal = journal
        self.stopped = False

    def before_request(self):
        if self.stopped or self.calls >= 6:
            raise RuntimeError('SMOKE_API_BUDGET_STOP')
        if self.journal is not None:
            # Persist reservation before HTTP, including errors/interruptions.
            with self.journal.open('a', encoding='utf-8') as stream:
                stream.write(json.dumps(dict(reserved_total=self.calls+1))+'\n')
                stream.flush()
                os.fsync(stream.fileno())
        self.calls += 1


def read_resume(path):
    """Only restart the explicitly approved authentication failure before retrieval.

    Other partial workflows need actual history restoration, not silent replay.
    """
    raw = path.read_bytes()
    prior = json.loads(raw)
    used = prior.get('llm_calls')
    cases = prior.get('cases', [])
    if (prior.get('kind') != 'milestone4b_smoke_not_benchmark'
            or prior.get('mode') != 'run' or prior.get('requested_model') != MODEL
            or prior.get('provider') != 'openrouter' or prior.get('status') != 'FAIL'
            or type(used) is not int or not 1 <= used <= 6
            or sum(c.get('llm_calls',0) for c in cases) != used
            or any(c.get('retrieval_calls',0) != 0 for c in cases)
            or any(c.get('status') not in ('error','NOT_RUN_GLOBAL_STOP') for c in cases)
            or not any(e.get('llm',{}).get('http_status') == 401
                       for c in cases for e in c.get('events',[]))):
        raise ValueError('UNSUPPORTED_OR_INVALID_RESUME_TRACE')
    return used, hashlib.sha256(raw).hexdigest()


def claim_resume(parent, output, used):
    # Exclusive marker prevents two processes/outputs spending the same allowance.
    # Never delete this marker automatically, even after a crash.
    with Path(str(parent)+'.resume-claim.json').open('x',encoding='utf-8') as stream:
        json.dump(dict(output=str(output.resolve()), inherited_calls=used),stream)
        stream.flush()
        os.fsync(stream.fileno())
    journal = Path(str(output)+'.requests.jsonl')
    with journal.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(dict(inherited_calls=used))+'\n')
        stream.flush()
        os.fsync(stream.fileno())
    return journal


class GuardedController:
    def __init__(self, budget):
        self.budget = budget
        self.backend = OpenRouterController(MODEL, timeout=60, max_output_tokens=512,
                                            request_guard=budget.before_request)
        self.last_trace = None

    def decide(self, question, history):
        if self.budget.stopped:
            raise RuntimeError('SMOKE_STOPPED')
        # Bound full user payload too; system prompt + message framing have ample
        # headroom below the model's 262K context, including 512 output tokens.
        if len(json.dumps(dict(question=question,retrieval_history=history)).encode()) > 24000:
            self.budget.stopped = True
            raise RuntimeError('SMOKE_INPUT_BUDGET')
        try:
            return self.backend.decide(question, history)
        except Exception:
            # Stop on ALL errors, including 401/402/429/timeout; never retry.
            self.budget.stopped = True
            raise
        finally:
            self.last_trace = self.backend.last_trace
            if self.last_trace and self.last_trace.get('service_cost_usd', 0):
                self.budget.stopped = True


class LimitedRetriever:
    def __init__(self, backend):
        self.backend, self.calls, self.last_trace = backend, 0, None

    def search(self, query, *, filters, top_k):
        if self.calls >= 2:
            raise RuntimeError('SMOKE_RETRIEVAL_LIMIT')
        self.calls += 1
        result = self.backend.search(query, filters=filters, top_k=top_k)
        self.last_trace = self.backend.last_trace
        return result


def benchmark_hashes():
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT/'data').glob('*')) if p.is_file()}


def prepare(day6_root):
    backend = d.DenseRetriever(d.Config(day6_root), d.load_embedder(d.Config(day6_root)))
    with backend.transaction() as conn:
        backend.preflight(conn)
    chunks = load_snapshot(backend)
    # No retrieval or gold selection: establish corpus coverage and ensure a whole
    # chunk can fit before any API request. Evidence is selected by the agent later.
    if not any('foreign key' in c['text'].casefold() for c in chunks):
        raise RuntimeError('SMOKE_FOREIGN_KEY_COVERAGE_MISSING')
    if any('orchid' in c['text'].casefold() for c in chunks):
        raise RuntimeError('SMOKE_OUT_OF_SCOPE_COVERAGE_AMBIGUOUS')
    if not any(pack_context([c], 12000, ByteBudget())['context_ids'] for c in chunks):
        raise RuntimeError('SMOKE_CONTEXT_BUDGET_TOO_SMALL')
    return backend, database_fingerprint(backend)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode', choices=['preflight','run'], required=True)
    parser.add_argument('--day6-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume-from', type=Path,
                        help='Prior failed-401 trace; consumes its remaining allowance once')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output already exists; choose a new path to preserve traces')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    used, parent_hash = 0, None
    if args.resume_from:
        if args.mode != 'run':
            parser.error('--resume-from requires --mode run')
        try:
            used, parent_hash = read_resume(args.resume_from)
        except Exception:
            parser.error('Invalid/unsupported resume trace; no calls made')
        if used >= 6:
            parser.error('API allowance exhausted; no calls made')
    elif args.mode == 'run':
        # Refuse accidental fresh runs when the repository already has spent calls.
        for path in (ROOT/'results').glob('milestone4b*.json'):
            try:
                prior = json.loads(path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                continue
            if prior.get('mode') == 'run' and prior.get('llm_calls',0):
                parser.error('Existing spent smoke allowance: use --resume-from')
    budget = CallBudget(used)
    report = dict(kind='milestone4b_smoke_not_benchmark', mode=args.mode,
        provider='openrouter', requested_model=MODEL, status='FAIL',
        inherited_llm_calls=used, resume_parent_sha256=parent_hash,
        resume_from=str(args.resume_from) if args.resume_from else None,
        config=dict(max_cases=2,max_llm_calls=6,max_retrieval_calls_per_case=2,
            max_searches=2,max_tokens=512,timeout=60,retries=0,fallback=False,
            price_caps=dict(prompt=0,completion=0),method='dense',top_k=3,
            context_budget=12000,context_budget_unit=ByteBudget.name,
            full_user_payload_max_bytes=24000), cases=[],errors=[])
    before_hashes = benchmark_hashes()
    backend, before_db = None, None
    try:
        report['key_present'] = bool(os.environ.get('OPENROUTER_API_KEY','').strip())
        if args.mode == 'run' and not report['key_present']:
            raise RuntimeError('OPENROUTER_KEY_MISSING')
        backend, before_db = prepare(args.day6_root)
        report.update(snapshot_chunks=264, snapshot_id=d.SNAPSHOT,
                      read_only=True, context_budget_check='PASS', coverage_check='PASS')
        report['preflight_status'] = 'PASS' if report['key_present'] else 'FAIL_KEY_MISSING'
        if args.mode == 'preflight':
            report['status'] = report['preflight_status']
        else:
            if args.resume_from:
                budget.journal = claim_resume(args.resume_from, args.output, used)
            controller = GuardedController(budget)  # one counter for both cases
            for cid, question in QUESTIONS:
                if budget.stopped:
                    report['cases'].append(dict(case_id=cid,status='NOT_RUN_GLOBAL_STOP'))
                    continue
                retriever = LimitedRetriever(backend)
                start_calls = budget.calls
                result = run_agent(question, controller, retriever, count_tokens=ByteBudget(),
                                   budget=12000, max_searches=2, top_k=3)
                result.update(case_id=cid,llm_calls=budget.calls-start_calls,
                    retrieval_calls=retriever.calls,retrieval_method='dense',
                    semantic_grounding='PENDING_MANUAL_REVIEW',
                    citation_membership_valid=all(c in result['citation_map'] for c in result['citations']))
                report['cases'].append(result)
                if result['status']=='error':
                    budget.stopped = True
            report['status'] = 'FAIL' if any(c['status']=='error' for c in report['cases']) else 'PENDING_MANUAL_REVIEW'
    except Exception as error:
        # No raw exceptions: they may contain DSN/provider details.
        known = str(error) if isinstance(error, (d.RetrievalError, RuntimeError)) else ''
        report['errors'].append(known if known.isupper() and known.replace('_','').isalnum()
                                else 'SMOKE_PREFLIGHT_OR_RUNTIME_ERROR')
        report['status'] = 'FAIL'
    finally:
        report['llm_calls'] = budget.calls
        report['llm_calls_this_run'] = budget.calls-used
        report['remaining_llm_calls'] = 6-budget.calls
        report['benchmark_unchanged'] = before_hashes == benchmark_hashes()
        report['database_before'] = before_db
        if backend is not None and before_db is not None:
            try:
                report['database_after'] = database_fingerprint(backend)
                report['database_unchanged'] = before_db == report['database_after']
            except Exception:
                report['database_unchanged'] = None
        if not report['benchmark_unchanged'] or (before_db is not None and
                                                report.get('database_unchanged') is not True):
            report['status'] = 'FAIL'
        with args.output.open('x',encoding='utf-8') as stream:
            json.dump(report, stream,ensure_ascii=False,indent=2)
        print(json.dumps(dict(status=report['status'],llm_calls=budget.calls,
                              errors=report['errors'],output=str(args.output))))
    return 0 if report['status'] in ('PASS','PENDING_MANUAL_REVIEW') else 1


if __name__ == '__main__':
    sys.exit(main())
