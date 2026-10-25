# Study workspace v2

The Study workspace now supports larger, source-backed assessments and flashcards, section-based editable notes, saved attempts, dated tasks, and a quieter Progress screen. The cream and terracotta design follows the supplied “B · Tabs and topic heatmap” reference. Example scores, streaks and times from that reference are not copied into learner data.

## Part 1 — Backend changes

### Compatibility and jobs

Existing routes and legacy defaults remain available. In particular, `POST /study/tools` without the new optional `generation` object retains its synchronous 201 artifact response. With `generation: {...}` it creates a durable job internally and returns 202. The new frontend uses the existing `POST /study/generation-jobs` route with `operation: "generate"` and `payload.generation_version: 2`.

The existing `aura_generation_jobs` table is extended rather than introducing a competing job queue. Its `student_id` is the authenticated user identifier; `state` remains available alongside the additive `status` response alias. Responses include `progress: {done, total}`, `items`, `requested`, `delivered`, `result`, `usage`, `usage_complete`, `model_tier`, timestamps and a machine-readable `error_code`. Public assessment items exclude answer keys and per-option explanations until submission.

A transaction lock enforces one active generation job per user. Each checked batch is saved in the same transaction as its progress update. Cancelled or failed jobs retain checked items; they become `partial` when there is saved output. Expired jobs retain their saved output too. A refresh reopens the saved job ID; it does not launch a duplicate request. It does not reconstruct an unfinished model stream following a backend process crash.

### Source planning and generation

Outlines are cached per user/course/content hash using the real slide, page or timestamp groups. The configured coverage tier may refine topic names, but cannot remove source sections or invent references. The documented capacity estimate is three questions or four cards per distinct topic. It is a conservative planning heuristic, not a promise of quality. When a requested count exceeds capacity, the result explains the shortfall and contains only supported, distinct items.

Assessments use batches of up to 10 questions; flashcards use up to 20 cards. At most three batches run concurrently. Allocations interleave topics, materials and types; numerical questions are restricted to materials with detectable numerical content. Unsupported numerical allocation is redistributed with a notice. Material context precedes variable instructions. Provider usage logs record cached tokens; a cache hit is never assumed.

Items pass strict Pydantic validation, deterministic source identity/location checks, a model support check, normalized-text deduplication and embedding cosine deduplication. There are at most two replacement rounds. Top-ups target the remaining type allocations. Invalid or unsupported items are excluded rather than padded to reach a count. Source identity checks establish that citations resolve; the model support check is not independent proof of factual accuracy.

Generation uses existing routing settings: `NEBIUS_COVERAGE_MODEL` for outlines/cards and `NEBIUS_ANSWER_MODEL` for assessments, notes and support checks. Unconfigured roles retain the existing model fallback. No model ID is hard-coded. `AURA_MAX_ANSWER_TOKENS` continues to bound output.

### Question types, attempts, cards and notes

- Multiple choice requires exactly one correct option.
- Multiple select requires four to six distinct options, at least two correct options and a distractor. Default credit is `max(0, (correct_selected - wrong_selected) / total_correct)`; `all_or_nothing` is also supported. Submission returns correct choices and per-option explanations.
- Short answers use deterministic rubric/keyword checks first, then a bounded model check for borderline answers.
- Numerical answers use the existing safe unit/tolerance parser; student input is not executed.
- Attempts have owner checks, optimistic revisions, per-question answers and a hashed resume token. GET sends that token through `X-Aura-Resume-Token`, not a URL parameter. The browser also retains draft answers; a newer saved server revision wins on resume.
- Cards support `term_definition`, `question_answer` and `cloze`. Appending checks ownership and the original material group, deduplicates against the deck, remaps citations and preserves existing card IDs/review dates. New cards get review records. Reviews update due dates and record real activity.
- Notes ignore item count. Source sections generate independently with up to three requests in parallel. Missing sections receive one retry. Structural coverage reports `covered`, `total`, and `missing_sections`. Editing preserves section identity, uses optimistic revision checks, and clearly removes the claim that edited coverage was verified.

### Cancellation and allowances

Study v2 streams Token Factory responses server-side with `httpx`. Cancellation closes the active upstream request as well as stopping later batches. Provider-reported tokens are retained when available. If a cancelled stream does not report terminal usage, `usage_complete` is false; quota accounting conservatively charges the reservation instead of inventing an observed token count. V2 generation never writes agent memories or creates tasks.

Legacy chat/tools retain their existing cooperative cancellation behavior. This update does not claim that every old synchronous model call can be aborted mid-request.

New environment settings in `backend/.env.example`:

| Setting | Default | Meaning |
| --- | --- | --- |
| `MAX_QUESTIONS_PER_REQUEST` | 50 | Reject larger v2 assessment requests |
| `MAX_FLASHCARDS_PER_REQUEST` | 100 | Reject larger v2 card requests |
| `STUDY_DAILY_TOKEN_BUDGET` | 1000000 | Per-user daily generation reservation/usage limit; database-day reset |
| `STUDY_DEDUP_COSINE_THRESHOLD` | 0.93 | Drop semantic duplicates above this similarity |

Over-cap and concurrent-job requests return friendly structured 422/429 errors. Daily allowances are configurable; the defaults are not a statement about hackathon credits.

## Part 2 — Frontend changes

The Materials panel has one upload entry, filename-first rows with menus, a sticky selection bar, rename/archive/remove actions, and a collapse rail that remembers its state. On small screens the open panel becomes a drawer with a visible Hide control and Escape/Tab handling. Removal is deliberately labelled **Delete from workspace**: saved work, originals and citations remain available. Study sets remain account-scoped browser selections.

The Plan screen keeps the current plan and Day cards prominent. Previous plans are collapsed, searchable, filterable, loaded five at a time and archiveable. Saved older runs can be reopened directly by ID. Today adds Yesterday/Today/Tomorrow, a date picker, actual seven-day completion dots and Move to today. Daily brief uses the existing labelled On/Off switch.

Notes replace the count selector with depth, style and include controls. Notes support editing/saving, section coverage, a missing-section list, Markdown download and browser Print / Save PDF. PDF export uses the browser print dialog; no server PDF service or new dependency is added.

Assessments offer counts 1–50, presets, percentage type mix, difficulty, multiple-select scoring, a capacity hint, one-question navigation, answer progress, save/resume and post-submission option explanations. Flashcards offer counts 1–100, card type, reveal, sources, review controls and Generate more to append. Both retain checked partial results and expose Stop/Escape, batch progress and the existing 20-second Keep waiting message.

Progress has Overview/Topics/Quizzes/History tabs, a mastery ring, four facts, a recommended-next card, and a warm topic heatmap with visible percentages and a legend. Values derive from saved evidence. Unknown mastery/quiz average/time display as unmeasured, not zero or example data. Mastery is a course-level estimate; range filters activity and quiz averages. Recorded time covers explicitly timed assessment sessions, not unobserved reading time. Topic and due-card counts are real saved records. All-time history is currently bounded to the most recent 2,000 events from each activity source.

No production dependencies were added. Focus styles, reduced-motion rules and both themes remain available. Authored DOM tests cover interactions and color calculations cover the new text/surface pairs; a live browser/device visual review is still required before a public demo.

## New endpoints and fields

All endpoints require the existing authenticated session. Course, artifact, task, run and material ownership are checked server-side.

| Endpoint | Request / result additions |
| --- | --- |
| `GET /study/capacity` | `course_id`, repeated `material_ids`, `kind`; returns `max_supported`, `reason` |
| `GET /study/generation-metrics` | `course_id`; measured batch summary |
| `GET /study/materials/managed` | `course_id`; excludes workspace-deleted entries and reflects processing |
| `PATCH /study/materials/{id}/name` | `course_id`, `name`; preserves the real extension |
| `POST /study/materials/{id}/delete` | `course_id`; workspace removal, original/citations retained |
| `GET /agents/plans` | `course_id`, `q`, `status`, `limit`, `cursor`; current run separately from previous items |
| `PATCH /agents/runs/{id}/archive` | `course_id`, body `archived`; terminal runs only |
| `GET /agents/tasks/by-date` | `course_id`, `day`; dated tasks plus explicitly labelled unscheduled unfinished tasks |
| `PATCH /agents/tasks/{id}/date` | `course_id`, body `scheduled_for` |
| `GET /agents/tasks/week` | `course_id`, `end`; seven actual completion counts |
| `GET /study/progress/summary` | `course_id`, `range`, optional `timezone_name`; facts, topics, recommendations and grouped activity |
| `PATCH /study/notes/{id}` | `revision`, `sections: [{id, text}]`; updated artifact |
| `POST /study/attempts` | `artifact_id`, `scoring`; attempt and one-time resume token |
| `GET /study/attempts/{id}` | Resume-token header; owner-checked saved attempt |
| `PATCH /study/attempts/{id}` | `resume_token`, `revision`, `answers`, `position` |
| `POST /study/attempts/{id}/submit` | Same draft fields plus `duration_seconds`; server feedback/score |
| `POST /study/decks/{deck}/cards/{card}/review` | `course_id`, `correct`; next due date and interval |

Existing generation job start/read/cancel routes remain unchanged. `/study/capabilities` adds `study_v2: true`. Generation v2 payload fields are `generation_version`, `course_id`, `source_id`, `material_ids`, `kind`, `count`, `focus`, `difficulty`, `type_mix`, `scoring`, `card_type`, `append_to_deck`, `depth`, `style`, and `include`. Most are optional with v2 defaults; legacy requests retain their separate existing defaults. No absent backend field was assumed in the UI.

## Database migrations

`backend/study_v2/schema.sql` is additive and idempotent, run automatically at authenticated-app startup under an advisory lock after the existing schema initialization. It:

- Extends `aura_generation_jobs` with generation settings, counts, progress, error/model metadata, usage counters and `usage_complete`.
- Creates `aura_concept_outlines`, `aura_study_attempts`, `aura_card_reviews`, `aura_study_activity`, `aura_daily_token_budget`, and `aura_generation_metrics`, with owner/history indexes.
- Adds task `scheduled_for`/`completed_at`, run `archived`, and material preference `deleted`.

`backend/agents/schema.sql` also declares its new task/run columns for standalone agent initialization. Existing artifacts/results/materials are preserved. No manual data reset or destructive migration is required. Review timing for old cards remains unmeasured until a review record is created.

## Requirement checklist

| Requirement | Implementation files | Status |
| --- | --- | --- |
| B1 durable jobs, polling shape, one active job | `backend/generation_jobs.py`, `backend/private_app.py`, `backend/study_tools.py`, `backend/study_v2/schema.sql` | Implemented; legacy synchronous default preserved |
| B2 caps, outline/cache/capacity, balanced batches, dedup, citations, routing, partials | `backend/study_v2/contracts.py`, `planning.py`, `engine.py`, `provider.py`, `budget.py`, `backend/.env.example` | Implemented |
| B3 types, scoring, mixes and resumable attempts | `backend/study_v2/contracts.py`, `scoring.py`, `product.py`, `backend/learning.py` | Implemented |
| B4 card types, append and spaced review | `backend/study_v2/contracts.py`, `engine.py`, `product.py`, `schema.sql` | Implemented |
| B5 complete notes, structural coverage, missing-section retry, save/export support | `backend/study_v2/notes.py`, `engine.py`, `product.py`; `src/components/StudyToolV2.tsx` | Implemented; PDF through browser print |
| B6 abort upstream, stop batches, retain usage/partials, no cancelled side effects | `backend/study_v2/provider.py`, `budget.py`, `engine.py`, `notes.py`, `backend/generation_jobs.py` | Implemented for v2 generation |
| B7 plans/date tasks/progress/material ownership and rename | `backend/study_v2/product.py`, `progress.py`, `backend/agents/store.py`, `schema.sql` | Implemented |
| B8 tests and measured generation metrics | `evaluation/check_study_v2_scoring.py`, `check_study_v2_runtime.py`, `check_study_v2_integration.py`, `study_generation_metrics.py`, `phase4.py` | Implemented; no fabricated live metrics |
| F1 single upload, collapsed/drawer panel, sticky selection, menus/rename | `src/components/StudyWorkspace.tsx`, `MaterialPicker.tsx`, `StudyOverview.tsx`, `StudyV2.css` | Implemented |
| F2 current/previous plans, Today dates/dots/move, brief switch | `src/components/AgentPanel.tsx`, `PreviousPlansV2.tsx`, `TodayV2.tsx`, `StudyRhythm.tsx`, `src/services/agentApi.ts` | Implemented |
| F3 notes controls, editing/export and coverage | `src/components/StudyToolV2.tsx`, `StudyV2.css`, `src/services/studyV2Api.ts` | Implemented |
| F4 mixed larger assessments, capacity, navigator/save/resume and partial Stop | `src/components/StudyToolV2.tsx`, `StudyWorkspace.tsx`, `src/services/studyV2Api.ts`, `generationJobs.ts` | Implemented |
| F5 larger typed cards, append/source/capacity/progress | `src/components/StudyToolV2.tsx`, `StudyV2.css`, `src/services/studyV2Api.ts` | Implemented |
| F6 Progress tabs/facts/ring/recommendation/heatmap/history | `src/components/ProgressV2.tsx`, `StudyV2.css`, `src/services/studyV2Api.ts` | Implemented with saved data only |
| F7 AA text contrast/focus/keyboard/mobile/friendly errors | `src/components/StudyV2.css`, `StudyWorkspace.tsx`, `StudyToolV2.tsx`, `src/services/apiClient.ts`, `generationJobs.ts`, frontend tests | Automated checks pass; live visual review pending |

Supporting frontend contracts: `src/services/studyToolsApi.ts` and `generationSupport.ts` preserve old artifacts and capability fallback.

## Tests and validation

New tests exercise every scoring type and multiple-select penalty/clamping; invalid schema and false citation rejection; strict caps; numerical redistribution; text/semantic dedup; bounded top-ups; notes missing-section retry; in-flight HTTP stream cancellation; per-user daily reservations; cached outlines; owner isolation; one-active-job rejection; capacity shortfalls; public key redaction; append/review-date preservation; notes revision conflicts; resumable partial-credit attempts and real progress; plan pagination/archive; dated tasks and seven-day counts; material rename/removal; and the optional asynchronous mode on the existing generation endpoint. Migration SQL is applied twice against the PostgreSQL test engine.

Frontend tests add notes controls/editing, multiple-select navigation/save, cloze reveal/append controls, unmeasured Progress values and measured heatmaps/history, dated tasks and paginated archive behavior. Existing legacy tests remain in place. Color checks cover cream/terracotta text, dark-theme secondary text and all topic tile surfaces.

Run checks from the repository root with the documented test-only PGlite/jsdom setup in the existing CI workflow:

```sh
python -m unittest discover -s evaluation -p 'check_*.py'
node --test tests/frontend/studyPlan.dom.test.mjs tests/frontend/studyPlanModel.test.mjs
python -m evaluation.phase4 --gate
npm run build
```

Batch metrics expose observed schema-valid, citation-valid and duplicate rates, type/difficulty mix adherence, latency and provider-reported token usage. No observations yield null rates, not 100%. `usage_complete` distinguishes incomplete stream accounting. The existing human judge calibration is unchanged and is not declared passed by these synthetic checks. Live hosted-model content quality, cache-hit behavior and browser/device appearance require review on the running app.
