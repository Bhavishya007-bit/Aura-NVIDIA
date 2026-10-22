
# Changelog

## 2026-10-22 — Recover useful summaries after checking failures

- Give uploaded-file summaries a dedicated structured prompt and server-formatted citations.
- Allow summaries of readable samples when the coverage check is partial or unavailable.
- Preserve individually checked points from a rejected draft; otherwise return explicitly labelled exact source excerpts.
- Keep wrapped source lines together and suppress misleading absence notices on successful summaries.
- Log checking stages without logging private prompts, documents or credentials.
- Add 15 regressions for the summary failure shown in the screenshot.

This is an answer-path change; the current prepared upload can be reused. See
`docs/TUTOR_RECOVERY.md` for test scope and limitations.

## 2026-10-22 — Conversation and slide-evidence recovery

- Preserve background answers in scoped conversation history and resolve person pronouns.
- Prioritize topic headings and same-slide labels; retain rescued and previously checked evidence.
- Prevent absence claims when exact topic mentions or reading failures contradict them.
- Add rendered-slide reading, higher-resolution bounded OCR and visible preparation notices.
- Correct the optional Ollama vision endpoint after the Nebius text migration.
- Add conversation, retrieval-failure and real synthetic PPTX/PDF OCR regressions.

See `docs/TUTOR_RECOVERY.md` for verification and the required fresh upload.

## 2026-10-22 — Phase 2 source-aware answering foundation

- Add full/partial/not-covered/unknown coverage decisions and a bounded retrieval retry.
- Separate verified document answers from explicitly unverified model background.
- Add Grounded/Intelligence API settings, depth instructions, and versioned prompts.
- Preserve account-scoped retrieval, legacy answer fields and original-image handling.
- Add configurable model-role candidates and cached-token measurements.
- Replace refusal-based API evaluation with coverage/provenance records; add synthetic suites and offline checks.
- Remove a credential-like value from the tracked environment template; key rotation remains necessary.

Live quality/latency/cost benchmarking, judge calibration, ingestion optimization,
agents, persistent memory and product UI work remain outstanding. See
`docs/PHASE2_SOURCE_AWARE.md` for verification commands and limitations.
