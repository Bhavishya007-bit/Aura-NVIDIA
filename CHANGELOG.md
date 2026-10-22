
# Changelog

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
