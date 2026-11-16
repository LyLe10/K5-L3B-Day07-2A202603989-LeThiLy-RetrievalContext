# Public minimal submission audit

Date: 2026-11-16. Offline only. Policy: PUBLIC CODE + PUBLIC METRICS + RESTRICTED EVIDENCE.

## Current publication and documentation cleanup

Public submission commit: `bdce3bd7f2ecaddbbc13314a46b952e46f659fa0` (local HEAD verified; user confirms GitHub push). Baseline/E1 frozen TEST and approved manual grading are complete. **PUBLIC_READY: PASS for the reviewed public content. FULL_SUBMISSION_READY: BLOCKED** pending restricted grader access/acceptance. No network verification of remote publication was performed here.

The current approved cleanup reduces tracked documentation from 19 files to six: [index](README.md), [reproducibility](REPRODUCIBILITY.md), [evidence access](EVIDENCE_ACCESS.md), [dense retrieval](DENSE_RETRIEVAL.md), [lexical/hybrid retrieval](LEXICAL_HYBRID.md), and this audit. Agent/context architecture, OpenRouter handling and accounting/resume principles from three removed milestone documents are consolidated in REPRODUCIBILITY. Obsolete free-model, smoke budget and pending-execution instructions are not current instructions.

The sections below record the **historical pre-publication audit**, including then-current file counts, HEAD, pending staging and hash comparisons. They do not describe the current cleanup diff or deny the subsequent publication at bdce3bd. The old staging manifest is retired; use the current six-document index and Git diff for cleanup review.

### Historical hash inventories and removed documents

`results/milestone5d_final_selection_gate.json` records historical `source_hashes`; `results/milestone6_test_runner_offline_validation.json` records historical `protected_input_sha256`. These inventories include documents now removed or updated. They are immutable evidence of earlier inputs, not a current Markdown navigation manifest or instructions to repin runtime dependencies. They remain unchanged. Obtain the historical version with `git show bdce3bd:docs/<filename>` and compare the recorded hash; do not rewrite an inventory to match today's documentation. The E1 lock, pinned runtime source and result artifacts remain unchanged by cleanup.

Approved removals: FINAL_PUBLIC_STAGING_MANIFEST.md; MILESTONE2_REPORT.md; MILESTONE3_REPORT.md; MILESTONE4_REPORT.md; OPENROUTER_ADAPTER.md; MILESTONE4B_PAID_SAFE_RESUME.md; MILESTONE4B_BUDGET1_UPDATE.md; MILESTONE4B_KEY_LIMIT_DIAGNOSIS.md; MILESTONE4B_PAID_MODEL_REVIEW.md; MILESTONE4B_REAL_LLM_REPORT.md; MILESTONE4B_REPORT.md; MILESTONE4B_SAFE_RESUME.md; MILESTONE4B_TERMINAL.md (all under docs/). Deletion changes the current tree only, not prior public Git history; no history rewrite or internal-ref removal is authorized/performed.

Source contracts still require benchmark/per-query evidence, grading and reproduction access under SUBMISSION/RUBRIC; removing duplicate milestone narratives does not waive those obligations. No new inference or evaluation is needed for this documentation cleanup. No cleanup staging, commit or push has been performed.

## Historical decisions before public commit

- PUBLIC_READY: **PASS for the explicit reviewed bundle and current tracked main ancestry**, subject to normal pre-publication staged-diff review and separate commit/push approval.
- FULL_SUBMISSION_READY: **BLOCKED**. Required benchmark/per-query evidence and approved labels exist locally, but the grader's restricted access channel and acceptance are PENDING.
- No source, tests, configuration, lock, raw, reviews, metrics, benchmark or journal was edited. Only the personal report and four new documentation files are part of this task's changes.
- No API/network, inference, DEV/TEST benchmark, reservation, staging, commit or push was performed.

## Contract and missing deliverables

SUBMISSION.md:19–25 requires code/three retrieval methods/tests/instructions, Day06 embedding/vector access or recreation, split benchmark (20 evidence + 4 absence), per-query/tool/context/answer/citation/error/time/cost evidence, two improvements/labels/failure analysis, personal report and grader access. RUBRIC.md:7–12 requires corresponding verifiable data, retrieval, Agent/context, evaluation, experiments and reproduction evidence. ADVANCED bonus is not claimed.

Public code/metrics/report cover implementation and published conclusions. Restricted benchmark (17 DEV + 7 TEST), 51 retrieval traces, Agent raw traces, approved semantic labels and original accounting are NOT replaced by aggregate numbers. Complete submission requires an approved restricted channel, corpus/excerpt sharing conditions, verified grader access, Day06 provisioning instructions and grader acceptance. Do not mark these mandatory evidence obligations PASS based only on this public manifest.

## Core-file classification

All 37 files were inspected as source/tests, structured metric/configuration metadata, or checksums. Generic SYSTEM prompts and synthetic fixtures contain no real DEV/TEST answers. Public scoring-case IDs/answerable flags do not contain questions or evidence. Hash/path references to restricted files disclose provenance, not file contents.

| File | Classification | Reason |
|---|---|---|
| `data/benchmark/manifest.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `data/benchmark/manifest.sha256` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone5d1_offline/manifest.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone5d3a_dependency_pin.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone5d_baseline_harmonized_metrics.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone5d_e1_candidate_manifest.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone5d_e1_final_configuration_lock.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone5d_e1_metrics.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone5d_e2_metrics.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone5d_final_selection_gate.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone6_test_baseline_metrics.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone6_test_e1_metrics.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone6_test_grading_validation.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone6_test_paired_comparison.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone6_test_runner_offline_validation.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `results/milestone6_test_scoring_cases.json` | PUBLIC_SAFE | Configuration, checksum or numeric metric metadata; no question/gold/corpus text |
| `scripts/dev_agent_evaluation.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `scripts/dev_improvement_experiment.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `scripts/dev_retrieval_benchmark.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `scripts/frozen_test_evaluation.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `scripts/milestone5c_pilot.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `scripts/milestone5c_remaining.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `scripts/prepare_improvement_experiments.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `scripts/validate_benchmark_dataset.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `src/agent.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `src/benchmark_data.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `src/llm.py` | PUBLIC_SAFE | Runtime/validation code; no benchmark construction literals |
| `tests/test_benchmark_dataset.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `tests/test_context_agent.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `tests/test_dependency_pins.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `tests/test_dev_agent_evaluation.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `tests/test_dev_pilot.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `tests/test_dev_readiness.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `tests/test_frozen_test_runner.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `tests/test_improvement_experiments.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `tests/test_improvement_runner.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `tests/test_remaining_dev.py` | PUBLIC_SAFE | Synthetic tests; private fixtures may still be required at runtime |
| `report/individual/2A202603989_LeThiLy.md` | PUBLIC_SAFE | Sanitized report; IDs/metrics and abstract failure analysis only |
| Four new public documentation files in staging manifest | PUBLIC_SAFE | Access boundaries, paths, audit and instructions only |

## Other classifications / exclusions

| Paths/group | Classification | Action |
|---|---|---|
| Frozen DEV/TEST JSON, corpus, builder literals, raw traces, semantic reviews and mixed gold audits listed in EVIDENCE_ACCESS | RESTRICTED | Never public stage; controlled grader access required |
| Local run identities/journals/checkpoints and original evidence | RESTRICTED | Preserve immutable originals; not needed publicly |
| `results/milestone5d1_offline/offline_readiness.json` | RESTRICTED | Contains replay answer content, unlike public manifest |
| Intermediate milestone reports/drafts/duplicated audits not allowlisted | EXCLUDE from this submission change set | Final report covers conclusions; some contain restricted quotations |
| .env, credentials, API keys, live DSNs, terminal dumps, caches, .venv, models/wheels, local DB/data, temporary files | EXCLUDE | Never stage; some are ignored, but .gitignore is not a security boundary |
| Private evidence distribution rights/channel and grader acceptance | NEEDS_APPROVAL | PENDING; no permission granted by this audit |

Existing .gitignore excludes .venv, Python caches, .env variants, .codex-log, starter generated data/results and data/local. It does NOT exclude all benchmark/results files; exact-path staging is essential. It was not changed.

## Git history exposure

Local HEAD/main and local origin/main reference `f2382b648ff673195eff5e425c84bd9772b6e23b`. No network fetch/remote inspection occurred.

The scan inspected 466 reachable local blobs. Restricted fingerprints matched 91 blobs reachable through internal Codex snapshot refs outside HEAD ancestry, including frozen benchmark JSON, the benchmark builder, raw traces, checkpoints and manual reviews. **No matching restricted content was found in HEAD ancestry or current tracked files** under this scan. No high-confidence live-secret pattern was found. This does not prove absence of every paraphrase, short quotation, unreachable object or remote exposure.

Method: normalized complete question/expected-answer fingerprints and long corpus substring comparisons; candidate content was evaluated without copying gold into this report. Current allowlisted public files are separately checked. Internal refs were neither removed nor rewritten. They are not evidence that restricted material was pushed.

Publish only a reviewed main branch after approval, never mirror/all internal refs or the entire .git. A whole-repository Git bundle/mirror is NOT PUBLIC_SAFE. If such an export is required, stop for a separately approved history/export remediation.

## Reproduction and link closure

The explicit manifest plus unchanged tracked main files supplies application source imports, starter code and pinned source paths. External Day06 source/model/database and frozen datasets/raw/reviews remain restricted. Public clone cannot reproduce full benchmark/semantic grading without them; missing inputs must fail closed.

Report links to omitted milestone/raw/review files have been replaced with internal sections or final public artifacts/access documentation. Four required report sections and approved numeric results are retained; no TEST questions/expected answers/gold excerpts or corpus quotations are published. Detailed corpus-supported failure evidence stays private. Public links are checked against the intended tracked-base plus allowlist, not merely local file existence.

Offline starter tests: **14/14 PASS** with UTF-8 Python runtime. Initial native Windows run had one cp1252 decoding error in a temporary fixture; rerun with PYTHONUTF8=1 passed without source edits. These synthetic tests are not a DEV/TEST pipeline or a reproduction of private evaluation. Historical full-suite 193/193 is reported separately, not rerun/promised for a public-only clone.

## Publication and completion gates

### Final offline validation results

- 42/42 exact allowlisted paths exist; 41 local Markdown links in the proposed documentation/report resolve within the tracked base plus public allowlist; zero broken or excluded file targets.
- Static local Python import scan of the proposed code/tests found zero missing existing local modules in that same public file set. This is source-path closure, not proof of private data/runtime closure.
- All 302 pre-task protected file hashes were compared: only the authorized personal report changed. Existing source/tests/metrics/raw/reviews/journals/benchmark artifacts remained byte-identical. Four documentation files are new.
- E1 lock SHA256 remains `87febe40ba9ba2c2e3204333e75b1578e830bb10469b29e3d4116be353e5579e`.
- Four required report sections remain. No allowlisted file exceeds 5 MiB. No new generated evidence/ledger/reservation was created.
- Documentation diff: personal report rewritten into public metrics/abstract failure analysis with restricted links replaced; REPRODUCIBILITY, EVIDENCE_ACCESS, FINAL_PUBLIC_STAGING_MANIFEST and this audit added. An unredacted old/new report diff is intentionally not embedded in public documentation because deleted text may itself disclose restricted TEST material. The original report snapshot was used only for in-memory comparison, not added to the public bundle.

1. Approve the reviewed public exact-path staging set; inspect staged diff, secrets and main history before any separately approved push.
2. Approve a restricted channel and sharing conditions; provide existing immutable evidence and Day06 reproduction assets without secrets.
3. Verify grader access/acceptance and update completion status only then.

No additional inference is required to resolve public/restricted packaging. Existing negative results, approved grades and TEST exposure disclosure are retained.
