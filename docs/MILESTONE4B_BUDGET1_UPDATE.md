# Milestone 4B — approved $1.00 internal budget update

2026-11-16. This policy supersedes the historical $0.10 key-cap requirement;
older reports/traces are retained as historical evidence.

Minimal implementation changes: USD_LIMIT is now 1.00 and reservation is
0.05 per request. Removed only the comparison requiring the API key's cap to
be <= the milestone budget. A key cap of 9 (or any finite positive amount) is
permitted independently of the internal budget. Explicit null/non-resetting
policy, numeric consistency, finite cap and adequate remaining credit remain
required. Initial remaining requirement is now 4*0.05=$0.20. Key cap=null still
fails. Account balance is separate and is not inferred from key-cap metadata.

Request accounting/resume remains unchanged: validates the original 401 and
resume1 404 evidence, starts at 2 calls, permits four new calls, reserves and
fsyncs before HTTP, never refunds uncertainty and never overwrites old claims,
journals or traces. Internal USD ceiling is $1.00; with four remaining requests
total additional reservations cannot exceed $0.20. Price caps remain $0.12
input/$0.36 output per million tokens, estimated four-call maximum text-token
cost $0.01321728, timeout 60s and max_tokens 512. No retry/fallback or changes
to Agent, retrieval, context selection, model, questions or benchmark.

89/89 unit tests PASS (0.898s). Updated mocks verify cap>internal-budget is
accepted, remaining >=$0.20, $0.05/request and $0.20 cumulative reservations,
internal $1.00 cap enforcement, unchanged request limit and reset/consistency
rules. Log: results/milestone4b_budget1_unit_tests.log.

Attempted key-preflight in Codex WSL: FAIL / OPENROUTER_KEY_MISSING before
HTTP. Evidence: results/milestone4b_budget1_codex_key_preflight.json.
Paid preflight therefore not run in this environment. No actual inference or
metadata HTTP requests were made; no DB queries, claim or new reservation.
The user's existing terminal may hold a key despite this separate process
environment. No credentials were searched, logged or changed.

In the user's terminal with the exported key, run metadata-only key preflight:

```bash
cd /mnt/d/AI20K/K5-L3B-Day07-2A202603989-LeThiLy-RetrievalContext
.venv/bin/python -B scripts/milestone4b_paid_smoke.py \
  --mode key-preflight \
  --resume-from results/milestone4b_terminal_real_smoke_resume1.json \
  --output results/milestone4b_budget1_terminal_key_preflight.json
```

After PASS, run full paid preflight (metadata GET + read-only Day 06 checks;
no inference):

```bash
.venv/bin/python -B scripts/milestone4b_paid_smoke.py \
  --mode preflight \
  --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion \
  --resume-from results/milestone4b_terminal_real_smoke_resume1.json \
  --output results/milestone4b_budget1_terminal_preflight.json
```

ONLY after full preflight PASS, user runs paid resume ONCE:

```bash
.venv/bin/python -B scripts/milestone4b_paid_smoke.py \
  --mode run --approve-paid-inference \
  --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion \
  --resume-from results/milestone4b_terminal_real_smoke_resume1.json \
  --output results/milestone4b_budget1_terminal_real_smoke.json
```

Do not delete existing output, claims or journals to bypass an error. The runner
repeats preflight and rechecks key metadata before each paid inference. Semantic
grounding still requires review; HTTP 200 alone is not PASS.

Changed code: src/openrouter_paid.py, scripts/milestone4b_paid_smoke.py.
Updated tests: tests/test_paid_smoke.py, tests/test_key_budget_diagnostics.py.
Added this note and new preflight/test outputs. No account/key limit changes,
credits purchase, inference, DEV/TEST, Day 06 edits, commit or push. Stop for
the user to run the terminal commands.
