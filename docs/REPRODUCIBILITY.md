# Reproducibility — public code, public metrics, restricted evidence

## What a public clone provides

Public code, selected tests, frozen configuration/dependency identities and final aggregate/per-case metric metadata are available through [the staging manifest](FINAL_PUBLIC_STAGING_MANIFEST.md). Existing tracked starter/specification files remain part of the repository. The public report contains no TEST questions, expected answers, gold quotations or corpus excerpts. Public case IDs, answerable flags and approved numeric metric metadata are not a replacement question set.

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

These test synthetic fixtures/local lexical CLI; they do not reproduce benchmark results. Complete source import closure for the pinned runner is included through existing tracked files plus the explicit manifest. External data/model closure is intentionally restricted.

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
