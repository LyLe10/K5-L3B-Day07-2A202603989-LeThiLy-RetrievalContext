# Restricted evidence access

**ACCESS_CHANNEL: PENDING. GRADER_ACCEPTANCE: PENDING. FULL_SUBMISSION_READY: NO.**

Policy: public code and numeric metrics; restricted questions/gold, corpus excerpts, raw traces and semantic-review evidence. This document lists paths/roles only, not their contents. It does not grant redistribution permission or create an access channel.

## Restricted evidence manifest

| Exact path or group | Why restricted / grader purpose |
|---|---|
| `data/benchmark/dev.json` | Frozen DEV questions/answers and evidence; controlled benchmark reproduction |
| `data/benchmark/test.json` | Frozen TEST questions, expected answers and gold; never public staging |
| `scripts/build_milestone5a_benchmark.py` | Contains benchmark construction literals, including TEST material; source code is not automatically public-safe |
| `results/milestone5a_dataset_freeze.json`, `results/milestone5a_dataset_validation.json`, `results/milestone5a_frozen_pin_validation.json` | Mixed validation/gold audit; schema/freeze/absence checks |
| `results/milestone5b_dev_retrieval.json` | 51 ranked retrieval traces containing corpus text; Dense/TF-IDF/Hybrid evidence |
| `results/milestone5c3c_dev17_traces.json` | Baseline DEV raw responses/context |
| `results/milestone5d_e1_raw.json`, `results/milestone5d_e2_raw.json` | DEV experiment responses/context |
| `results/milestone5d_baseline_harmonized_reviews.json`, `results/milestone5d_e1_manual_review.json`, `results/milestone5d_e2_manual_review_final.json` | Approved labels with textual evidence/rationales; not just public metric counts |
| `results/milestone6_test_baseline_raw.json`, `results/milestone6_test_e1_raw.json` | Completed TEST responses, questions and retrieved corpus excerpts |
| `results/milestone6_test_baseline_manual_reviews.json`, `results/milestone6_test_e1_manual_reviews.json` | Approved TEST semantic evidence/rationale |
| `results/milestone6_test_run/baseline/identity.json`, `results/milestone6_test_run/E1/identity.json` | Controlled execution provenance |
| `results/milestone6_test_run/baseline/requests.jsonl`, `results/milestone6_test_run/E1/requests.jsonl` | Request/outcome/reservation audit; preserved read-only |
| `results/milestone6_test_run/baseline/checkpoints/`, `results/milestone6_test_run/E1/checkpoints/` | Duplicated per-case raw evidence; original checkpoint hashes/accounting |
| `results/milestone5d_e1_run/`, `results/milestone5d_e2_run/` | Original experiment identity/journal/checkpoints, including copied corpus |
| `results/milestone5c_pilot_requests.jsonl`, `results/milestone5c3a_remaining_requests.jsonl` | Baseline DEV accounting chain |
| `results/milestone5d1_offline/offline_readiness.json` | Replay answer content; controlled predeclared-design evidence |
| Other raw/smoke/draft `.json`, `.jsonl`, checkpoint and mixed audit files not explicitly allowlisted | May contain questions, answers or corpus; do not infer safety from filename |
| External Day06 corpus, vectors, models and database access | Not part of public repo; permissions/provisioning required separately |

Do not include API keys, .env, credentials or unredacted terminal dumps even in a grader bundle. If credentials are needed for runtime access, use a separately approved secure mechanism. Corpus/excerpt sharing must respect its notice/permission conditions; no notice copy or permission grant is fabricated here.

## Proposed access process — not yet implemented

1. User identifies the grader and approves a restricted read-only channel (for example a separately controlled private repository or institutional file share). These are options, not channels already created.
2. User confirms corpus/excerpt rights and required notices, recipient access and permitted use. Preserve originals and their SHA256; never overwrite public metrics/grades to fit a different bundle.
3. Provide only required evidence from the table with a private integrity inventory. Keep TEST material separate from inference inputs. Do not use gold to tune the selected system.
4. Verify grader access and record acceptance of the restricted route under SUBMISSION.md:20–25. Until then mark PENDING, not full completion.
5. Reaggregation/audit should be offline; no new paid run is needed to inspect completed evidence. Any rerun or account change needs separate approval.

## Integrity disclosure and Git history

An earlier audit may have exposed TEST gold in truncated local tool output. User chose KEEP_EXISTING_TEST_WITH_DISCLOSURE and reports instructor acceptance. No completely blind evaluation claim is made; existing TEST/configuration remains unchanged. This does not establish acceptance of the separate restricted-sharing channel above.

Local Git audit found restricted snapshots reachable through internal `refs/codex/*`. No matches were found in the current `main`/HEAD ancestry under the recorded scan. Do not mirror this repository or export internal refs/whole .git for public delivery. A narrowly scoped future push of the reviewed main branch requires separate approval. No refs/history were deleted or rewritten; remote contents were not inspected. See [public audit](PUBLIC_SUBMISSION_AUDIT.md).
