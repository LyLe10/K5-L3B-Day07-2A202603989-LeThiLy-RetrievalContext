# Reproducibility — public code, public metrics, restricted evidence

## What a public clone provides

Public code, selected tests, frozen configuration/dependency identities and final aggregate/per-case metric metadata were committed at `bdce3bd7f2ecaddbbc13314a46b952e46f659fa0`; the user confirms publication. See [the documentation index](README.md), [public audit](PUBLIC_SUBMISSION_AUDIT.md) and [final individual report](../report/individual/2A202603989_LeThiLy.md). Existing tracked starter/specification files remain part of the repository. The public report contains no TEST questions, expected answers, gold quotations or corpus excerpts. Public case IDs, answerable flags and approved numeric metric metadata are not a replacement question set.

The public clone is deliberately **not a self-contained benchmark execution package**. Full retrieval/Agent reproduction and semantic regrading require [restricted evidence access](EVIDENCE_ACCESS.md). A missing private file must fail validation; do not create empty datasets, rewrite hashes, replace gold or disable identity checks to make commands pass.

## Pinned data/runtime dependency

Day06 is read-only. Snapshot B: 264 chunks, 40 physical pages 97–132 and 148–151; dataset `day06-postgresql`; snapshot `c7d9d92e6695709595d044e5a5a09bb8f91826fb692474c7b1806751015ec1e0`; profile `528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651`.

Embedding: `intfloat/multilingual-e5-small`, revision `fd1525a9fd15316a2d503bf26ab031a61d056e98`, 384 dimensions, compatible Day06 CPU/normalization/query-prefix implementation. Corpus bytes and model artifacts are not included publicly. Source URL/provenance and permitted acquisition instructions must be provided through the approved Day06 access process, not assumed from a local path.

Lab requirement: Python 3.11+. Documented execution environment: WSL CPython 3.12.3, Linux CPU dependencies in [requirements-dense.txt](../requirements-dense.txt) and hash-locked [requirements-dense.lock](../requirements-dense.lock). Exact historical installed environment and future stochastic LLM outputs are not attested. Setup depends on the approved Day06 wheel/model artifacts; no unverified package/model downloads are implied.

Existing runtime preparation command, **not executed by this documentation task**:

```bash
DAY6_ROOT=/mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion
.venv/bin/python -B scripts/prepare_dense_runtime.py --day6-root "$DAY6_ROOT"
```

This helper requires existing Day06 files/cached wheels and checks hashes. A fresh machine without those resources cannot bootstrap solely from the public clone. Approved private instructions must supply them. Keep secrets in the authorized local execution environment; never send .env or database credentials through GitHub.

## PostgreSQL/pgvector setup boundary

The adapter expects an already provisioned Day06 PostgreSQL/pgvector store and `day6_ingestion` schema. It validates the target, profile/snapshot and dimensions, opens read-only repeatable-read transactions, and rolls back/closes. Day07 does not provide a new migration, vector import or corpus encoder. A grader must receive authorized Day06 setup/access instructions, credentials through a separate secure channel, and a verified snapshot. Existing pins may require the original documented filesystem layout. Do not silently edit lock/source pins to relocate dependencies.

No database creation command is invented here. Day06 provisioning/import is outside this public package and remains PENDING until an approved access/recreation channel is established.

## Offline checks available publicly

With Python available, the starter-only synthetic tests do not require restricted datasets or an API key:

```bash
python3 -B -m unittest tests.test_agentic tests.test_agent_metrics tests.test_baseline
```

These test synthetic fixtures/local lexical CLI; they do not reproduce benchmark results. The public commit includes local application source imports for the pinned runner. External data/model closure is intentionally restricted. On Windows, use a UTF-8 Python environment (`PYTHONUTF8=1`) for these fixtures; documented execution uses WSL.

The historical full offline suite passed 193/193 in the authorized local environment. Do not promise 193/193 in an unprovisioned public clone: dependency-identity and dataset tests need private Day06/runtime/benchmark artifacts. Once private dependencies are provided, the existing full command is:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
```

Public metrics support checking counts, denominators, deltas and cost arithmetic. Re-running `score_reviewed(cases, traces, reviews)` requires restricted raw traces/reviews. The public scoring metadata alone is insufficient; aggregate metrics are published claims backed by restricted audit evidence, not independently reproducible semantic labels from public inputs.

`scripts/validate_benchmark_dataset.py` and default `scripts/frozen_test_evaluation.py --variant baseline|E1` are not executable-ready on a public-only clone: they require frozen private dataset bytes and, for some checks, Day06 dependencies. Do not run paid `--mode run` to test a clone or repeat completed runs. No execution authorization comes from this guide.

## Reproduction after private access

1. Approve a read-only channel under [EVIDENCE_ACCESS.md](EVIDENCE_ACCESS.md); obtain frozen datasets, accepted reviews, original traces and approved Day06 artifacts without altering originals.
2. Check exact file hashes, E1 lock/dependency pins, snapshot, seven-case coverage and journal accounting offline. No TEST-driven tuning or reselection.
3. Reaggregate existing labels using unchanged `scripts.dev_agent_evaluation.score_reviewed()` and compare with public metrics. This needs no inference; keep original outputs immutable.
4. Only with new explicit authorization consider database/retrieval or provider execution. Public reproduction documentation does not authorize spend, reruns or account changes.

Full submission remains incomplete until the grader accepts the evidence/access route. Public code and aggregates do not substitute for SUBMISSION.md:20–23 evidence.

## Agent and context architecture

The runtime reuses `Controller.decide(question, history)` and `Retriever.search(query, *, filters, top_k)`. A decision selects search or a final answer. Search results accumulate as candidates; after each search the context builder repacks whole chunks in retrieval order, deduplicates IDs, rejects conflicting provenance, skips chunks that do not fit and tries later candidates. No LLM compression or reranker is implied. Earlier-search priority can prevent later evidence from fitting; this remains a limitation.

Model-facing context retains chunk ID, text, source ID/source, physical page and printed-page label. Retrieval logs retain scores/ranks; scores are not answer confidence. Citation maps refer only to selected chunks. Final citation IDs must be unique, belong to context and agree with inline citation IDs. Those deterministic checks do not prove semantic support: approved manual reviews evaluate the full answer and each citation separately.

An explicit empty-citation answer and system guards can produce abstention. Repeated-search, empty-context, citation and search-limit termination are distinguished in traces; provider, malformed-output, timeout, database and context-construction failures remain operational errors. Do not count them as successful abstentions. Trace events retain decisions, tools, queries, retrieved/context IDs, citations, sanitized errors, latency and provider usage/cost.

## OpenRouter and locked evaluation configuration

The adapter normalizes JSON search/answer actions into the existing controller contract; it does not require native function calling. `OPENROUTER_API_KEY` is read from the executing process environment, never hardcoded or logged. Initialization/import does not perform inference; redirects, automatic retries and model fallback are disabled. HTTP/provider failures use sanitized codes; raw headers/bodies must not enter logs.

Final Baseline/E1 use `qwen/qwen3-30b-a3b-instruct-2507`, temperature 0, max output 512, timeout 60 seconds, TF-IDF top_k=3, max_searches=2 and context budget 12000 UTF-8 bytes. E1 changes only the SYSTEM prompt; E2 was a separate DEV-only max_searches=1 experiment. The [immutable E1 lock](../results/milestone5d_e1_final_configuration_lock.json), not historical smoke defaults/free-model policies, is authoritative. Its SHA256 remains `87febe40ba9ba2c2e3204333e75b1578e830bb10469b29e3d4116be353e5579e`.

The generic context packer accepts a supplied counter; final byte-budget configuration is not measured model tokens. Full-message byte/token estimates are planning safeguards, not an independently proven provider billing bound. Provider-reported token usage and actual cost are recorded separately.

## Request accounting, errors and resume

The [frozen TEST runner](../scripts/frozen_test_evaluation.py) keeps variants separate: at most 7 cases, 21 LLM requests per variant, 3 requests/case and 2 retrievals/case. Planned reservation envelopes were 0.084 USD per variant, 0.168 USD combined, at 0.004 USD per attempted request. These are internal request/reservation controls, not an unconditional financial guarantee; hard monetary assurance remains UNVERIFIED. They are not the obsolete Milestone4B smoke policy.

Identity/source pins are checked before provider activity. A durable reservation is written before the HTTP request; failed or uncertain attempts are not silently erased or refunded. Outcomes and case-completion checkpoints preserve accounting across resume. Resume skips completed cases and fails closed on inconsistent identities, incomplete/ambiguous cases, corrupt journals, duplicates or exhausted limits. Never delete or rename journals/checkpoints/claims to bypass a stop. Unknown cost/provider errors require audit before further execution; do not replay an uncertain request automatically.

Baseline/E1 TEST is already completed, not a pending smoke run. Retained TEST reservations were 0.068/0.064 USD; actual provider costs were 0.00193353/0.00199362 USD. See [the final report](../report/individual/2A202603989_LeThiLy.md) and [paired metrics](../results/milestone6_test_paired_comparison.json). This documentation grants no new execution/spending authorization, and no reservation is released by cleanup.
