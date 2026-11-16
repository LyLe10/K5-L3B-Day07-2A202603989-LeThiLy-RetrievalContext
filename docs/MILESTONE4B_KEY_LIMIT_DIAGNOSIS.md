# Milestone 4B — KEY_LIMIT_NOT_SAFE diagnosis

2026-11-16 (Asia/Bangkok). Diagnosis/code tests only; no live key metadata,
inference or database requests were made in this change.

## Evidence and limits of the finding

Inspected src/openrouter_paid.py, scripts/milestone4b_paid_smoke.py, existing
paid tests and results/milestone4b_paid_terminal_preflight.json. The actual
saved trace has errors=[KEY_LIMIT_NOT_SAFE], no key_budget object or diagnostic
fields, metadata_checks=1, inherited calls=2, new calls=0, remaining calls=4.
The original evidence was preserved.

The old verifier parsed response['data'], then converted limit,
limit_remaining and usage into finite, nonnegative numbers before reaching
KEY_LIMIT_NOT_SAFE. Therefore the observed code proves that those conversions
passed. Missing/null/string/bool/nonfinite/negative numeric fields would have
raised INVALID_KEY_BUDGET_METADATA instead, and an HTTP/parsing failure would
have produced another error. A low remaining balance alone would have produced
KEY_REMAINING_BUDGET_INSUFFICIENT, not the observed code.

The exact old OR expression could raise KEY_LIMIT_NOT_SAFE for ANY of:

1. limit_reset key absent.
2. limit_reset is not Python None (any non-null JSON value).
3. limit equals zero (negative already rejected by amount()).
4. limit > 0.10.
5. limit_remaining > limit.
6. usage > limit.
7. limit_remaining + usage > limit + 0.000001.

No raw or sanitized metadata snapshot exists in the failing artifact, so the
specific true predicate cannot be recovered. It would be fabrication to assert
that this key definitely has a cap above $0.10, is uncapped, or resets daily.
Multiple predicates may fail at once; the old code hid all of them behind one
message. This lost diagnostic detail is the confirmed code defect.

## Parsing and null semantics

Official [limits documentation](https://openrouter.ai/docs/api/reference/limits)
describes limit=null as unlimited, limit_remaining=null as unlimited remaining
credit, and limit_reset=null as never resetting. The same JSON null value has
different meanings in different fields; it must not be mapped generically to
zero or to missing metadata.

Python json.load maps JSON null to None. JSON string "null" remains a string,
not None. Missing key and an explicit null also differ; the old numeric .get()
calls conflated these in the error code, and the new verifier separates them.
No string-to-number conversion or reset normalization was introduced.

GET [current key metadata](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-api-key)
returns an object under data. Invalid JSON, missing data, data=null or data
as a list now produce KEY_METADATA_RESPONSE_INVALID. Network/HTTP errors remain
KEY_METADATA_REQUEST_FAILED; no raw response bodies/headers are retained.

## New distinct codes and remediation

| Condition | Error | Action before inference |
|---|---|---|
| limit explicitly null | KEY_LIMIT_UNCAPPED | Stop. User must review/configure an existing finite per-key cap within the approved policy; code never changes it. |
| limit > $0.10 | KEY_LIMIT_EXCEEDS_APPROVED_BUDGET | Stop. User reviews the actual key's cap; account credits are not a key cap. |
| limit=0 | KEY_LIMIT_ZERO | Stop. Zero permits no spend; do not treat it as unlimited. |
| limit_reset absent | KEY_RESET_METADATA_MISSING | Stop. Verify metadata/schema; missing does not prove never-resetting. |
| limit_reset non-null, including string "null" | KEY_RESET_POLICY_NOT_ALLOWED | Stop. Review the reset setting; policy requires actual JSON null. Do not silently normalize. |
| finite remaining < $0.020 initially | KEY_REMAINING_BUDGET_INSUFFICIENT | Stop. Check remaining allowance; adding account credits alone does not raise the key cap. |
| remaining > limit | KEY_REMAINING_EXCEEDS_LIMIT | Stop. Review inconsistent metadata with OpenRouter; do not estimate a usable allowance. |
| usage > limit | KEY_USAGE_EXCEEDS_LIMIT | Stop. Review usage/cap history; no automatic override. |
| remaining+usage > limit+0.000001 | KEY_BUDGET_TOTAL_INCONSISTENT | Stop. Review inconsistent metadata; tolerance unchanged. |
| numeric field missing | KEY_LIMIT_METADATA_MISSING / KEY_REMAINING_METADATA_MISSING / KEY_USAGE_METADATA_MISSING | Stop. Verify the response schema. |
| remaining/usage explicitly null | KEY_REMAINING_UNVERIFIABLE / KEY_USAGE_UNVERIFIABLE | Stop. No finite budget can be confirmed under current policy. |
| invalid type, nonfinite or negative number | KEY_LIMIT_METADATA_INVALID / KEY_REMAINING_METADATA_INVALID / KEY_USAGE_METADATA_INVALID | Stop. Do not coerce invalid metadata. |
| invalid response structure/JSON | KEY_METADATA_RESPONSE_INVALID | Stop. Verify endpoint/schema. |
| HTTP/network failure | KEY_METADATA_REQUEST_FAILED | Stop. Diagnose separately, no automatic retry. |

Validation raises the first applicable code and stores all failed original
numeric/reset safety predicates in key_budget_diagnostics.failed_checks. The
diagnostic snapshot contains only fixed field names/categories: reset_state is
missing/json_null/string_null/non_null. No raw reset value, key, Authorization,
label, hash, account ID or raw response is logged. Successful metadata output
retains the previously permitted numeric budget fields.

Acceptance policy is unchanged: positive finite cap <=$0.10, actual null reset,
valid nonnegative numeric usage/remaining, original consistency tolerance,
and sufficient remaining reservations. No budget, price cap, request limit,
reservation, retry, fallback or model changes were made.

## Safe next diagnostic command (no inference, no database)

In the WSL terminal holding the key:

```bash
cd /mnt/d/AI20K/K5-L3B-Day07-2A202603989-LeThiLy-RetrievalContext
.venv/bin/python -B scripts/milestone4b_paid_smoke.py \
  --mode key-preflight \
  --resume-from results/milestone4b_terminal_real_smoke_resume1.json \
  --output results/milestone4b_paid_key_diagnosis.json
```

This only validates local resume evidence and GETs key metadata. It creates no
resume claim/reservation and sends no questions or chunks. The output is new;
the previous failing trace is not overwritten. Read errors plus
key_budget_diagnostics to identify the actual cause, then review the relevant
account setting or metadata issue manually before a full preflight. No need
to paste the key or full metadata response into chat. Do not rerun inference
until budget verification and full preflight pass and execution is approved.

## Tests and files

89/89 tests PASS (82 previous + 7 diagnosis tests), 1.147 seconds in WSL .venv;
all HTTP mocked. Added explicit error-code cases, missing-vs-null distinction,
JSON round-trip tests, overlapping-predicate diagnostics, invalid envelopes,
sanitized runner reporting and equivalence with the previous acceptance rule
over 720 boundary combinations (8 limits * 6 remaining * 5 usage * 3 resets).
No acceptance decisions changed across those cases.

Log: results/milestone4b_key_budget_diagnostics_unit_tests.log.
Changed src/openrouter_paid.py, scripts/milestone4b_paid_smoke.py; added
tests/test_key_budget_diagnostics.py, this report and new log. Old traces,
journals and claims untouched. No key limit/account updates, inference,
DEV/TEST, Day 06 writes, commit or push. Budget remains 2 used / 4 remaining.
