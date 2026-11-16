# AGENTS.md — Day 07 Agentic RAG

## Objective
Implement the VinUni AI20K Day 07 Retrieval & Context Engineering lab, following README.md, GUIDE.md, RULES.md, RUBRIC.md, BENCHMARK.md, SUBMISSION.md and the actual starter code.

## Working principles
1. Read the relevant lab specification before implementation.
2. Inspect the existing code, tests, dependencies and Day 06 database schema.
3. Work incrementally, one milestone at a time.
4. Preserve existing public interfaces unless changes are justified.
5. Never fabricate benchmark results, tool calls, citations or evaluation metrics.
6. Never use gold answers or gold evidence to influence retrieval or agent decisions.
7. Do not tune on the test set.
8. Do not modify Day 06 source data, snapshots, embeddings or migrations without explicit approval.
9. Never commit .env, credentials, API keys or private datasets.
10. Do not commit or push without explicit user approval.

## Required implementation
- Reuse the real Day 06 embedding model and pgvector store.
- Implement and compare at least three retrieval methods.
- Implement a real LLM-powered retrieval agent.
- Provide evidence-grounded answers and abstention.
- Preserve source metadata, chunk IDs and page references.
- Log tool calls, retrieval results, context, citations, errors, latency and cost.
- Build the required 17-question dev and 7-question test benchmark.
- Evaluate at least two improvement configurations.
- Analyze at least two development-set failures.
- Freeze the selected configuration before evaluating on test.

## Cost control
- Prefer local embeddings and database retrieval.
- Use small smoke tests before full evaluations.
- Cache reusable retrieval results when valid.
- Avoid repeated API calls for unchanged inputs.
- Record token usage and estimated cost where available.

## Workflow
For each milestone:
1. Inspect relevant files.
2. State the implementation plan.
3. Implement only the approved scope.
4. Run focused tests.
5. Summarize changed files, test results, remaining risks and next steps.
6. Stop and wait for review before moving to the next milestone.

## Definition of done
The solution must be reproducible, benchmarked, traceable and compliant with the lab rubric. Passing mock unit tests alone is insufficient.