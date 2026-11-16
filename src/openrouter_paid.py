"""Fail-closed paid-smoke policy. Metadata GET only; no inference here."""
from decimal import Decimal
import hashlib
import json
import os
from urllib.request import Request, build_opener

from src.llm import PAID_MODEL, _NoRedirect

PAID_ALLOWLIST = frozenset({PAID_MODEL})
USD_LIMIT = Decimal('1.00')
PER_REQUEST_RESERVATION = Decimal('0.05')
MAX_INPUT_TOKENS_BOUND = 26000
MAX_OUTPUT_TOKENS = 512
MAX_FOUR_CALL_COST = (Decimal('26000')*Decimal('0.12') +
                      Decimal('512')*Decimal('0.36'))*4/Decimal('1000000')


def amount(value):
    if type(value) not in (int, float):
        raise RuntimeError('INVALID_KEY_BUDGET_METADATA')
    result = Decimal(str(value))
    if not result.is_finite() or result < 0:
        raise RuntimeError('INVALID_KEY_BUDGET_METADATA')
    return result


class KeyBudgetError(RuntimeError):
    """Fixed error code plus categorical diagnostics, never raw metadata."""
    def __init__(self, code, diagnostics):
        super().__init__(code)
        self.diagnostics = diagnostics


def _budget_field(data, field):
    prefix = {'limit':'KEY_LIMIT','limit_remaining':'KEY_REMAINING','usage':'KEY_USAGE'}[field]
    if field not in data:
        raise KeyBudgetError(prefix+'_METADATA_MISSING', dict(field=field,state='missing'))
    if data[field] is None:
        code = 'KEY_LIMIT_UNCAPPED' if field=='limit' else prefix+'_UNVERIFIABLE'
        raise KeyBudgetError(code, dict(field=field,state='json_null'))
    try:
        return amount(data[field])
    except RuntimeError:
        raise KeyBudgetError(prefix+'_METADATA_INVALID', dict(field=field,state='invalid_number')) from None


def validate_key_metadata(data, required=PER_REQUEST_RESERVATION*4):
    """Require a finite non-resetting key cap, separate from the smoke USD cap."""
    if not isinstance(data,dict):
        raise KeyBudgetError('KEY_METADATA_RESPONSE_INVALID',dict(response_shape='data_not_object'))
    limit = _budget_field(data,'limit')
    remaining = _budget_field(data,'limit_remaining')
    usage = _budget_field(data,'usage')
    # Key cap may exceed the milestone's internal USD cap. Keep all remaining
    # metadata consistency checks and collect overlapping failures.
    checks = [
        ('KEY_RESET_METADATA_MISSING', 'limit_reset' not in data),
        ('KEY_RESET_POLICY_NOT_ALLOWED', 'limit_reset' in data and data['limit_reset'] is not None),
        ('KEY_LIMIT_ZERO', limit==0),
        ('KEY_REMAINING_EXCEEDS_LIMIT', remaining>limit),
        ('KEY_USAGE_EXCEEDS_LIMIT', usage>limit),
        ('KEY_BUDGET_TOTAL_INCONSISTENT', remaining+usage>limit+Decimal('0.000001')),
    ]
    failures = [code for code,failed in checks if failed]
    reset = data.get('limit_reset')
    reset_state = ('missing' if 'limit_reset' not in data else 'json_null' if reset is None
                   else 'string_null' if type(reset) is str and reset=='null' else 'non_null')
    diagnostics = dict(failed_checks=failures,reset_state=reset_state)
    if failures:
        raise KeyBudgetError(failures[0],diagnostics)
    if remaining < required:
        raise KeyBudgetError('KEY_REMAINING_BUDGET_INSUFFICIENT',
            dict(failed_checks=['KEY_REMAINING_BUDGET_INSUFFICIENT'],reset_state=reset_state))
    return dict(limit=float(limit),limit_remaining=float(remaining),usage=float(usage),
                limit_reset=None,status='PASS')


def verify_key_budget(required=PER_REQUEST_RESERVATION*4):
    key = os.environ.get('OPENROUTER_API_KEY','').strip()
    if not key:
        raise RuntimeError('OPENROUTER_KEY_MISSING')
    try:
        request = Request('https://openrouter.ai/api/v1/key',
                          headers={'Authorization':'Bearer '+key})
        with build_opener(_NoRedirect()).open(request,timeout=30) as response:
            result = json.load(response)
    except (ValueError,TypeError):
        raise KeyBudgetError('KEY_METADATA_RESPONSE_INVALID',dict(response_shape='invalid_json')) from None
    except Exception:
        raise RuntimeError('KEY_METADATA_REQUEST_FAILED') from None
    if not isinstance(result,dict) or 'data' not in result:
        raise KeyBudgetError('KEY_METADATA_RESPONSE_INVALID',dict(response_shape='missing_data_object'))
    # Only sanitized numeric budget fields are retained, never label/hash/IDs.
    return validate_key_metadata(result['data'], required)


class PaidBudget:
    """One process, one exclusive resume claim, durable reservations, no refunds."""
    def __init__(self, journal, *, used=2, verify=verify_key_budget):
        if type(used) is not int or used != 2:
            raise ValueError('PAID_RESUME_REQUIRES_TWO_PRIOR_CALLS')
        self.calls, self.journal, self.verify = used, journal, verify
        self.stopped = False
        self.reserved_usd = Decimal('0')
        self.actual_usd = Decimal('0')
        self.settled_calls = 0
        self.metadata_checks = 0
        self.last_key_budget = None
        self.key_identity = hashlib.sha256(os.environ.get('OPENROUTER_API_KEY','').encode()).digest()

    def before_request(self):
        if self.stopped or self.calls >= 6:
            raise RuntimeError('SMOKE_API_BUDGET_STOP')
        if self.journal is None or self.reserved_usd + PER_REQUEST_RESERVATION > USD_LIMIT:
            raise RuntimeError('PAID_USD_BUDGET_STOP')
        if hashlib.sha256(os.environ.get('OPENROUTER_API_KEY','').encode()).digest() != self.key_identity:
            raise RuntimeError('PAID_KEY_CHANGED')
        self.metadata_checks += 1
        self.last_key_budget = self.verify(PER_REQUEST_RESERVATION*(6-self.calls))
        # Write-ahead reservation counts uncertainty as spent. Never release it.
        reserved = self.reserved_usd + PER_REQUEST_RESERVATION
        with self.journal.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(reserved_total=self.calls+1,
                reserved_usd_total=str(reserved),request_usd=str(PER_REQUEST_RESERVATION)))+'\n')
            stream.flush()
            os.fsync(stream.fileno())
        self.calls += 1
        self.reserved_usd = reserved

    def record_usage(self, trace):
        usage = trace.get('usage',{})
        try:
            cost = amount(usage.get('cost'))
            prompt = amount(usage.get('prompt_tokens'))
            completion = amount(usage.get('completion_tokens'))
            if (cost > PER_REQUEST_RESERVATION or prompt > MAX_INPUT_TOKENS_BOUND
                    or completion > MAX_OUTPUT_TOKENS
                    or trace.get('actual_model',PAID_MODEL) != PAID_MODEL):
                raise RuntimeError('PAID_USAGE_OUTSIDE_RESERVATION')
        except Exception:
            self.stopped = True
            raise RuntimeError('PAID_USAGE_UNVERIFIED_OR_EXCESSIVE') from None
        self.actual_usd += cost
        self.settled_calls += 1
        with self.journal.open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(dict(settled_total=self.calls,cost_usd=str(cost)))+'\n')
            stream.flush()
            os.fsync(stream.fileno())


def validate_paid_resume(path):
    """Validate the observed 401 -> 404 chain, journal and parent hash.

    No generic replay of partial retrieval or paid runs is authorized.
    """
    from scripts.milestone4b_smoke import read_resume, MODEL as FREE_MODEL
    raw = path.read_bytes()
    prior = json.loads(raw)
    parent_path = path.parent / _basename(prior.get('resume_from',''))
    # Resolve recorded basename in the trace directory, portable Windows/WSL.
    original_used, original_hash = read_resume(parent_path)
    journal = [json.loads(line) for line in
               path.with_name(path.name+'.requests.jsonl').read_text().splitlines()]
    claim = json.loads(parent_path.with_name(parent_path.name+'.resume-claim.json').read_text())
    cases = prior.get('cases',[])
    if (original_used != 1 or prior.get('resume_parent_sha256') != original_hash
            or prior.get('kind') != 'milestone4b_smoke_not_benchmark'
            or prior.get('mode') != 'run' or prior.get('provider') != 'openrouter'
            or prior.get('requested_model') != FREE_MODEL or prior.get('status') != 'FAIL'
            or type(prior.get('llm_calls')) is not int or prior['llm_calls'] != 2
            or prior.get('inherited_llm_calls') != 1 or prior.get('llm_calls_this_run') != 1
            or sum(c.get('llm_calls',0) for c in cases) != 1
            or any(c.get('retrieval_calls',0) != 0 for c in cases)
            or any(c.get('status') not in ('error','NOT_RUN_GLOBAL_STOP') for c in cases)
            or not any(e.get('llm',{}).get('http_status') == 404 for c in cases for e in c.get('events',[]))
            or journal != [dict(inherited_calls=1),dict(reserved_total=2)]
            or claim.get('inherited_calls') != 1 or _basename(claim.get('output','')) != path.name):
        raise RuntimeError('PAID_RESUME_CHAIN_INVALID')
    return hashlib.sha256(raw).hexdigest()


def _basename(value):
    # Stored WSL and Windows path strings are data, never shell commands.
    if not isinstance(value,str) or not value:
        raise RuntimeError('PAID_RESUME_PATH_INVALID')
    return value.replace('\\','/').rsplit('/',1)[-1]
