"""One independent DEV experiment per invocation. Default CLI is offline-only."""
import argparse
from collections import Counter
from copy import deepcopy
from decimal import Decimal as D
import hashlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_improvement_experiments import prepare as verify_design, digest, read
from scripts.dev_agent_evaluation import automatic_checks, review_template
from scripts.dev_retrieval_benchmark import load_frozen_dev, validate_dev
from scripts.milestone4b_smoke import ByteBudget
from scripts.milestone5c_pilot import append_record, check_catalog, number
from scripts.dense_smoke import database_fingerprint
from src.agent import run_agent
from src.benchmark_data import load_offline_snapshot
from src.llm import PAID_MODEL, MODEL_PRICE_CAPS, _NoRedirect
from src.openrouter_paid import verify_key_budget
from src.retrieval import LexicalRetriever, load_snapshot
from src import dense as dense_module

MANIFEST = ROOT/'results/milestone5d1_offline/manifest.json'
READINESS = ROOT/'results/milestone5d1_offline/offline_readiness.json'
RESERVATION = D('.004')
DEPENDENCY_PIN = ROOT/'results/milestone5d3a_dependency_pin.json'
# Closed local import closure affecting preflight, inference, accounting or resume.
CODE_DEPENDENCIES = (
    'scripts/dev_improvement_experiment.py', 'scripts/milestone5c_pilot.py',
    'scripts/prepare_improvement_experiments.py', 'scripts/milestone5c_remaining.py',
    'scripts/dev_agent_evaluation.py', 'scripts/dev_retrieval_benchmark.py',
    'scripts/milestone4b_smoke.py', 'scripts/dense_smoke.py',
    'src/__init__.py', 'src/agent.py', 'src/llm.py', 'src/retrieval.py',
    'src/context.py', 'src/dense.py', 'src/benchmark_data.py', 'src/openrouter_paid.py',
    'starter/baseline.py', 'starter/agent_metrics.py')
DAY6_CODE_DEPENDENCIES = ('starter/src/__init__.py', 'starter/src/embeddings.py',
                          'starter/src/schema.py')
LOADED_CODE_HASHES = {p:digest(ROOT/p) for p in CODE_DEPENDENCIES}


def validate_dependencies(header=None, *, day6_root=None):
    """Require the reviewed external pin, never silently rebaseline changed code.

    Recheck disk hashes before metadata HTTP and each inference request. Old run
    identities without the complete dependency set are deliberately incompatible.
    This detects file drift, not malicious replacement of code and its trust pin.
    """
    pin = read(DEPENDENCY_PIN)
    expected = pin.get('code_sha256', {})
    external = pin.get('day6_code_sha256', {})
    if set(expected) != set(CODE_DEPENDENCIES) or set(external) != set(DAY6_CODE_DEPENDENCIES):
        raise RuntimeError('DEPENDENCY_PIN_INCOMPLETE')
    if header is not None and (header.get('code_sha256') != expected
        or header.get('day6_code_sha256') != external
        or header.get('dependency_pin_sha256') != digest(DEPENDENCY_PIN)
        or header.get('day6_root') != pin['day6_root']):
        raise RuntimeError('DEPENDENCY_IDENTITY_MISSING_OR_CHANGED')
    if day6_root is not None and str(Path(day6_root).resolve()) != pin['day6_root']:
        raise RuntimeError('DAY6_DEPENDENCY_ROOT_CHANGED')
    if LOADED_CODE_HASHES != expected or any(digest(ROOT/p) != h for p,h in expected.items()):
        raise RuntimeError('CODE_DEPENDENCY_CHANGED')
    if any(digest(Path(pin['day6_root'])/p) != h for p,h in external.items()):
        raise RuntimeError('DAY6_CODE_DEPENDENCY_CHANGED')
    return pin


def object_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def write_new(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())


def design(experiment, day6_root):
    """Read-only offline preflight; no new ledger, key/catalog request or DB."""
    if experiment not in ('E1', 'E2'):
        raise RuntimeError('SELECT_EXACTLY_ONE_EXPERIMENT')
    pin = validate_dependencies(day6_root=day6_root)
    expected, expected_replay = verify_design()
    manifest = read(MANIFEST)
    if manifest != expected or read(READINESS) != expected_replay:
        raise RuntimeError('OFFLINE_DESIGN_ARTIFACT_MISMATCH')
    _, cases, frozen = load_frozen_dev(ROOT/'data/benchmark/dev.json')
    chunks, _, identity = load_offline_snapshot(day6_root)
    if identity != frozen['identity']:
        raise RuntimeError('SNAPSHOT_IDENTITY_MISMATCH')
    validate_dev(cases, chunks)
    arm = manifest['experiments'][experiment]
    # Pin code, prompt, baseline, dataset, limits and exact IDs across resume.
    header = dict(event='allocation', experiment=experiment, model=PAID_MODEL,
        case_ids=manifest['case_ids'], config=arm['config'],
        prompt=arm['system_prompt'], prompt_sha256=arm['system_prompt_sha256'],
        limits=arm['limits'], envelope_usd=arm['proposed_envelope_usd'],
        reservation_usd=str(RESERVATION), manifest_sha256=digest(MANIFEST),
        baseline_accounting=manifest['accounting'], frozen=frozen,
        code_sha256=pin['code_sha256'], day6_code_sha256=pin['day6_code_sha256'],
        day6_root=pin['day6_root'], dependency_pin_sha256=digest(DEPENDENCY_PIN))
    return header, cases, chunks


def state(directory, header, *, active_case=None):
    """Unknown requests, partial cases, errors and stray checkpoints block resume."""
    directory = Path(directory)
    validate_dependencies(header)
    if read(directory/'identity.json') != header:
        raise RuntimeError('RUN_IDENTITY_MISMATCH')
    journal = directory/'requests.jsonl'
    rows = [json.loads(line) for line in journal.read_text().splitlines()]
    if not rows or rows[0] != header:
        raise RuntimeError('EXPERIMENT_IDENTITY_MISMATCH')
    calls = 0
    outcomes = 0
    per_case = Counter()
    completed = {}
    actual = D(0)
    case_outcomes = {}
    current_case = None
    for row in rows[1:]:
        event = row.get('event')
        if event == 'reserve':
            cid = row.get('case_id')
            current_case = cid
            calls += 1
            per_case[cid] += 1
            if (outcomes != calls-1 or cid not in header['case_ids'] or cid in completed
                or set(per_case)-set(completed) != {cid}
                or per_case[cid] > header['limits']['requests_per_case']
                or row.get('request') != calls
                or number(row.get('reserved_usd')) != calls*RESERVATION):
                raise RuntimeError('INVALID_RESERVATION_SEQUENCE')
        elif event == 'outcome':
            if row.get('request') != calls or outcomes != calls-1:
                raise RuntimeError('INVALID_OUTCOME_SEQUENCE')
            outcomes += 1
            if row.get('cost_usd') is None:
                raise RuntimeError('REQUEST_COST_UNKNOWN_STOP')
            actual += number(row['cost_usd'])
            case_outcomes.setdefault(current_case, []).append(row)
            if row.get('status') != 'ok' or number(row['cost_usd']) > RESERVATION:
                raise RuntimeError('PROVIDER_OR_USAGE_ERROR_STOP')
        elif event == 'case_complete':
            cid = row.get('case_id')
            if (outcomes != calls or cid in completed or cid not in per_case
                or set(per_case)-set(completed) != {cid}):
                raise RuntimeError('CASE_SEQUENCE_INVALID')
            file = directory/'checkpoints'/(cid+'.json')
            trace = read(file)
            decisions = sum(e['event'] == 'decision' for e in trace['events'])
            retrievals = sum(e['event'] == 'search' for e in trace['events'])
            if (object_hash(trace) != row.get('trace_sha256') or trace['query_id'] != cid
                or trace['status'] not in ('answered', 'abstain')
                or trace['llm_requests'] != per_case[cid] or decisions != per_case[cid]
                or retrievals > header['limits']['retrievals_per_case']
                or trace['config']['max_searches'] != header['config']['max_searches']):
                raise RuntimeError('CHECKPOINT_MISMATCH')
            usage = [e.get('llm', {}) for e in trace['events'] if e['event'] == 'decision']
            for llm, outcome in zip(usage, case_outcomes[cid]):
                u = llm.get('usage', {})
                if (llm.get('status') != 'ok' or llm.get('actual_model') != PAID_MODEL
                    or number(u.get('cost')) != number(outcome['cost_usd'])
                    or number(u.get('prompt_tokens')) > 26000 or number(u.get('completion_tokens')) > 512):
                    raise RuntimeError('CHECKPOINT_USAGE_MISMATCH')
            completed[cid] = trace
        else:
            raise RuntimeError('JOURNAL_ERROR_OR_UNKNOWN_EVENT')
    if outcomes != calls:
        raise RuntimeError('UNRESOLVED_REQUEST_STOP')
    partial = set(per_case)-set(completed)
    if partial and partial != {active_case}:
        raise RuntimeError('PARTIAL_CASE_REQUIRES_REVIEW')
    files = {p.stem for p in (directory/'checkpoints').glob('*.json')}
    if files != set(completed):
        raise RuntimeError('ORPHAN_OR_MISSING_CHECKPOINT')
    reserved = RESERVATION*calls
    if (calls > header['limits']['requests'] or reserved > number(header['envelope_usd'])
        or actual > number(header['envelope_usd'])):
        raise RuntimeError('EXPERIMENT_LIMIT_EXCEEDED')
    return dict(calls=calls, per_case=per_case, completed=completed, actual=actual, reserved=reserved)


class ExperimentBudget:
    def __init__(self, directory, header, *, verify=verify_key_budget):
        self.directory, self.header, self.verify = Path(directory), header, verify
        self.calls = state(directory, header)['calls']
        self.case_id = None
        self.stopped = False
        self.key_identity = hashlib.sha256(os.environ.get('OPENROUTER_API_KEY', '').encode()).digest()

    def before_request(self):
        s = state(self.directory, self.header, active_case=self.case_id)
        limit = self.header['limits']
        if (self.stopped or self.calls != s['calls'] or self.calls >= limit['requests']
            or self.case_id not in self.header['case_ids'] or self.case_id in s['completed']
            or s['per_case'][self.case_id] >= limit['requests_per_case']):
            raise RuntimeError('EXPERIMENT_REQUEST_LIMIT_STOP')
        if max(s['reserved'], s['actual'])+RESERVATION > number(self.header['envelope_usd']):
            raise RuntimeError('EXPERIMENT_USD_LIMIT_STOP')
        if self.key_identity != hashlib.sha256(os.environ.get('OPENROUTER_API_KEY', '').encode()).digest():
            raise RuntimeError('EXPERIMENT_KEY_CHANGED')
        validate_dependencies(self.header)
        self.verify((limit['requests']-self.calls)*RESERVATION)
        append_record(self.directory/'requests.jsonl', dict(event='reserve', request=self.calls+1,
            case_id=self.case_id, reserved_usd=str((self.calls+1)*RESERVATION)))
        self.calls += 1

    def outcome(self, trace):
        cost = None
        valid = False
        try:
            usage = trace['usage']
            cost = number(usage['cost'])
            valid = (trace['status'] == 'ok' and trace['actual_model'] == PAID_MODEL
                and cost <= RESERVATION and number(usage['prompt_tokens']) <= 26000
                and number(usage['completion_tokens']) <= 512)
        except (KeyError, RuntimeError, TypeError):
            pass
        append_record(self.directory/'requests.jsonl', dict(event='outcome', request=self.calls,
            status='ok' if valid else 'error', cost_usd=str(cost) if cost is not None else None,
            error=trace.get('error'), http_status=trace.get('http_status')))
        if not valid:
            self.stopped = True
            raise RuntimeError('EXPERIMENT_RESPONSE_UNVERIFIED_STOP')


class ExperimentController:
    """Same JSON-action contract/payload as baseline, with an instance-local prompt.

    No module-global SYSTEM override and no change to the baseline adapter.
    """
    def __init__(self, budget, prompt):
        self.budget, self.prompt = budget, prompt
        self.last_trace = None

    def decide(self, question, history):
        started = perf_counter()
        before = self.budget.calls
        self.last_trace = dict(provider='openrouter', model=PAID_MODEL, status='pending',
            service_cost_usd=None, cost_basis='provider usage.cost when available')
        try:
            if self.budget.stopped:
                raise RuntimeError('EXPERIMENT_STOPPED')
            key = os.environ.get('OPENROUTER_API_KEY', '').strip()
            if not key:
                raise RuntimeError('OPENROUTER_KEY_MISSING')
            user = json.dumps(dict(question=question, retrieval_history=history), ensure_ascii=False)
            messages = [dict(role='system', content=self.prompt), dict(role='user', content=user)]
            # UTF-8 byte upper bound with framing/output margin; not measured tokenization.
            if len(user.encode()) > 24000 or len(json.dumps(messages, ensure_ascii=False).encode())+1024 > 26000:
                raise RuntimeError('EXPERIMENT_INPUT_BUDGET_STOP')
            payload = dict(model=PAID_MODEL, stream=False, temperature=0, max_tokens=512,
                provider=dict(allow_fallbacks=False, require_parameters=True,
                    max_price=dict(MODEL_PRICE_CAPS[PAID_MODEL])), messages=messages)
            request = Request('https://openrouter.ai/api/v1/chat/completions',
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type':'application/json', 'Authorization':'Bearer '+key})
            opener = build_opener(_NoRedirect())
            self.budget.before_request()  # fsync reservation before the HTTP call
            validate_dependencies(self.budget.header)
            with opener.open(request, timeout=60) as response:
                result = json.load(response)
            usage = result.get('usage', {})
            safe_usage = {k:v for k,v in usage.items() if k in
                ('prompt_tokens', 'completion_tokens', 'total_tokens', 'cost')
                and type(v) in (int, float) and D(str(v)).is_finite() and v >= 0}
            self.last_trace.update(usage=safe_usage, service_cost_usd=safe_usage.get('cost'))
            actual = result.get('model')
            if isinstance(actual, str) and all(c.isalnum() or c in '/:._-' for c in actual):
                self.last_trace['actual_model'] = actual
            choice = result['choices'][0]
            self.last_trace['finish_reason'] = choice.get('finish_reason')
            if result.get('error') or choice.get('finish_reason') != 'stop':
                raise RuntimeError('OPENROUTER_PROVIDER_ERROR')
            action = json.loads(choice['message']['content'])
            if not isinstance(action, dict):
                raise RuntimeError('INVALID_LLM_OUTPUT')
            self.last_trace['status'] = 'ok'
        except Exception as error:
            self.budget.stopped = True
            timed_out = isinstance(error, TimeoutError) or (
                isinstance(error, URLError) and isinstance(error.reason, TimeoutError))
            code = 'LLM_TIMEOUT' if timed_out else 'LLM_ERROR'
            if isinstance(error, HTTPError):
                self.last_trace['http_status'] = error.code
                code = {401:'OPENROUTER_UNAUTHORIZED', 402:'OPENROUTER_PAYMENT_REQUIRED',
                        429:'OPENROUTER_RATE_LIMIT'}.get(error.code, 'OPENROUTER_PROVIDER_ERROR')
                error.close()
            elif isinstance(error, RuntimeError) and str(error).startswith(('EXPERIMENT_', 'OPENROUTER_')):
                code = str(error)
            self.last_trace.update(status='error', error=code)
            if self.budget.calls > before:
                try:
                    self.budget.outcome(self.last_trace)
                except RuntimeError:
                    pass  # Error outcome is durable; preserve timeout/provider classification.
            if timed_out:
                raise TimeoutError(code) from None
            raise RuntimeError(code) from None
        finally:
            self.last_trace['elapsed_ms'] = (perf_counter()-started)*1000
        try:
            self.budget.outcome(self.last_trace)
        except Exception:
            self.last_trace.update(status='error', error='EXPERIMENT_RESPONSE_UNVERIFIED_STOP')
            raise
        return action


def checkpoint(directory, row):
    directory = Path(directory)
    write_new(directory/'checkpoints'/(row['query_id']+'.json'), row)
    append_record(directory/'requests.jsonl', dict(event='case_complete',
        case_id=row['query_id'], trace_sha256=object_hash(row)))


def evaluate(cases, chunks, controller, budget, directory, header):
    """Same Agent/TF-IDF/trace schema; only arm max_searches differs."""
    s = state(directory, header)
    retriever = LexicalRetriever(chunks)
    for case in cases:
        if case['id'] in s['completed']:
            continue
        budget.case_id = case['id']
        before = budget.calls
        result = run_agent(case['question'], controller, retriever, filters=case.get('filter'),
            top_k=3, max_searches=header['config']['max_searches'], budget=12000, count_tokens=ByteBudget())
        row = dict(result, query_id=case['id'], split='dev', retrieval_method='lexical',
            llm_requests=budget.calls-before, cumulative_llm_requests=budget.calls,
            automatic=automatic_checks(case, result), manual_review=review_template(case, result))
        if result['status'] == 'error':
            write_new(Path(directory)/'failed_case.json', row)
            append_record(Path(directory)/'requests.jsonl', dict(event='case_error', case_id=case['id']))
            raise RuntimeError('EXPERIMENT_CASE_ERROR_STOP')
        checkpoint(directory, row)
        s = state(directory, header)
    return [s['completed'][cid] for cid in header['case_ids']]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--experiment', choices=['E1', 'E2'], required=True)
    parser.add_argument('--mode', choices=['offline-preflight', 'run'], default='offline-preflight')
    parser.add_argument('--day6-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--approve-paid-experiment', action='store_true')
    parser.add_argument('--approved-envelope-usd')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Output exists; use a new filename')
    if args.mode == 'run' and not args.approve_paid_experiment:
        parser.error('Explicit separate paid-experiment approval required')
    header, cases, offline_chunks = design(args.experiment, args.day6_root)
    directory = ROOT/'results'/('milestone5d_'+args.experiment.lower()+'_run')
    lock = ROOT/'results/milestone5d_experiment.lock'
    if lock.exists():
        raise RuntimeError('EXPERIMENT_BUSY_OR_STALE_LOCK')
    s = state(directory, header) if directory.exists() else dict(
        calls=0, completed={}, reserved=D(0), actual=D(0))
    if args.mode == 'offline-preflight':
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_new(args.output, dict(status='OFFLINE_PASS_NOT_AUTHORIZED', header=header,
            pending_case_ids=[c['id'] for c in cases if c['id'] not in s['completed']],
            requests=s['calls'], retained_reservations_usd=str(s['reserved']),
            actual_provider_cost_usd=str(s['actual']), snapshot_chunks=len(offline_chunks),
            new_api_calls=0, online_key_budget='NOT_CHECKED', online_pricing='NOT_CHECKED'))
        return
    if number(args.approved_envelope_usd) != number(header['envelope_usd']):
        parser.error('Approve the exact separate experiment envelope')
    if bool(directory.exists()) != args.resume:
        parser.error('Existing run requires --resume; new run must not use --resume')
    # All paid paths below require a separate explicit authorization at invocation.
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('x') as stream:
        stream.write(str(os.getpid())); stream.flush(); os.fsync(stream.fileno())
    report = dict(experiment=args.experiment, header=header, status='FAIL', errors=[])
    dense = None
    before_db = None
    try:
        if len(s['completed']) == 17:
            report.update(status='ALREADY_COMPLETE_NO_REQUESTS', case_results=[s['completed'][cid]
                for cid in header['case_ids']])
        else:
            validate_dependencies(header)
            verify_key_budget((header['limits']['requests']-s['calls'])*RESERVATION)
            validate_dependencies(header)
            check_catalog()
            report.update(key_budget_verification='PASS', pricing_verification='PASS')
            config = dense_module.Config(args.day6_root)
            dense = dense_module.DenseRetriever(config, dense_module.load_embedder(config))
            before_db = database_fingerprint(dense)
            chunks = load_snapshot(dense)
            validate_dev(cases, chunks)
            if not directory.exists():
                directory.mkdir()
                (directory/'checkpoints').mkdir()
                write_new(directory/'identity.json', header)
                append_record(directory/'requests.jsonl', header)
            budget = ExperimentBudget(directory, header)
            controller = ExperimentController(budget, header['prompt'])
            traces = evaluate(cases, chunks, controller, budget, directory, header)
            report.update(status='PENDING_MANUAL_REVIEW', case_results=traces)
    except Exception as error:
        code = str(error)
        report['errors'] = [code if code.isupper() and code.replace('_', '').isalnum()
                            else 'EXPERIMENT_PREFLIGHT_OR_RUN_ERROR']
    finally:
        try:
            if dense is not None and before_db is not None:
                report['database_unchanged'] = database_fingerprint(dense) == before_db
                if not report['database_unchanged']:
                    report.update(status='FAIL', errors=['DATABASE_FINGERPRINT_CHANGED'])
            if directory.exists():
                try:
                    final = state(directory, header)
                    report.update(requests=final['calls'], actual_provider_cost_usd=str(final['actual']),
                        retained_reservations_usd=str(final['reserved']),
                        completed_case_ids=list(final['completed']))
                except Exception:
                    # Never present unresolved cost/counters as stale zero values.
                    rows = [json.loads(line) for line in (directory/'requests.jsonl').read_text().splitlines()]
                    count = sum(r.get('event') == 'reserve' for r in rows)
                    report.update(status='FAIL', accounting_verification='UNRESOLVED_STOP',
                        requests=count, retained_reservations_usd=str(count*RESERVATION),
                        actual_provider_cost_usd=None)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            write_new(args.output, report)
        finally:
            lock.unlink()  # Only our owned lock; process crashes leave a stale lock for review.
    if report['status'] == 'FAIL':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
