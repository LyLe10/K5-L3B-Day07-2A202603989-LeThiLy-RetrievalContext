# Safe resume after authentication fix

2026-11-16. No real API or live database calls made during this change.

Reviewed original `results/milestone4b_terminal_real_smoke.json`: FAIL,
1 request, HTTP 401, Case A retrieval_calls=0, Case B NOT_RUN_GLOBAL_STOP.
`milestone4b_terminal_preflight_v2.json` records PASS with unchanged database.
The user's authentication HTTP 200 is not a smoke inference result and no
authentication response artifact was found among these traces. The approved
smoke allowance remains 6 total, including the failed inference request.

Previously CallBudget reset to zero every invocation. `--resume-from` now reads
and validates the failed authentication trace, including model, provider, request
count and zero prior retrieval. It accepts only this narrow restart-before-
retrieval workflow. It refuses other partial workflows rather than replaying
already completed retrieval/cases. Agent, model, retrieval, benchmark unchanged.

For this source, the shared counter starts at 1, permitting at most 5 new HTTP
requests. It is checked at the existing HTTP boundary before every request.
Both cases share the same counter; each retains its independent 2-search cap.
Failures stop all subsequent requests within the resumed process. There is no
automatic retry or fallback; this is the user's explicit post-fix restart.

The original trace remains byte-for-byte unchanged. New trace fields include
inherited_llm_calls, llm_calls_this_run, cumulative llm_calls, remaining_llm_calls,
resume_from and resume_parent_sha256. Before inference an exclusive sidecar
`<parent>.resume-claim.json` consumes the source's one resume opportunity and
prevents another process/output reusing it. A new
`<output>.requests.jsonl` records and fsyncs each cumulative reservation BEFORE
HTTP, so 401, timeout or interruption cannot silently disappear from evidence.
Uncertain reservations remain spent conservatively. Do not delete claim/journal
files after failure or interruption. Crash recovery requires evidence review;
the runner deliberately refuses automatic recovery/replay.

A fresh run without --resume-from is also refused if results contain a spent
Milestone 4B run. Do not move/edit/delete evidence to bypass these checks.
Preflight mode remains API-free and does not claim a resume allowance.

Run ONCE in the existing WSL terminal holding the exported key:

```bash
cd /mnt/d/AI20K/K5-L3B-Day07-2A202603989-LeThiLy-RetrievalContext
.venv/bin/python -B scripts/milestone4b_smoke.py \
  --mode run \
  --day6-root /mnt/c/Users/Admin/K5-L3B-DAY06-2A202603989-DataIngestion \
  --resume-from results/milestone4b_terminal_real_smoke.json \
  --output results/milestone4b_terminal_real_smoke_resume1.json
```

The runner repeats read-only preflight, reads the key only from process
environment, never logs it, retains fixed :free model/zero price caps and 60s
timeout/512 output tokens. It does not overwrite an existing output. Manual
semantic grounding assessment is still required after completion.

Validation: 68/68 tests PASS (65 previous + 3 new resume tests), all HTTP mocked.
Tests verify inherited 401 + only 5 new requests, sixth new request blocked at
HTTP boundary, persisted reservations, duplicate claims refused, unchanged old
evidence, invalid traces rejected, and cumulative main-report fields. Log:
`results/milestone4b_resume_unit_tests.log`. Actual source trace was parsed
without inference and yielded inherited=1, remaining=5.

Changed: scripts/milestone4b_smoke.py, tests/test_smoke_limits.py, this document,
and the new test log. No Day 06, source corpus, vectors, schema, gold or benchmark
changes; no commit/push. Stop for review.
