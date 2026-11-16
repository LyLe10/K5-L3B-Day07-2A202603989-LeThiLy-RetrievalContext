# Milestone 4B — Real LLM smoke: FAIL (preflight stopped)

Date: 2026-11-16, Asia/Bangkok. FAIL means real LLM was not verified;
neither case was executed. This is not a model quality result.

## A. Environment and configuration

Read README, GUIDE, RULES, RUBRIC, BENCHMARK, SUBMISSION and both Milestone 4B
documents. Reviewed OpenRouterController, agent contract, smoke CLI, dense
read-only adapter, runtime dependencies and existing fingerprint helper.
RUBRIC permits APIs. User explicitly authorized public PostgreSQL documentation
excerpts to be sent to OpenRouter; no additional permission was requested.

WSL existing virtual environment: Python 3.12.3. The actual Python process
reported `key_present=false` for OPENROUTER_API_KEY. No key value or Authorization
header was printed or saved. Shell-local exports in another terminal are not
inherited by a new tool-launched WSL shell. No credential files were searched.

Fixed model: `qwen/qwen3-next-80b-a3b-instruct:free`. Static adapter checks:
one explicit free model, allow_fallbacks=false, prompt/completion max_price=0,
timeout=60 seconds, max_tokens=512, no retry, redirects refused. Initialization
does not issue requests. Actual response model: unavailable, no response.

Planned limits: 2 cases, 6 total LLM requests, 2 retrieval calls/case.
The missing-key check stopped execution before constructing a live run.
A shared request counter and global stop latch must still be wired and tested
before any future API request; the existing generic adapter alone does not
provide those run-level guarantees. No inference-capable runner was launched.

Tokenizer/safe context-budget verification and live Day 06 snapshot verification
were NOT RUN after this critical preflight failure, as instructed. Snapshot B's
264 chunks are enforced by existing adapter code but were not verified live here.

## B. Calls, usage, latency and cost

| Measurement | Actual |
|---|---|
| LLM API requests | 0 / 6 |
| Retrieval calls | 0 (both cases unstarted) |
| Retries / fallbacks | 0 / 0 |
| Inference tokens / latency | N/A — not measured |
| Provider-reported API cost | N/A — no response |
| Inference cost incurred by this run | 0 — no requests |

Evidence: [preflight JSON](../results/milestone4b_real_llm_preflight.json).
The limits in this JSON are planned configuration, not proof of a running
shared counter. No synthetic model decisions, citations or measured usage exist.

## C. Smoke A — Answerable

NOT RUN. Intended independent topic: PostgreSQL foreign-key requirements.
No benchmark TEST questions or gold answers were loaded. No question was sent,
no evidence selected, and no answer generated.

## D. Smoke B — Unanswerable

NOT RUN. Intended topic outside the ingested PostgreSQL documentation.
There is no abstention result; a preflight error must not be scored as abstention.

## E. Citation validity and semantic grounding

Not evaluated: no model answer, retrieved chunks, context or citations.
No PASS can be inferred from unit tests or adapter structure.

## F. Errors and causes

Blocking code: OPENROUTER_KEY_MISSING_IN_EXECUTION_ENVIRONMENT.
The user's interactive terminal key check and this execution process check
refer to different process environments. The first inline shell probe also
failed due to nested quoting; a file-based Python probe then completed normally
and established the missing environment variable. Neither probe called an API.

To resume, provide the key through a private environment mechanism inherited by
the actual execution process, or run the completed guarded runner from the WSL
terminal that already holds the export. Do not paste the key into chat or commit
it. Existing user authorization remains valid; no new API approval is needed.
Then complete the remaining preflight and run-level guard before inference.

## G. Rubric compliance status

59/59 mock unit tests PASS (0.571 seconds): all 51 original plus 8 OpenRouter
tests. [Log](../results/milestone4b_real_llm_unit_tests.log).
No DEV/TEST benchmark was run, no tuning, gold edits, corpus re-encoding,
database mutations, commit/push, or Milestone 5 work was performed.

No live database connection was made in this attempt. Thus this work issued no
database writes; database content equality before/after is NOT independently
verified and cannot be claimed. A future live run must compare all-table
fingerprints including vectors before/after using read-only transactions.
Benchmark/data hashes were saved without feeding their contents to the agent;
tracked benchmark files show no Git diff. Existing dirty files predate this run.

Real LLM retrieval orchestration, grounded answer and genuine abstention remain
unverified. Full rubric requirements still include dev comparisons, two improvement
configurations, failure analysis, freeze and held-out evaluation in later scope.

## H. Git diff summary

This attempt adds only:

- scripts/openrouter_preflight.py (no inference code; credential-presence check).
- results/milestone4b_real_llm_preflight.json.
- results/milestone4b_real_llm_unit_tests.log.
- docs/MILESTONE4B_REAL_LLM_REPORT.md.

No src, tests, benchmark or Day 06 file was edited in this attempt. Git status
already contains many untracked milestone files and a modified .gitignore;
`git diff --stat` reports only tracked .gitignore (one line), so it does not
represent all existing milestone work. No global Git configuration was changed.

## I. Conclusion

**FAIL — preflight prevented real LLM verification.** Both cases NOT RUN,
0 API requests. Stop for user review; do not continue to Milestone 5.
