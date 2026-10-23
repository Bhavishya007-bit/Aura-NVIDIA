# Study tools: authenticated Nebius adapter

Flashcards failed because `backend/study_tools.py:model_json` manually sent an Ollama request body to the Nebius URL supplied by the current `LLM` client. The request had no Bearer header and parsed an Ollama response envelope. It bypassed the authenticated client used by Tutor and Study Plan.

The approved backend fix routes this shared adapter through `LLM.generate_json`:

- Uses the existing server-side Nebius credentials, endpoint and configured answer model.
- Uses the client's JSON-object response mode and parser, including rejection of truncated output.
- Supplies the application JSON schema as trusted system instructions. JSON-object mode guarantees JSON syntax, not complete JSON-schema compliance; the existing item, count, citation, duplicate, answer-key and source-verdict validators remain responsible for acceptance.
- Preserves each call's output-token budget, bounded by the existing operator ceiling. Uses one transport attempt per adapter call; existing bounded generation/structure-repair loops remain intact.
- Uses the existing writing reasoning settings for generation and verification settings for source judging, short-answer grading and misconception classification. For the configured Nemotron Super model, their existing default is no reasoning, preserving room for small JSON outputs.
- Returns controlled, provider-neutral HTTP 503 errors for configuration, authentication, transport and invalid-response failures. Detailed sanitized provider diagnostics stay in backend logs.

The shared fix applies to Flashcards, Notes, Summary, Assessment and their grading helpers. No API routes, request/response fields, database migrations, environment-variable names or dependencies were added. Existing image/OCR services are outside this change.

## Validation

`python -m unittest evaluation.check_study_provider -v` passes 12 targeted checks. These use the real adapter, HTTP response parser and validators with synthetic provider replies. They cover authentication headers, absence of Ollama protocol fields, complete schema instructions, budget limits, isolated reasoning settings, service-error handling, invalid/truncated JSON, fail-closed verdict checks, and authenticated short-answer grading.

A fixture-backed FastAPI route test generates, source-checks and saves each of the four tool kinds through `/study/tools`, retaining its response shape and hiding assessment answer keys. Database operations and provider responses are simulated; no private student database is used.

The broader evaluation suite ran 200 tests: **198 passed, 2 skipped**. Optional PostgreSQL checks used the locally installed PGlite test engine. Python compilation also passes. No live Nebius credentials are available in the agent environment, so hosted generation still needs the local retest below.

## Local retest in PowerShell

From the Aura-NVIDIA project folder, pull the latest main branch:

```powershell
git pull --ff-only origin main
```

Stop the running FastAPI process with Ctrl+C, then restart it using the existing virtual environment:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Keep the frontend running. Refresh the browser, select the presentation, open Flashcards and click Generate. Repeat with one short-answer assessment if Flashcards succeeds. No upload, dependency reinstall or database migration is required for this adapter fix.

If it still fails, capture the new `provider=nebius` log lines and the study-generation warning from that attempt. Their HTTP status/failure code distinguishes credential, model-access/quota, timeout, output truncation and validation failures. Do not copy secrets into the report.
