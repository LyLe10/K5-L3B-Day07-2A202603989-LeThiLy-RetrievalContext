# Milestone 4B — paid safe resume implementation

Date: 2026-11-16 (Asia/Bangkok). Implementation ready for terminal preflight;
paid inference NOT RUN. Key budget NOT VERIFIED in Codex execution environment.

## Authorization and key verification result

User approved `qwen/qwen3-30b-a3b-instruct-2507` and $0.10 maximum inference
spend. RULES/RUBRIC permit public-data API inference and do not require free
models. Account credits alone do not establish a finite API-key limit.

Executed only the new `--mode key-preflight` in WSL. It validated the real
historical trace chain but could not query GET /api/v1/key because the actual
process environment has no OPENROUTER_API_KEY. It stopped before any HTTP
request, database connection, resume claim or inference. Evidence:
`results/milestone4b_paid_codex_key_preflight.json`: FAIL,
OPENROUTER_KEY_MISSING, inherited requests=2, new requests=0. This is not
evidence that the user's interactive terminal has no key.

The new runner checks the existing key with read-only
[GET /api/v1/key](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key).
Only sanitized numeric limit/usage fields are retained. No label, key hash,
account identifier, credential or Authorization header is printed. Redirects,
HTTP failures and invalid metadata fail closed, without retries. No key limit,
credits or account settings are changed.

Validation requires a finite positive key limit <=$0.10, explicit limit_reset=null,
finite nonnegative usage/remaining values consistent with that cap, and at least
$0.020 remaining at initial preflight. Unlimited, resetting, oversized or
insufficient caps block execution. Before every paid HTTP request the same key
identity is checked in memory, and metadata is refreshed with enough remaining
allowance to cover the outstanding $0.005 reservations. Metadata GETs are logged
separately from the six inference-request allowance. They are not inference.

## Model, cost policy and limits

Paid allowlist is a singleton containing the approved Qwen ID. The generic
OpenRouter adapter uses an exact-ID policy (no arbitrary :free suffix acceptance).
It retains the previously approved exact free ID solely for old compatibility;
the paid runner cannot select it or any other model. Paid requests require a
request guard. Controller.decide(question, history) remains unchanged.

Fixed paid settings: max_tokens=512, timeout=60s, temperature=0, one model,
allow_fallbacks=false, no retries, no native paid tools/plugins, price caps
$0.12 prompt/$0.36 completion per million tokens. Official
[endpoint metadata](https://openrouter.ai/api/v1/models/qwen/qwen3-30b-a3b-instruct-2507/endpoints)
lists input $0.09–0.10 and output $0.30 per million. Caps include a 20% margin
over the higher observed rates, not permission for model fallback.

Agent, retrieval and context selection are unchanged: existing dense top_k=3,
two fixed cases, max_searches=2 and context limit 12,000 UTF-8 bytes. The new
transport guard bounds user JSON at 24,000 bytes and system+user+framing allowance
at 26,000. Byte-level Qwen BPE gives a conservative text-token bound; framing
allowance is an estimate, not measured model tokens. Provider counts are retained.

Estimated upper text-token cost at caps:

`4 * (26,000 * 0.12 + 512 * 0.36) / 1,000,000 = $0.01321728`.

Code reserves $0.005 per attempted paid request (higher than the estimated
$0.00330432/request), fsyncs that reservation BEFORE HTTP, never refunds uncertain
responses, and enforces total reservations <=$0.10. With four remaining requests
the additional reservations cannot exceed $0.020. Missing cost/tokens, usage
beyond the reservation/token bound, unexpected response model or any LLM error
stops all further inference calls. Cost reports distinguish known-response sums
from an unknown total after unverified responses.

Application guarantees concern request count and durable reservations. Actual
charges depend on OpenRouter/provider honoring price caps, token limits and the
verified key cap. The runner cannot independently guarantee their billing system
or control another program using the same key. Use a dedicated non-resetting
capped key, no concurrent runs or unrelated usage. A reservation/estimate is
not an unconditional financial guarantee; paid execution stays blocked if
account verification fails. Credit purchases/fees are outside inference estimates.

## Resume and evidence

The paid runner accepts only the observed pre-retrieval 401 -> 404 chain:
original trace=1 request, resume1 inherited=1/new=1/cumulative=2. It validates
the original SHA-256, original resume claim and the existing journal's
inherited_calls=1/reserved_total=2. Previous retrieval must be zero. It does not
replay partially completed retrieval or support generic paid-run recovery.

The new exclusive claim is attached to resume1, leaving the original claim,
all traces and old journal intact. Counter starts at 2 and refuses request 7
at the actual HTTP boundary. Each case independently refuses a third retrieval.
New output and journal paths must not exist. Duplicate claim prevents another
output/process consuming the same allowance. After failure/interruption do not
delete claims/journals or rerun under another filename; review evidence first.

## Exact terminal commands

Run in the existing WSL terminal whose environment contains the key:

```bash
cd /mnt/d/AI20K/K5-L3B-Day07-2A202603989-LeThiLy-RetrievalContext
.venv/bin/python -B scripts/milestone4b_paid_smoke.py \
  --mode preflight \
  --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion \
  --resume-from results/milestone4b_terminal_real_smoke_resume1.json \
  --output results/milestone4b_paid_terminal_preflight.json
```

This performs metadata GET plus existing offline model/read-only database
preflight, never inference POST. It creates no resume claim. It must report PASS.
If the key is unlimited, resetting, >$0.10 or has <$0.020 remaining, stop and
review existing account configuration manually; no automatic adjustment occurs.

Only AFTER preflight PASS and the user's subsequent execution approval, run ONCE:

```bash
.venv/bin/python -B scripts/milestone4b_paid_smoke.py \
  --mode run --approve-paid-inference \
  --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion \
  --resume-from results/milestone4b_terminal_real_smoke_resume1.json \
  --output results/milestone4b_paid_terminal_real_smoke.json
```

Run repeats key/DB preflight and checks metadata again before every inference.
Success remains PENDING_MANUAL_REVIEW until each claim/citation is checked for
semantic support. Do not use the legacy free runner for paid execution.

## Validation and changed files

82/82 unit tests PASS (68 previous + 14 new), 0.901s in existing WSL .venv.
All HTTP mocked. Tests cover safe/unsafe key limits, metadata GET sanitization,
missing key/HTTP error/no retry, paid model/caps/mandatory guard, four remaining
requests, reservation persistence before timeout, failed journal write blocking
HTTP, missing/excessive usage, key/model changes, real-shaped resume chain/journal
validation, metadata-only preflight, failed-key execution blocking and a full
two-case paid resume through mocked HTTP (answered + abstain, cumulative 6).
Mock answers are synthetic fixtures and are not real-model validation.

Log: results/milestone4b_paid_implementation_unit_tests.log.
Changed: src/llm.py; added src/openrouter_paid.py,
scripts/milestone4b_paid_smoke.py, tests/test_paid_smoke.py, this report, key
preflight JSON and unit log. Existing scripts/Agent/Retrieval/Context, benchmark,
Day 06, dependencies, traces and journals were not modified. No database query
was made in this preparation attempt, no DEV/TEST, inference, credit purchase,
key update, commit or push. Stop for user review and execution approval.
