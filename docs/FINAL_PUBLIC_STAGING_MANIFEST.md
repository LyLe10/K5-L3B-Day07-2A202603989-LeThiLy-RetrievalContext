# FINAL_PUBLIC_STAGING_MANIFEST

Status: **PUBLIC_READY for this reviewed path allowlist plus existing tracked main files**. **FULL_SUBMISSION_READY: BLOCKED** pending grader access/acceptance of restricted evidence. No staging, commit or push has occurred. This is not an allowlist for all local Git refs or the entire working tree.

## Exact PUBLIC_SAFE additions/updates (42)

Each path below is classified PUBLIC_SAFE. Existing tracked, unchanged starter/specification/runtime files remain required base content; this list is the minimal proposed change set, not a stand-alone archive.

```text
data/benchmark/manifest.json
data/benchmark/manifest.sha256
results/milestone5d1_offline/manifest.json
results/milestone5d3a_dependency_pin.json
results/milestone5d_baseline_harmonized_metrics.json
results/milestone5d_e1_candidate_manifest.json
results/milestone5d_e1_final_configuration_lock.json
results/milestone5d_e1_metrics.json
results/milestone5d_e2_metrics.json
results/milestone5d_final_selection_gate.json
results/milestone6_test_baseline_metrics.json
results/milestone6_test_e1_metrics.json
results/milestone6_test_grading_validation.json
results/milestone6_test_paired_comparison.json
results/milestone6_test_runner_offline_validation.json
results/milestone6_test_scoring_cases.json
scripts/dev_agent_evaluation.py
scripts/dev_improvement_experiment.py
scripts/dev_retrieval_benchmark.py
scripts/frozen_test_evaluation.py
scripts/milestone5c_pilot.py
scripts/milestone5c_remaining.py
scripts/prepare_improvement_experiments.py
scripts/validate_benchmark_dataset.py
src/agent.py
src/benchmark_data.py
src/llm.py
tests/test_benchmark_dataset.py
tests/test_context_agent.py
tests/test_dependency_pins.py
tests/test_dev_agent_evaluation.py
tests/test_dev_pilot.py
tests/test_dev_readiness.py
tests/test_frozen_test_runner.py
tests/test_improvement_experiments.py
tests/test_improvement_runner.py
tests/test_remaining_dev.py
report/individual/2A202603989_LeThiLy.md
docs/REPRODUCIBILITY.md
docs/EVIDENCE_ACCESS.md
docs/FINAL_PUBLIC_STAGING_MANIFEST.md
docs/PUBLIC_SUBMISSION_AUDIT.md
```

## Exact staging commands — proposed only

Run from repository root only after user approval and a renewed staged-diff/secret check. Do not use git add ., git add -A, force-add ignored data, push --mirror or push --all. Do not copy .git or internal refs.

```bash
git add -- 'data/benchmark/manifest.json'
git add -- 'data/benchmark/manifest.sha256'
git add -- 'results/milestone5d1_offline/manifest.json'
git add -- 'results/milestone5d3a_dependency_pin.json'
git add -- 'results/milestone5d_baseline_harmonized_metrics.json'
git add -- 'results/milestone5d_e1_candidate_manifest.json'
git add -- 'results/milestone5d_e1_final_configuration_lock.json'
git add -- 'results/milestone5d_e1_metrics.json'
git add -- 'results/milestone5d_e2_metrics.json'
git add -- 'results/milestone5d_final_selection_gate.json'
git add -- 'results/milestone6_test_baseline_metrics.json'
git add -- 'results/milestone6_test_e1_metrics.json'
git add -- 'results/milestone6_test_grading_validation.json'
git add -- 'results/milestone6_test_paired_comparison.json'
git add -- 'results/milestone6_test_runner_offline_validation.json'
git add -- 'results/milestone6_test_scoring_cases.json'
git add -- 'scripts/dev_agent_evaluation.py'
git add -- 'scripts/dev_improvement_experiment.py'
git add -- 'scripts/dev_retrieval_benchmark.py'
git add -- 'scripts/frozen_test_evaluation.py'
git add -- 'scripts/milestone5c_pilot.py'
git add -- 'scripts/milestone5c_remaining.py'
git add -- 'scripts/prepare_improvement_experiments.py'
git add -- 'scripts/validate_benchmark_dataset.py'
git add -- 'src/agent.py'
git add -- 'src/benchmark_data.py'
git add -- 'src/llm.py'
git add -- 'tests/test_benchmark_dataset.py'
git add -- 'tests/test_context_agent.py'
git add -- 'tests/test_dependency_pins.py'
git add -- 'tests/test_dev_agent_evaluation.py'
git add -- 'tests/test_dev_pilot.py'
git add -- 'tests/test_dev_readiness.py'
git add -- 'tests/test_frozen_test_runner.py'
git add -- 'tests/test_improvement_experiments.py'
git add -- 'tests/test_improvement_runner.py'
git add -- 'tests/test_remaining_dev.py'
git add -- 'report/individual/2A202603989_LeThiLy.md'
git add -- 'docs/REPRODUCIBILITY.md'
git add -- 'docs/EVIDENCE_ACCESS.md'
git add -- 'docs/FINAL_PUBLIC_STAGING_MANIFEST.md'
git add -- 'docs/PUBLIC_SUBMISSION_AUDIT.md'
```

Proposed commit message: `Complete Day07 public code, final metrics and restricted-evidence access documentation`.

## Boundary

The 37 core files are explicitly classified in [the public audit](PUBLIC_SUBMISSION_AUDIT.md). [Evidence access](EVIDENCE_ACCESS.md) lists restricted material; no raw/review/question/corpus content is allowlisted. Tests use synthetic fixtures; the scoring-case artifact contains only IDs/split/answerable flags. No TEST gold text is staged.

Existing pinned runner source and local import paths are retained, but private input/data closure is intentionally incomplete. Full benchmark validation, semantic regrading and full-suite reproduction need approved private provisioning. See [reproducibility](REPRODUCIBILITY.md). Source dependencies are not a reason to stage the benchmark builder containing real gold.

Only a future explicit reviewed main-branch publication is contemplated. Internal Codex snapshot refs contain restricted material outside main ancestry. Remote contents were not inspected; do not export all refs. Grader-channel approval, corpus/excerpt permissions and actual access verification remain PENDING.
