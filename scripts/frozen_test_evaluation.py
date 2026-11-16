"""Frozen TEST orchestration. Import/default CLI never executes held-out cases.

Reuse the evaluated controller, Agent and durable accounting, never DEV design()
or its fixed directories. Paid execution requires separate explicit approval.
"""
import argparse
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import dev_improvement_experiment as dev
from src.llm import SYSTEM

LOCK = 'results/milestone5d_e1_final_configuration_lock.json'
LOCK_SHA = '87febe40ba9ba2c2e3204333e75b1578e830bb10469b29e3d4116be353e5579e'
PIN = 'results/milestone6_test_runner_offline_validation.json'
SELF = 'scripts/frozen_test_evaluation.py'
ENVELOPE = Decimal('.084')
LOADED_SHA = dev.digest(ROOT/SELF)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def configuration(root=ROOT):
    """Verify the approved lock and existing runtime; no TEST content parsing."""
    root = Path(root)
    if dev.digest(root/LOCK) != LOCK_SHA:
        raise RuntimeError('TEST_LOCK_INVALID')
    lock = read(root/LOCK)
    if (lock['status'] != 'E1_LOCKED' or lock['selected_variant'] != 'E1'
            or lock['approval_scope'] != 'configuration_lock_only'):
        raise RuntimeError('TEST_LOCK_INVALID')
    candidate = read(root/lock['provenance']['candidate_manifest'])
    config = lock['verified_configuration']
    if (config != {k:candidate[k] for k in config}
            or dev.digest(root/lock['provenance']['candidate_manifest']) != lock['provenance']['candidate_manifest_sha256']
            or dev.digest(root/lock['provenance']['selection_gate']) != lock['provenance']['selection_gate_sha256']
            or hashlib.sha256(config['system_prompt'].encode()).hexdigest() != config['system_prompt_sha256']):
        raise RuntimeError('TEST_CONFIG_MISMATCH')
    if (config['retrieval'] != dict(method='lexical',top_k=3,max_searches=2,
            context_budget=12000,context_budget_unit='utf8_byte_upper_bound_not_measured_model_tokens')
            or config['generation'] != dict(temperature=0,max_tokens=512,timeout_seconds=60,stream=False)
            or config['model'] != dev.PAID_MODEL or config['provider'] != 'openrouter'
            or config['request_limits']['retries'] != 0
            or config['request_limits']['fallback'] is not False
            or config['provider_routing']['allow_fallbacks'] is not False
            or config['provider_routing']['max_price_usd_per_million'] != dev.MODEL_PRICE_CAPS[dev.PAID_MODEL]):
        raise RuntimeError('TEST_CONFIG_MISMATCH')
    pin = dev.validate_dependencies()
    if (pin['code_sha256'] != lock['provenance']['code_sha256']
            or pin['day6_code_sha256'] != lock['provenance']['day6_code_sha256']
            or dev.digest(dev.DEPENDENCY_PIN) != lock['provenance']['dependency_pin_sha256']):
        raise RuntimeError('TEST_DEPENDENCY_MISMATCH')
    return lock, config, pin


def metadata(config, root=ROOT):
    """Hash both splits; extract only TEST ID fields, never questions/gold."""
    root = Path(root)
    frozen = config['frozen_benchmark']
    directory = root/'data/benchmark'
    if (dev.digest(directory/'manifest.json') != frozen['manifest_sha256']
            or dev.digest(directory/'manifest.sha256') != frozen['manifest_pin_sha256']
            or any(dev.digest(directory/name) != value for name,value in frozen['files_sha256'].items())):
        raise RuntimeError('TEST_FROZEN_HASH_CHANGED')
    ids = [s.decode('ascii') for s in re.findall(rb'"id"\s*:\s*"(test-[0-9]+)"',
                                              (directory/'test.json').read_bytes())]
    if len(ids) != 7 or len(set(ids)) != 7:
        raise RuntimeError('TEST_SEVEN_UNIQUE_IDS_REQUIRED')
    return ids


def design(variant, root=ROOT):
    if variant not in ('baseline','E1'):
        raise RuntimeError('TEST_SELECT_ONE_VARIANT')
    lock, config, pin = configuration(root)
    ids = metadata(config, root)
    prompt = config['system_prompt'] if variant == 'E1' else SYSTEM
    return dict(event='allocation',scope='FROZEN_TEST',split='test',variant=variant,
        case_ids=ids,model=config['model'],config=config['retrieval'],prompt=prompt,
        prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),lock_sha256=LOCK_SHA,
        frozen=config['frozen_benchmark'],limits=dict(cases=7,requests=21,
            requests_per_case=3,retrievals_per_case=2,retries=0,fallback=False),
        envelope_usd=str(ENVELOPE),reservation_usd=str(dev.RESERVATION),
        code_sha256=pin['code_sha256'],day6_code_sha256=pin['day6_code_sha256'],
        day6_root=pin['day6_root'],dependency_pin_sha256=dev.digest(dev.DEPENDENCY_PIN),
        test_runner_sha256=dev.digest(Path(root)/SELF))


def run_directory(header, root=ROOT):
    return Path(root)/'results/milestone6_test_run'/header['variant']


def validate_identity(header, directory, root=ROOT):
    """External reviewed report pins new orchestration, on new run and resume."""
    expected = design(header.get('variant'), root)
    if header != expected or Path(directory).resolve() != run_directory(expected,root).resolve():
        raise RuntimeError('TEST_NAMESPACE_OR_IDENTITY_MISMATCH')
    report = read(Path(root)/PIN)
    if (report.get('status') != 'PASS' or report.get('code_sha256',{}).get(SELF) != LOADED_SHA
            or header['test_runner_sha256'] != LOADED_SHA):
        raise RuntimeError('TEST_RUNNER_PIN_MISSING_OR_CHANGED')


def state(directory, header):
    try:
        s = dev.state(directory,header)
    except (KeyError,TypeError,ValueError,OSError):
        raise RuntimeError('TEST_JOURNAL_OR_CHECKPOINT_INVALID') from None
    if any(t.get('split') != 'test' for t in s['completed'].values()):
        raise RuntimeError('TEST_CHECKPOINT_SPLIT_MISMATCH')
    return s


def initialize(directory, header):
    directory = Path(directory)
    directory.mkdir()  # exclusive; a partially created directory is never resumed silently
    (directory/'checkpoints').mkdir()
    dev.write_new(directory/'identity.json',header)
    dev.append_record(directory/'requests.jsonl',header)


class TestBudget(dev.ExperimentBudget):
    def __init__(self,directory,header,*,verify=dev.verify_key_budget):
        validate_identity(header,directory)
        state(directory,header)  # reject partial cases on process resume
        super().__init__(directory,header,verify=verify)

    def before_request(self):
        validate_identity(self.header,self.directory)
        # Parent state supports the active in-process partial case, but forbids
        # unknown outcomes. Parent fsyncs the reservation before HTTP.
        super().before_request()


def validate_cases(cases, header):
    if (len(cases) != 7 or len({c['id'] for c in cases}) != 7
            or [c['id'] for c in cases] != header['case_ids']
            or any(c.get('split') != 'test' for c in cases)):
        raise RuntimeError('TEST_CASE_IDS_OR_SPLIT_INVALID')


def evaluate(cases, retriever, controller, budget, directory, header):
    """Same Agent and trace contract; injected retrieval/controller for mocks."""
    validate_cases(cases,header)
    validate_identity(header,directory)
    s = state(directory,header)
    for case in cases:
        if case['id'] in s['completed']:
            continue
        budget.case_id = case['id']
        before = budget.calls
        result = dev.run_agent(case['question'],controller,retriever,
            filters=case.get('filter'),top_k=3,max_searches=2,budget=12000,
            count_tokens=dev.ByteBudget())
        row = dict(result,query_id=case['id'],split='test',retrieval_method='lexical',
            llm_requests=budget.calls-before,cumulative_llm_requests=budget.calls,
            automatic=dev.automatic_checks(case,result),manual_review=dev.review_template(case,result))
        if result['status'] == 'error':
            dev.write_new(Path(directory)/'failed_case.json',row)
            dev.append_record(Path(directory)/'requests.jsonl',dict(event='case_error',case_id=case['id']))
            raise RuntimeError('TEST_CASE_ERROR_STOP')
        dev.checkpoint(directory,row)
        s = state(directory,header)
    if set(s['completed']) != set(header['case_ids']):
        raise RuntimeError('TEST_INCOMPLETE_STOP')
    return [s['completed'][cid] for cid in header['case_ids']]


def execute(header, *, approved=False, approved_envelope=None, resume=False):
    """Never reached by import/offline preflight; approval checked before TEST parse."""
    if approved is not True or dev.number(approved_envelope) != ENVELOPE:
        raise RuntimeError('TEST_EXPLICIT_APPROVAL_AND_ENVELOPE_REQUIRED')
    directory = run_directory(header)
    validate_identity(header,directory)
    output = ROOT/'results'/('milestone6_test_'+header['variant'].lower()+'_raw.json')
    if output.exists():
        raise RuntimeError('TEST_OUTPUT_EXISTS')
    if bool(directory.exists()) != resume:
        raise RuntimeError('TEST_RESUME_FLAG_MISMATCH')
    s = state(directory,header) if resume else dict(calls=0,completed={})
    # Only this explicitly approved path deserializes TEST. Gold is used only
    # by post-generation signals/review; never passed to controller/retriever.
    cases = read(ROOT/'data/benchmark/test.json')
    validate_cases(cases,header)
    claim = ROOT/'results/milestone6_test_execution.lock'
    db = None; fingerprint = None
    with claim.open('x') as stream:
        stream.write(header['variant'])
    try:
        if len(s['completed']) == 7:
            traces = [s['completed'][cid] for cid in header['case_ids']]
        else:
            validate_identity(header,directory)
            dev.verify_key_budget((21-s['calls'])*dev.RESERVATION)
            validate_identity(header,directory)
            dev.check_catalog()
            cfg = dev.dense_module.Config(Path(header['day6_root']))
            db = dev.dense_module.DenseRetriever(cfg,dev.dense_module.load_embedder(cfg))
            fingerprint = dev.database_fingerprint(db)
            chunks = dev.load_snapshot(db)
            if not directory.exists():
                directory.parent.mkdir(parents=True,exist_ok=True)
                initialize(directory,header)
            budget = TestBudget(directory,header)
            traces = evaluate(cases,dev.LexicalRetriever(chunks),
                dev.ExperimentController(budget,header['prompt']),budget,directory,header)
        final = state(directory,header)
        validate_identity(header,directory)
        report = dict(status='PENDING_MANUAL_REVIEW',variant=header['variant'],header=header,
            case_results=traces,requests=final['calls'],completed_case_ids=list(final['completed']),
            actual_provider_cost_usd=str(final['actual']),retained_reservations_usd=str(final['reserved']))
        if db is not None and dev.database_fingerprint(db) != fingerprint:
            raise RuntimeError('TEST_DATABASE_FINGERPRINT_CHANGED')
        dev.write_new(output,report)
    finally:
        # DenseRetriever owns short-lived read-only connection contexts; it has
        # no persistent connection/close interface.
        claim.unlink()  # stale locks after process death require review, never automatic recovery


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--variant',choices=['baseline','E1'],required=True)
    parser.add_argument('--mode',choices=['offline-preflight','run'],default='offline-preflight')
    parser.add_argument('--approve-paid-test',action='store_true')
    parser.add_argument('--approved-envelope-usd')
    parser.add_argument('--resume',action='store_true')
    args = parser.parse_args(argv)
    if args.mode == 'run' and (not args.approve_paid_test or args.approved_envelope_usd != str(ENVELOPE)):
        parser.error('Separate paid TEST approval and exact envelope required')
    header = design(args.variant)
    validate_identity(header,run_directory(header))
    if args.mode == 'run':
        execute(header,approved=args.approve_paid_test,approved_envelope=args.approved_envelope_usd,resume=args.resume)
    else:
        print(json.dumps(dict(status='OFFLINE_ONLY_NOT_EXECUTION_APPROVAL',variant=args.variant,
            cases=7,lock_sha256=LOCK_SHA,requests=21,envelope_usd=str(ENVELOPE),new_api_calls=0)))


if __name__ == '__main__':
    main()
