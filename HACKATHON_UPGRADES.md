
# Aura hackathon upgrades

## Preserved base

Authentication, private workspaces, multimodal document ingestion, pgvector
retrieval, citation checking, assessments, learner estimates and source viewing
predate this Phase 2 change.

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
- 27 offline regressions, synthetic coverage fixtures and an updated live API collector.

## Not yet demonstrated

Measured production routing, real cache hit rates, live coverage/provenance exit
metrics, human judge calibration, improved ingestion timings, web research,
tool execution, agent loops, persistent memory, reminders, production hosting
and the final submission package. Offline tests are not model benchmarks.

Full details: [Phase 2 implementation](docs/PHASE2_SOURCE_AWARE.md).
