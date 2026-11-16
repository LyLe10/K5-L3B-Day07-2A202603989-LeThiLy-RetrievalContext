# Terminal execution of Milestone 4B

Use `scripts/milestone4b_smoke.py`; the older `agent_smoke.py` is a generic
single-question entrypoint and does not enforce this two-case shared budget.
`openrouter_preflight.py` is the historical key-only probe.

In your existing WSL terminal with OPENROUTER_API_KEY exported:

```bash
cd /mnt/d/AI20K/K5-L3B-Day07-2A202603989-LeThiLy-RetrievalContext
.venv/bin/python -B scripts/milestone4b_smoke.py --mode preflight \
  --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion \
  --output results/milestone4b_terminal_preflight.json
```

Only after that reports PASS, execute ONCE:

```bash
.venv/bin/python -B scripts/milestone4b_smoke.py --mode run \
  --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion \
  --output results/milestone4b_terminal_real_smoke.json
```

The run repeats all preflight checks. Existing output files are refused before
network/database activity; preserve them. Do not launch concurrent runs or rerun
under a different filename after spending API calls: six calls is the total
approved allowance, not permission to repeat six calls per invocation.

Preflight mode contains no path to controller.decide or HTTP calls. It checks
key presence without printing it, the pinned local E5 model, the verified B
snapshot (264 chunks, 40 pages, 384 dimensions and provenance), foreign-key
coverage and absence of orchid mentions across the loaded corpus. No benchmark
questions or gold are loaded. Database queries use the existing read-only,
repeatable-read adapter, followed by rollback. Table-content fingerprints
including vectors are compared before/after. No corpus encoding is performed.

The run fixes the requested OpenRouter model to
`qwen/qwen3-next-80b-a3b-instruct:free`, timeout 60 seconds, max_tokens 512,
max_searches 2, dense retrieval top_k 3, two independent smoke questions. No
retrieval tuning, retry or fallback. The adapter sends zero prompt/completion
price caps. Any LLM error stops subsequent requests across both cases, including
401/402/429/timeouts. A nonzero reported cost also stops subsequent calls.

CallBudget is shared across both cases and invoked immediately before each
HTTP open. It refuses request seven. LimitedRetriever independently refuses a
third search in a case. The generic agent also limits max_searches=2. No request
for metadata/generation/model discovery is made. Real response model is retained
if supplied, alongside requested model, usage, cost, decisions and latency.

No exact-model tokenizer download is needed: Qwen uses byte-level BPE, so UTF-8
byte length provides a conservative upper bound for text tokens. Context is
capped at 12,000 UTF-8 bytes; the full serialized user payload is additionally
capped at 24,000 bytes, leaving ample system/framing/output headroom below 262K.
These are explicitly labeled upper bounds, never reported as measured tokens.
Provider usage remains the source of measured API token usage.

The runner saves JSON traces containing only retrieved public chunks, not the
full corpus, and sanitized operational errors. A successful API workflow is
PENDING_MANUAL_REVIEW: inspect each claim against cited text and source/page
metadata before assigning semantic PASS. For Case B distinguish abstention
from technical errors. Do not count citation membership alone as grounding.

Mock regression log: `results/milestone4b_terminal_unit_tests.log`.
No real API was called during preparation in Codex.

Preparation validation (2026-11-16): 65/65 tests PASS, including shared budget
at the HTTP boundary, global stop on 401/402/429/timeout, retrieval cap, payload
size and no-HTTP preflight. The real API-free Codex preflight verified snapshot
B, corpus coverage, read-only transactions and matching database fingerprints.
Its final status is FAIL_KEY_MISSING solely because the tool-launched WSL
process does not inherit the user's terminal key. See
`results/milestone4b_terminal_codex_preflight.json`; the user must rerun preflight
in the current keyed terminal and obtain PASS before running smoke.
