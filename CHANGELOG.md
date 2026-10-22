
# Changelog

## 2026-10-22 — Check generic file summaries through selected-file support

- The next live run generated two 916-word, 21-point drafts, but both were
  rejected by the topic judge before factual checking. It returned 264 words
  of excerpts. Checker truncation did not recur; rejection reasons were not logged.
- Recognize generic whole-file summary requests narrowly. With structured
  claims bound to the requested source ID, establish overview task relevance
  through mandatory per-point evidence checks instead of another model veto.
- Keep semantic intent checks for named topics, focused summaries, sections,
  unstructured answers and unbound or mixed-source contexts. Keep rendered-text
  binding, language, citation and factual checks mandatory.
- Add ten controlled regressions, including the two 916-word drafts expanding
  to 1,991 checked words. Broader suite: 153 passed, two optional OCR checks
  skipped. Hosted behavior still requires verification.

## 2026-10-22 — Recover truncated citation checks before summary expansion

- The live 809-word result followed a 1,374-word draft whose citation judge
  exhausted all 4,096 output tokens on reasoning. Verification unavailability
  stopped the expansion path; the material was not established to be missing.
- Apply model-scoped reasoning controls to citation and intent judges. Give a
  truncated judge request one targeted retry, reserving measured reasoning
  overhead up to 8,192 tokens and respecting the existing operator ceiling.
- Keep successful batches, valid negative decisions and strict citation checks;
  repeated truncation or malformed decisions still fail closed.
- Eight controlled regressions pass, including recovery followed by checked
  expansion to 2,010 words. Broader suite: 143 passed, two optional OCR checks
  skipped. Hosted output and judge quality need live validation.

## 2026-10-22 — Extend checked summaries and validate section intent locally

- Carry checked summary units forward in their original order and request only
  additional supported detail from under-covered source sections.
- Validate section topic match against a local question and assigned passages;
  keep word-count and factual-support checks separate and mandatory.
- Batch groups of 2–12 structured claims with independent results instead of
  checking each sequentially. Missing results remain failures.
- Preserve support metadata during recovery, filter exact repeats and stop
  additions when the measured overall length is satisfied.
- Nine new regressions pass, including controlled 1,110-to-2,010-word completion.
  Full suite: 135 passed, two optional OCR checks skipped. Live output remains
  an integration check; no hosted call was made for this update.

## 2026-10-22 — Preserve whole scientific claims and expand short long summaries

- Verify structured summary points directly, preserving scientific abbreviations
  such as `E. coli`; bind the checked units to the actual displayed answer.
- Reject damaged recovered fragments and preserve whole-passage literal evidence.
- Expand still-short long overviews through source-scoped sections, retaining
  checked content and using two shared, targeted repairs within explicit bounds.
- Keep native/OCR/vision representations of a slide together and reject section
  citations to passages outside its assigned source set.
- Add 13 regressions. The 104 relevant checks pass locally; successful live
  requested-length generation and judge calibration remain unverified.
- Broader shared-validator/retrieval checks: 126 passed, two optional OCR checks skipped.

## 2026-10-22 — Align summary drafts and coverage contracts

- Permit coverage parts to reference up to the 96 supplied passages and send
  the actual coverage schema and valid ID range to the judge.
- Normalize redundant inline summary citations only when they match structured
  IDs; keep rejecting foreign IDs and checking every resulting source claim.
- Preserve rejected drafts with specific format/schema repair feedback instead
  of discarding them. Keep a checked short draft if the next draft is empty.
- Send explicit word bounds, sentence targets and schema limits to summary
  generation. Log safe draft counts and distinct render failure codes.
- Ten new regressions pass; all 91 relevant local checks pass. Live hosted
  generation at the requested length remains an integration check.

## 2026-10-22 — Reserve tokens for long Nemotron summaries

- Use the documented Nebius `reasoning_effort=none` request field for long
  summaries on the observed Nemotron 3 Super model, with an optional override.
- Keep short summaries, coverage/verification clients and other answers unchanged.
- Replace an identical truncation retry with a measured reasoning-token reserve,
  within the existing two-attempt limit and configured global output cap.
- Add eight controlled regressions, including the two supplied live truncation
  patterns and recovery to 2,000 checked words. All 81 relevant checks pass.
- Live provider acceptance/control compliance remains to be verified; no hosted
  model call was made for this update. See `docs/LONG_ANSWERS.md`.

## 2026-10-22 — Exclude backend runtime files from Vite watching

- Ignore the backend directory and descendants so LibreOffice's locked preview
  profile files cannot enter the frontend watcher.
- Verify with a running Vite server that existing/new backend files are ignored,
  frontend add/change events remain active, and the UI returns HTTP 200. This
  check ran on Linux; the reported Windows file lock was not reproduced here.
- Add private-data-safe provider failure codes, token usage and schema paths
  for diagnosing the still-unresolved live long-summary failure.
- Eight new diagnostics regressions pass; 73 relevant Python checks and the
  frontend build pass. No hosted model call was made for this update.

## 2026-10-22 — Honor length and format follow-ups

- Resolve `in 2000 words` and chained style/length modifiers against the preceding topic.
- Scale summary sentence limits, answer token budgets and owned document context.
- Measure the generated length, request one bounded revision, and report unmet targets.
- Batch long-answer claim checks with independent, strictly validated per-claim results.
- Add 23 response regressions and three PostgreSQL document-context checks.

See `docs/LONG_ANSWERS.md` for measured behavior, limits and validation scope.

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
