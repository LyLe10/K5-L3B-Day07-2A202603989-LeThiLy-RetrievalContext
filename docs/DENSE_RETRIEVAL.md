# Milestone 2: PostgreSQL adapter and dense smoke

This milestone implements `Retriever.search(query, *, filters, top_k)` from
`starter/agentic.py`. Starter code is unchanged. No controller, lexical/hybrid
retriever, official benchmark or LLM call is included.

## Runtime and reproduction

Use WSL CPython 3.12.3 and run commands from the Day 07 repository root. The
existing Day 06 checkout must be accessible locally. Do not copy its `.env`.

```bash
DAY6_ROOT=/mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion
.venv/bin/python -B scripts/prepare_dense_runtime.py --day6-root "$DAY6_ROOT"
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B scripts/dense_smoke.py --day6-root "$DAY6_ROOT" \
  --output results/milestone2_dense_smoke.json
```

`prepare_dense_runtime.py` recovers wheels from the existing Stage 4 and user
pip caches. It checks their SHA-256 against Day 06's accepted wheel lock before
copying them into ignored `data/local/wheelhouse/`. It installs the minimal
direct runtime requirements and their dependencies into Day 07 `.venv` using
the hash-locked closure in `requirements-dense.lock` (`--require-hashes`).
If a required wheel is absent, pip fails closed with `--no-index`. On the first
setup in this session, setuptools 84.2.1 needed a separate pip install using the
exact wheel URL already pinned in the Day 06 lock. It is not a model download.
The generated wheel inventory stays local. No model artifacts enter Git.

## Adapter design

`src/dense.py` loads only the DATABASE_URL entry from Day 06 `.env`, without
interpolation, environment updates, credential logging or provider key loading.
It accepts only the approved loopback host, port, database and user, and rejects
URL query options. Connection options enforce read-only mode and timeouts.
Each operation opens one repeatable-read, read-only transaction, checks the
target, validates the pinned B snapshot and profile, then rolls back and closes.
Application data queries access `day6_ingestion` only. PostgreSQL catalog and
existing public pgvector functions/operators are used for transaction checks,
dimension validation and cosine distance; no DDL or DML is issued.

The adapter pins dataset `day06-postgresql`, profile
`528f0792d5fdf66a50c7d42f12de648935d70e2912072e6c6dd2eb6b3f4fd651`, and B snapshot
`c7d9d92e6695709595d044e5a5a09bb8f91826fb692474c7b1806751015ec1e0`.
It requires complete status, 264 rows and 40 pages, expected manifest/corpus
hashes, and a database profile identical to the verified runtime profile.
A/B vectors are never combined for retrieval.

The model adapter subclasses Day 06 `MyEmbedder`, reusing its model artifact
checksums, full pinned revision, library/runtime checks, query prefix, tokenizer
overflow rejection, normalization and vector validation. Only query encoding is
exposed; document encoding is blocked. Existing Day 06 query cache can be read,
but `_write_cache` is disabled. Repeat queries use an in-memory vector cache.
Imports use `-B` / disabled bytecode so Day 06 source is not written.

Ranking uses `embedding <=> query_vector` with score `1 - cosine_distance`,
deterministic chunk-ID tie breaking, parameterized section equality and top-k.
Supported top-k is 1–264; unknown filters fail rather than being ignored.
There is no index creation, corpus encoding or mock fallback.

## Data and context

Mapping is `chunk_id → id`, `document_id → source_id`, and
`physical_page → page`. Original metadata, text, source URL, printed page label,
section, offsets, page ID and all profile/snapshot/hash provenance are retained.
The structured `citation` explicitly distinguishes physical and printed page.

`pack_dense_context` reuses starter `pack_context` selection and character-budget
logic with both page systems labeled. Smoke uses a 2400-character budget and
records selected IDs and full context. The original `run_agent` still uses its
original formatter; a later approved agent milestone must wire this helper into
its context path if both page labels are required in model-facing context.

## Validation and limits

`tests/test_dense.py` covers mapping, metadata, context budgets, inputs, vectors,
binding filters, snapshot/profile mismatch, read-only cleanup and sanitized
database errors/timeouts. Existing 15 baseline tests remain unchanged.

`scripts/dense_smoke.py` explicitly opts into the real model and database. It
never opens benchmark/gold files. Its technical queries are listed in source.
It tests corruption rejection before model loading, snapshot mismatch, a real
server statement timeout, a real SQL error, empty results and query caching.
It compares fingerprints (including stored vectors) of all four Day 06 tables
before/after. This is an integration smoke test, not a retrieval-quality metric.

Filesystem verification uses `scripts/check_day6_files.py` and a before manifest
kept in ignored `data/local/`. It checks source, corpus, snapshots and model files;
runtime environments, caches, bytecode and Git internals are explicitly excluded.

Database errors expose fixed error codes only. A future least-privilege database
role would add defense in depth; this milestone uses the authorized existing
`day6` role and read-only transactions without changing grants or credentials.

The earlier Milestone 1 tool output exposed the local PostgreSQL password literal
from Day 06 Compose in this conversation/tool transcript. No API keys or full
`.env` were printed in that incident. Do not redistribute that output. The user
should rotate that local password and update its configuration through their
normal process; this milestone does not change credentials or remove history.
