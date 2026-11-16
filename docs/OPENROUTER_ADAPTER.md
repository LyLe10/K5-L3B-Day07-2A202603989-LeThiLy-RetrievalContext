# Milestone 4B — OpenRouter adapter (2026-11-16)

Implementation complete; real LLM validation NOT RUN. No DEV/TEST benchmark,
Day 06 modifications, commit or push. No credential was read from WSL or printed.
The key set in an interactive WSL shell must be inherited by the actual Python
process; Windows and new WSL shells do not necessarily inherit that environment.

Reviewed README, GUIDE, RULES, RUBRIC, BENCHMARK, SUBMISSION, starter Controller,
src/agent.py, src/llm.py, retrieval adapter and dependencies. RUBRIC explicitly
allows local models or APIs, with no paid requirement. OpenRouter is therefore
compatible with provider requirements, subject to RULES' permission to send the
selected corpus to an external service. No data permission is inferred here.

## Behavior

`OpenRouterController(model, timeout=60, max_output_tokens=512)` implements
`decide(question, history) -> dict` unchanged. It uses the existing system prompt
and normalized JSON search/answer actions, not native function calling. JSON
output must parse to an object; existing agent validation handles actions and
citations. Malformed or truncated output is an operational error, not abstention.
No JSON-schema API parameter is required, improving compatibility with free
providers; real-model formatting reliability remains unverified.

Only explicit vendor/model IDs ending in `:free` are accepted. Requests use one
model, no model fallback list, `allow_fallbacks=false`, and zero prompt/completion
price caps. No automatic retries, downloads or network calls on initialization.
Redirects are refused to avoid forwarding credentials/context elsewhere.
Authorization comes exclusively from OPENROUTER_API_KEY in the process environment.
Timeouts, missing key, HTTP 401/429, other HTTP/provider errors and malformed
responses have sanitized trace codes. Raw provider messages/bodies are not logged.
Usage token counts, reported cost and latency are recorded; missing cost is null,
never a fabricated zero. Existing agent trace preserves detailed controller errors.

## Proposed model and smoke budget (pending approval)

Propose `qwen/qwen3-next-80b-a3b-instruct:free`. The official
[model page](https://openrouter.ai/qwen/qwen3-next-80b-a3b-instruct:free)
lists free pricing and describes multilingual instruction following, RAG and
agentic use without thinking traces. This is a candidate, not evidence of success
on our corpus. Availability/rate limits may change. Routing controls follow
[official provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

With `--max-searches 2`, each case has at most 3 LLM API calls and 2 local
retrieval calls. Expected search then answer/abstain: 2 API calls per case,
4 total for evidence + insufficient-evidence cases; hard upper bound 6 total.
Max output 512 tokens/call: at most 3,072 output tokens across both cases.
Failures can end earlier; no retries. Actual usage, cost and grounding remain
unmeasured. No metadata/generation API calls are planned.

After user approval, invoke the existing script in the WSL shell holding the key:

```bash
# TEMPLATE ONLY — not executed; requires existing exact-model local tokenizer.
.venv/bin/python -B scripts/agent_smoke.py \
  --provider openrouter --approve-openrouter \
  --day6-root "$DAY6_ROOT" --method hybrid \
  --model qwen/qwen3-next-80b-a3b-instruct:free \
  --tokenizer-path "$QWEN3_NEXT_TOKENIZER_PATH" \
  --question "$SMOKE_QUESTION" --output "$NEW_TRACE_PATH" \
  --budget 1200 --max-searches 2
```

The tokenizer must match this model; do not reuse the E5 or Qwen2.5 tokenizer.
No tokenizer downloaded in this milestone. Real smoke still needs tokenizer
availability, corpus-sharing permission and human review of claim/citation support.
The script retains existing Ollama arguments and requires explicit OpenRouter
opt-in. No default provider switch can accidentally send local data externally.

## Verification

WSL existing `.venv/bin/python -B -m unittest discover -s tests -v`:
59/59 PASS (51 existing + 8 new). All OpenRouter HTTP is mocked, including
authorization, free routing caps, timeout, 401, 429, provider errors, malformed
output, usage, missing key, no redirect, and agent answer/abstention integration.
Windows default Python initially failed two existing tests due to missing dotenv
and its default encoding; no production code was changed to hide these issues.
See `results/milestone4b_openrouter_unit_tests.log` for final WSL run.

Changed scope: src/llm.py, scripts/agent_smoke.py, tests/test_openrouter.py,
this document and the unit-test log. Stop here for review before real API calls.
