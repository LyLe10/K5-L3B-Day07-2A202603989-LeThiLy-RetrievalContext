# Milestone 3: lexical and hybrid retrieval

Algorithm and adapter details below remain useful; smoke counts/commands describe the earlier integration stage, not final DEV/TEST results. The DEV comparison and selected TF-IDF configuration are in the [final report](../report/individual/2A202603989_LeThiLy.md); execution boundaries are in [REPRODUCIBILITY](REPRODUCIBILITY.md).

All methods implement `search(query, *, filters, top_k)` and return original
source metadata, IDs, physical/printed pages and provenance plus score/rank.
The starter and dense implementation are unchanged. No dependencies added.

- Dense: existing pgvector cosine search and local Day 06 query embeddings.
- Lexical: existing `starter.baseline.TfidfIndex`, NFC/casefold `\w+` tokens,
  raw term counts, smoothed IDF `log((1+N)/(1+df))+1`, L2 normalization and
  cosine dot product. Positive scores only. IDF fits all 264 B texts once;
  section equality is applied after scoring. No Vietnamese word segmentation.
- Hybrid: unweighted RRF `sum(1/(60+rank))`, one contribution per unique ID
  per branch. Retrieve `max(20, top_k)` candidates from each unchanged branch.
  Rank ties break by ID ascending. Preserve each component's rank and score.
  Conflicting provenance or branch failures propagate; no fallback.

`load_snapshot` uses dense's repeatable-read read-only transaction and preflight,
reads only texts/metadata columns for pinned B, verifies 264 unique IDs and
provenance, and creates an in-memory lexical index. It never reads gold or
encodes documents. The index remains fixed for the retriever's lifetime.

```python
from pathlib import Path
from src.dense import Config, DenseRetriever, load_embedder
from src.retrieval import create_retriever
config = Config(Path('/mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion'))
dense = DenseRetriever(config, load_embedder(config))
retriever = create_retriever('hybrid', dense)  # dense | lexical | hybrid
results = retriever.search('What is a foreign key?', filters=None, top_k=3)
```

Supported inputs match dense: nonempty string without NUL, integer top_k 1–264,
and optional section equality. Unknown filter keys fail. TF-IDF can return fewer
than top_k when terms are absent. `last_trace` records results, latency, errors
and service cost; hybrid also records component traces. Scores have different
meanings across methods and do not measure answer quality.

From the repository root in the existing WSL runtime:

```bash
.venv/bin/python -B -m unittest discover -s tests -v
.venv/bin/python -B scripts/dense_smoke.py --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion --output results/milestone3_dense_regression.json
.venv/bin/python -B scripts/retrieval_smoke.py --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion --output results/milestone3_retrieval_smoke.json
```

Smoke uses exactly the three original Milestone 2 technical queries, no query
rewrites, no filters, top-3, and a 2400-character context budget. Repeated queries
check deterministic outputs; an explicit nonexistent section checks empty
results. Full traces include text, source, pages, context and component rankings.
Database fingerprints include all four tables and vectors, before/after.
Day 06 file inventory excludes environments, caches, bytecode and Git internals
as documented for Milestone 2. No LLM API or official benchmark runs.

Latency is diagnostic only: local model/cache warmup and execution order differ.
RRF parameters are defaults selected before smoke, not optimized or frozen as
the final benchmark configuration. Future dev experiments must evaluate all
methods fairly before configuration selection and held-out test evaluation.
