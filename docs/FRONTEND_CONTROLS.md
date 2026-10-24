# Generation and material controls

Frontend and additive backend implementation. Existing API routes remain available and single-material callers remain supported.

| Requirement | Implementation |
| --- | --- |
| Stop / Esc, AbortController, late-response protection | src/hooks/useGeneration.ts; src/components/ChatHome.tsx; src/components/StudyWorkspace.tsx; src/components/TutorCheck.tsx |
| Partial streamed chat text, Stopped label, edit and resend | src/services/apiClient.ts; ChatHome.tsx; StudyWorkspace.tsx |
| Agent cancellation, retained saved results | src/components/AgentPanel.tsx; src/services/agentApi.ts |
| 20-second notice, Keep waiting, announcements | src/components/GenerationStatus.tsx |
| Checkboxes, select all, counter, readiness, five-material limit | src/components/MaterialPicker.tsx |
| Removable Using chips, Chat and study workspace | MaterialPicker.tsx; ChatHome.tsx; StudyWorkspace.tsx |
| Study set create, rename, delete, one-tap selection | MaterialPicker.tsx; account/course-scoped browser storage |
| Material arrays and legacy compatibility | src/services/studyApi.ts; studyToolsApi.ts; agentApi.ts; generationSupport.ts |
| Filename and location citation labels | src/services/citationDisplay.ts; src/types/study.ts; StudyWorkspace.tsx |
| Session and run selection snapshots | ChatHome.tsx; StudyWorkspace.tsx; AgentPanel.tsx |
| Styled menus, item count buttons, focus and reduced motion | ChoiceSelect.tsx; StudyControls.css |
| Screenshot coding task completion policy | backend/visual_reasoning.py |

## Implemented backend contracts

- `GET /study/capabilities` advertises `multi_chat`, `multi_study`, `multi_agents`, and `study_jobs`. Older servers fall back to their existing routes and one document at a time; the existing multiple-screenshot path remains usable.
- `POST /chat`, `POST /study/tools`, and `POST /agents/runs` accept additive `material_ids`, a maximum of five distinct positive IDs. Keep `source_id` as the primary selected material for legacy callers. Every selected material is checked for owner, course and readiness. No unselected source is included in group retrieval.
- Artifacts record `payload.material_ids`, agents record `request.material_ids`, and `/study/artifacts` accepts repeated `material_ids` query parameters for exact-group filtering. Existing artifacts without that field remain readable.
- `POST /study/generation-jobs` accepts `{course_id, operation, payload}`. Operations are `chat`, `generate` (existing tool request), and `grade` (existing assessment answers plus `artifact_id`). The authenticated server saves the validated request and queues it.
- `GET /study/generation-jobs/{id}?course_id=...` returns `id`, `course_id`, `operation`, `state`, `result`, and `created_at`. States: queued, running, completed, cancelled, failed. Reads and cancellation require the owning account and course.
- `POST /study/generation-jobs/{id}/cancel?course_id=...` acknowledges durable cancellation. Model calls have cooperative checks before/after the provider request; study artifact and assessment/mastery writes recheck cancellation in the save transaction. Cancelled jobs cannot later become completed. An already in-flight provider request can still finish and consume tokens; its cancelled output is discarded.
- Existing `POST /agents/runs/{id}/cancel?course_id=...` remains unchanged. Saved partial plan/code results remain available.
- The new `aura_generation_jobs` table and index are created idempotently at application startup. No existing table columns are changed. Two workers per application process, global queue capacity 20, and at most two active generation jobs per user. Queued/running jobs expire after ten minutes. Interrupted running work is not replayed automatically; a reconnect can read it until expiry or retry after failure.
- Study sets remain browser-local and account/course-scoped. Cross-device set synchronization is not implemented. Per-run material snapshots are saved by the backend; local snapshots also support old run records.

## Streaming and partial-result limits

The existing model calls return complete JSON. The saved-job path therefore shows progress and supports real cancellation, but does not pretend that token text has already arrived. Previously received text and existing saved artifacts/checkpoints remain visible. A provider response that never arrived cannot supply partial answer text.

The chat transport also accepts an additive SSE response: `event: delta` with JSON `{"text":"increment"}`, then `event: result` with the complete existing chat DTO. Abort retains received deltas as Stopped with no invented citations. This transport is tested; the current backend does not emit token-stream SSE. No answer-verification or provenance check is bypassed to create partial output.

## Validation

Frontend interaction checks cover legacy routes, stop/Esc, late-response suppression, server cancellation, saved-job recovery without duplicate creation, material limits/readiness, study sets, menus and streamed partial text. Backend checks use synthetic PostgreSQL data for group ownership, validation, durable cancellation and cancellation during active work. Live provider quality and the user's original screenshots still need a local retry.

No new runtime dependencies were added. Test-only jsdom and PostgreSQL test engines are installed outside the repository. The complete requirement mapping is the table above; backend implementation lives in `backend/material_groups.py`, `backend/generation_jobs.py`, `backend/private_app.py`, `backend/study_tools.py`, and `backend/agents/`.
