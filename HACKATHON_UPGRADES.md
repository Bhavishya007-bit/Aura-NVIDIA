
# Aura hackathon upgrades

## Preserved base

Authentication, private workspaces, multimodal document ingestion, pgvector
retrieval, citation checking, assessments, learner estimates and source viewing
predate these hackathon changes.

## Confirmed integration baseline

The repository now includes the Nebius Token Factory client. The developer's
earlier local text/JSON smoke tests passed with Nemotron 3 Super. This does not
establish the quality of the new coverage classifier.

## New Phase 2 implementation

- Structured coverage decisions including an unknown/failure state.
- Broader retrieval retry before passage-scoped absence claims.
- Source-aware answers with verified document and unverified background sections.
- Grounded/Intelligence settings, per-answer depth policies and versioned prompts.
- Explicit model-role configuration and per-request cache-usage logs.
- 45 checks including real synthetic slide/PDF OCR, synthetic coverage fixtures and an updated live API collector.
- Conversation continuity for background answers, source-heading recovery, whole-slide reading and visible extraction notices.

## Phase 3 first increment — in progress

- Typed agent decisions and account-scoped document, memory and task tools.
- Durable background runs, short plans/timeline, cancellation and bounded work.
- User-managed typed memories, deduplication, edit/delete and on/off control.
- Depth/example preferences feed subsequent text tutoring, with explicit user
  requests taking priority.
- Study-plan and uploaded-material/web research-brief skills; agent output is clearly
  labelled a draft. It does not inherit the tutor's source-verification badge.
- Study Plan and Today views, account-menu memory controls and source-separated research results.
- Optional Tavily Search with bounded paid attempts, persisted source links and credit reports, cancellation-safe network calls and material-only fallback.

Live Tavily/Nemotron research quality still needs a configured local retest. Sandbox/code execution and agent assessment remain pending. The
summary-length problem is deferred by user direction, not declared resolved.
See [Phase 3 implementation and remaining work](docs/PHASE3_AGENTS_MEMORY.md).

## Not yet demonstrated

Measured production routing, real cache hit rates, live coverage/provenance exit
metrics, human judge calibration, improved ingestion timings, web research,
hosted agent-task quality, reminder jobs, production hosting
and the final submission package. Offline tests are not model benchmarks.

Full details: [Phase 2 implementation](docs/PHASE2_SOURCE_AWARE.md).
Reported-failure fixes: [Follow-ups and slide evidence](docs/TUTOR_RECOVERY.md).
