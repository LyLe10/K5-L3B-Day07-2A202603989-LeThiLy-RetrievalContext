# Milestone 4B — paid model review: STOPPED BEFORE ENABLEMENT

Date: 2026-11-16 (Asia/Bangkok). No inference API calls in this review.

## Repository permission and historical calls

Read RULES.md, RUBRIC.md, README.md and AGENTS.md. RUBRIC allows local models
or APIs and says payment is not required; it does not prohibit paid models.
RULES requires authorized public data and protection of credentials. User has
authorized paid-model consideration and public PostgreSQL excerpts, but requests
model/budget review before running and mandates stopping if the USD cap cannot
be assured in code AND account controls.

Original trace has one 401. Resume1 has one additional 404, inherited=1,
cumulative llm_calls=2. Its requests journal contains inherited_calls=1 and
reserved_total=2. Case A retrieval=0 and B not run in both attempts. Therefore
remaining allowance is FOUR, never six. Existing traces, journal and claim
are preserved. No inference was used to diagnose errors.

## HTTP 404 diagnosis

Official public [endpoint metadata](https://openrouter.ai/api/v1/models/qwen/qwen3-next-80b-a3b-instruct:free/endpoints)
currently returns the free model ID with `endpoints: []`. This supports no
available serving endpoint as the likely cause. The historical trace stores
404 but not provider response body: historical cause cannot be proved exactly,
and account privacy filters/parameter support cannot be excluded from that
historical event. A cached marketing page is not proof of live endpoint supply.

## Candidates, USD per million text tokens

These are advertised prices observed in official metadata/pages during review,
not a guarantee that any provider remains available at that price.

| Exact model ID | Input | Output | Suitability |
|---|---:|---:|---|
| qwen/qwen3-30b-a3b-instruct-2507 | 0.09 | 0.30 | Non-thinking, instruction following, multilingual and agentic tool use; 262K context |
| google/gemini-2.5-flash-lite | 0.10 | 0.40 | Low latency; thinking disabled by default; candidate for simple JSON decisions and grounded answers |
| openai/gpt-4.1-nano | 0.10 | 0.40 | Low latency instruction model; candidate for simple decisions; grounded answer quality must be checked |

Sources: [Qwen endpoint prices and supported parameters](https://openrouter.ai/api/v1/models/qwen/qwen3-30b-a3b-instruct-2507/endpoints),
[Gemini model page](https://openrouter.ai/google/gemini-2.5-flash-lite),
[GPT model page](https://openrouter.ai/openai/gpt-4.1-nano).
The [general model catalog](https://openrouter.ai/api/v1/models) lists Qwen at
0.10/0.30 whereas its endpoint metadata/page lists 0.09/0.30. Endpoint metadata
shows DekaLLM and SiliconFlow at 0.09/0.30, Nebius at 0.10/0.30. Use proposed
caps 0.10 input / 0.30 output to cover this observed variation without fallback.
Current metadata supports max_tokens and temperature. No candidate was tested
on this lab; semantic correctness is not guaranteed by these descriptions.

Propose ONLY `qwen/qwen3-30b-a3b-instruct-2507` for approval. It preserves the
Qwen tokenizer family/context assumptions and offers non-thinking agentic
behavior at lower output cost. Alternatives are not an execution allowlist.

## Estimated costs for the two cases

Assumption for planning: four calls total, combined 10,000 input and 2,000
output tokens. This assumes search then final answer/abstention in each case;
an extra search in A can leave insufficient allowance for B. No retries.

| Candidate | Estimated text inference cost |
|---|---:|
| Qwen at 0.09/0.30 | $0.00150 |
| Qwen at proposed 0.10/0.30 caps | $0.00160 |
| Gemini Flash Lite | $0.00180 |
| GPT-4.1 nano | $0.00180 |

Conservative proposed reservation: 26,000 input tokens per call (24,000-byte
user payload plus system/framing headroom), 512 output tokens/call, four calls.
At Qwen caps this is 4 * (26,000*0.10 + 512*0.30)/1e6 = $0.0110144.
At the other two candidates' rates it is $0.0112192. These are planning bounds,
NOT enforced accounting today; they exclude credit-purchase fees and optional
plugins/tools, which must not be enabled. API cost is separate from buying credits.

## Stop condition: account-side cap unverified

No sanitized evidence establishes that the actual executing key has a finite
non-resetting $0.10 cap, remaining credits or dedicated usage. HTTP 200
authentication proves none of those. The existing code only supports zero-price
free requests and does not reserve USD. Therefore we CANNOT claim the requested
joint code/account guarantee. Per the user's explicit stop condition, paid
enablement is paused here: no paid allowlist, controller policy, price caps,
USD reservations or paid resume changes were applied. No paid tests can be
claimed. The current runner must not be used for the proposed paid model.

Official [key metadata API](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key)
provides GET /api/v1/key (no inference), including limit, limit_reset,
limit_remaining and usage. [Limit documentation](https://openrouter.ai/docs/api/reference/limits)
distinguishes optional per-key caps from account balance. A positive balance
or max_tokens alone is not a USD ceiling. Provider enforcement cannot be
independently guaranteed by this application.

Before enablement: user approves fixed Qwen ID and $0.10; user configures a
dedicated key with finite total cap <=$0.10, no periodic reset, no concurrent
other use, and verifies remaining allowance via sanitized metadata. No credits
are purchased and no account setting is changed by this review. Then implement
fail-closed metadata validation, explicit model allowlist, capped pricing,
fsynced worst-case USD reservations (never refund uncertain outcomes), and
stop on missing/inconsistent usage. Resume must validate original -> resume1
chain/journal and start cumulative requests at 2. It must retain old claims,
accept the explicit model migration/404 restart, and never replay retrieval.
These implementation steps remain outstanding, not completed work.

## Next terminal command — metadata only, no inference

Run in the terminal holding the environment key. This prints only budget fields,
never the key, Authorization header or raw response/error. It does not modify
the account. Do not share the full raw key metadata response (it can include a
key label or account identifiers).

```bash
.venv/bin/python -B - <<'PY'
import json, os
from urllib.request import Request, build_opener, HTTPRedirectHandler
class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None
try:
    key = os.environ.get('OPENROUTER_API_KEY', '').strip()
    if not key:
        raise RuntimeError()
    req = Request('https://openrouter.ai/api/v1/key', headers={'Authorization':'Bearer '+key})
    with build_opener(NoRedirect()).open(req, timeout=30) as response:
        data = json.load(response)['data']
    print(json.dumps({k:data.get(k) for k in ('limit','limit_reset','limit_remaining','usage')}))
except Exception:
    print('KEY_BUDGET_CHECK_FAILED')
PY
```

No paid inference command is supplied because the runner does not yet implement
the required controls and the model/budget approval is pending.

## Tests and changes

Full existing suite: 68/68 PASS (2.324s), all HTTP mocked. New log:
results/milestone4b_paid_review_unit_tests.log. No implementation/test changes;
only this review document and new regression log were added. Old evidence
unchanged. No Agent, Retrieval, Context, benchmark, Day 06 or dependency changes.
No DEV/TEST, inference, credit purchase, commit/push. Stop for user review.
