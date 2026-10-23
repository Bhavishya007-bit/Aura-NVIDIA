# Phase 4: a clearer tutor and a daily study rhythm

Phase 4 adds readable teaching answers, opt-in daily briefs and spaced review, an evaluation summary, and a CI regression gate. It preserves existing agent/chat/tool payloads and citation rules. Human calibration and the real local demo must still be completed before declaring the phase's quality exit passed.

## Update an existing setup

In PowerShell at the repository root, with your virtual environment active:

```powershell
git pull origin main
python -m pip install tzdata
npm install
uvicorn backend.main:app --reload
```

Start `npm run dev` in your other terminal. Restart the backend after updating. It installs four additive, idempotent study-rhythm tables; existing work stays in place. **Do not run the empty-database initializer against your current database.** New installations continue to use `scripts/init_database.py`, which now includes the rhythm schema.

`tzdata` is the only added production dependency. Python's IANA timezone support needs it on Windows. There are no new frontend production dependencies. PGlite and jsdom below are test-only dependencies.

## Follow-up: readable code lessons and connection failures

The provider's JSON instruction previously said not to include Markdown, which conflicted with teaching instructions. It now requires a bare JSON envelope while explicitly allowing requested formatting inside string values. Code finish schemas describe the answer as the complete lesson: intuition, a worked example explaining why steps work, captured results and limitations. Comparison tables are encouraged, while explicit requests for brevity, plain text, no emojis, language or length take precedence. This uses the existing `finish.answer` field and safe renderer; it adds no model call, dependency or API field. Existing saved text is unchanged; create a fresh run to test the prompt changes.

Connection and timeout exceptions now preserve fixed `model_connection_failed` or `model_timeout` reasons through the agent runtime. The UI gives recovery guidance for every outcome without attributing a model connection problem to Docker. Older `model_or_tool_unavailable` runs retain their original ambiguous reason and receive general service/tool guidance. Unknown code failures no longer assume execution is disabled. Technical codes remain inside collapsed Run details.

If Python completed before the explanation request failed, its captured output and files remain available with a connection notice. A connection failure does not replay code or add automatic model retries; Retry starts a new run using the existing controls. Cancellation still prevents late failures from overwriting the run. Provider exception text, private endpoints, prompts and keys are not copied to run errors or logs.

Controlled tests cover JSON formatting, transport redaction, failure before/after execution, cancellation and UI recovery/rendering. They do **not** measure live teaching accuracy or guarantee that the model follows the requested structure. Retest with the configured model and representative material before marking the remaining Phase 4 quality checks complete. The 2,000-word summary issue remains open.

### Evidence review before publishing code explanations

`backend/agents/code_review.py` now reviews a proposed explanation against the latest executed program, captured stdout/stderr, truncation flags and any retrieved document evidence. Six strict boolean verdicts cover results, traces, counts/timing, assumptions, files and execution status. Program comments and all payload text remain untrusted data; the reviewer has no tools. File metadata is not presented as file contents.

The normal path adds **one model call**. A rejected draft gets at most **one text-only revision and one recheck**, for three additional calls at most. These consume existing credits and stay within the same step/token/time limits; no extra Python execution or tool action is permitted. A running verification step persists across navigation and is labelled **Checking your explanation**. Approved text is still `verified=false`, and the UI says an AI review can miss mistakes.

If the final review rejects, is malformed or unavailable, Aura withholds the explanation and retains real output/downloads with a recovery message. Rejected drafts are not published in result text or saved finish actions. Cancel, expiry and budget stops cannot release a late or unchecked answer. Retry uses the existing new-run behavior; it does not silently replay a sandbox submission.

Controlled checks cover clean review, revision/recheck, repeated rejection, malformed output, truncated model output, cancellation, expiry, token/step limits, downloads after rejection and friendly UI recovery. Two new agent regression cases check repair and withholding, raising the offline gate to **24 cases**. These test the workflow with controlled verdicts, not the live reviewer's ability to detect every error. The reviewer still needs independent human quality assessment; the 30-case coverage-judge calibration below assesses a different task.

### Search explanation regression

A real local answer reported correct counts but invented the path for target 1, claimed timing variability from deterministic counts, implied unique values were required, and described an uninspected JSON file as confirming the results. These remain recorded failures, not a successful teaching evaluation.

`evaluation/fixtures/search_comparison.py` is a fixed authored program using synthetic data. The trusted test guest executes it and captures real per-target loop traces. `search_comparison_expected.json` records the expected paths, the observed explanation failures and a live-review checklist. Tests check indices, counts, interval bounds, branch directions, duplicate behavior and actual saved JSON bytes. They also check that the complete small trace reaches the model context while file bytes remain excluded. No generated model code runs on the test host.

For the lower-midpoint implementation on `[1,3,5,7,9,11,13,15]`:

| Target | Returned index | Linear items | Binary probes | Binary midpoint indices |
| --- | ---: | ---: | ---: | --- |
| 5 | 2 | 3 | 3 | 3 → 1 → 2 |
| 16 | -1 | 8 | 4 | 3 → 5 → 6 → 7 |
| 1 | 0 | 1 | 3 | 3 → 1 → 0 |

Code instructions now ask for traces collected in the actual loop and require the explanation to follow the corresponding target's captured path. Without a captured trace, the answer must acknowledge that limit. Counts are distinguished from measured runtime and primitive comparisons; ordinary duplicate matching is distinguished from finding the first/last match. File metadata cannot establish content inspection. This adds no model requests, automatic replay, API fields or dependencies.

Run the original comparison goal again and apply the fixture's review checklist to the **new live answer**. The authored reference and deterministic tests do not measure the live reviewer's error rate or replace independent human assessment.

## What students see

- Chat, Tutor, notes, summaries, flashcard explanations and agent explanations share a safe Markdown renderer: headings, bold terms, lists, code, tables and quoted text. Source/background labels remain distinct, and existing citation buttons still open the source viewer. Model-written HTML and links are displayed as text, never executed.
- New teaching prompts favor the main idea, small logical steps, a supported example and a takeaway. Substantial answers can use up to three relevant emojis; simple factual answers stay brief. Explicit requests for prose, no emoji, language and length take precedence. Code teaching asks for a worked trace and an explanation of the observed result, rather than merely printing code.
- Existing saved answers retain their text. Ask a fresh question or regenerate a tool result to see the prompt changes. Rendering improves existing Markdown immediately.
- Existing backend clarification and follow-up fields now appear as a question card and clickable suggestion chips. Selecting a suggestion fills and focuses the composer so the student can review it before sending.
- **Overview → Your study rhythm**, also available under **Study Plan → Today**, has a switch, timezone and daily-hour settings, a saved brief and a due-topic list. Practice opens Assessment using that review's original material and topic. “Tomorrow” postpones the reminder; it does not mark anything learned.
- **Progress → Quality & evaluation** shows the controlled regression report, human-review progress and the current student's run counts. Run completion is explicitly not a correctness score.

## Background behavior

Reminders start paused for each workspace. Enabling them permits a backend job to check saved tasks and graded practice every 30 seconds. There are **no email, push, web-search or LLM calls** in the job. Keep Aura's backend running for scheduled work; after downtime it creates today's brief at/after the selected local hour rather than backfilling every missed day. The UI polls once per minute while mounted.

One brief is saved per local calendar day. It is a snapshot; subsequent task checkmarks appear in Today, and “Update due topics” refreshes the live review list. If no brief exists for today, that button also creates one immediately. Briefs older than 30 days are removed during processing; the most recent seven are returned by the API.

A graded quiz/topic counts as one review session, regardless of question count. All answers for that topic must be correct to extend the interval: **1, 3, 7, 14, 30 days**, capped at 30. Any incorrect answer resets it to one day. Reading, opening a page or snoozing never updates mastery. This is a transparent scheduling heuristic, not a validated prediction of retention. Existing grading still owns mastery evidence.

The job processes bounded batches, uses PostgreSQL advisory/row locks, and deduplicates both graded sessions and local-day briefs. All reads/mutations enforce authenticated account and course ownership; practice links retain source ownership. Archived materials do not appear in the due list. Disabling pauses new processing and hides due reminders; saved briefs remain.

## Evaluation: what has actually been measured

`evaluation/reports/phase4.json` records **controlled offline** checks:

| Group | Cases | What is checked |
| --- | ---: | --- |
| Agent tasks | 12 | Real orchestration with controlled model/tool responses: saved task, day plan, research provenance, memory permission, code result/correction, explanation repair/withholding, quiz, cancel, budget stop, unknown citation |
| Injection boundaries | 10 | Rejection of attacker-controlled actions: wrong tool, forged account/course, unauthorized memory, fake citations, extra fields and invented actions |
| Provenance contracts | 2 | No citations in background claims; sourced claims require citations |

These are deterministic server/contract checks, **not live model prompt-injection resistance, teaching accuracy, retrieval recall or learning gains**. The automated gate fails if a group loses cases or its pass rate falls below the committed threshold. Existing source/agent/PostgreSQL/UI regressions also run in CI. No API credits are used in this gate.

### Live coverage-judge calibration — still required

`evaluation/calibration_cases.json` contains 30 synthetic questions with assistant-authored reference labels. These reference labels are **not human judgments** and do not count as calibration.

Collect real outputs only when you explicitly want to spend API credits:

```powershell
python -m evaluation.phase4 --collect-live --model YOUR_EXACT_MODEL_ID
```

This invokes 30 coverage requests through your configured provider. The resulting ignored local file, `evaluation/results/judge_calibration.json`, contains the synthetic passages, questions, actual judge decisions, and empty human labels. No student data is sent by this collector. Each result is checkpointed, and an existing packet is never overwritten; select a new `--packet` path for another collection. Inspect each question, evidence and output, then have a person choose the coverage label independently:

```powershell
python -m evaluation.phase4 --review-case cal-01 --label fully_covered
```

Repeat for all 30 IDs, using `fully_covered`, `partially_covered` or `not_covered` as appropriate. Do not copy reference labels blindly. Then:

```powershell
python -m evaluation.phase4 --gate --require-live
```

Calibration remains untrusted until all 30 actual outputs have human labels, agreement is at least 80%, Cohen's kappa at least 0.60, and false “not covered” predictions on fully/partially covered questions are at most 5%. The report includes a confusion matrix. Thirty simple synthetic cases are limited evidence even after passing; actual slide/diagram retrieval and teaching still need representative manual checks. A schema failure/unknown output blocks readiness.

The default CI command is `--gate`, so offline software checks can pass while live calibration remains visibly pending. Use `--require-live` as the release-quality check after review. A human-reviewed packet stays local unless deliberately shared. The authenticated UI serves aggregates only, never review records or student traces.

### Reproduce the tests

Use Python 3.12 and the existing frontend dependencies. For the optional real PostgreSQL-semantics and DOM checks, install test-only engines outside the app:

```powershell
npm install --prefix .test-deps --no-save @electric-sql/pglite@0.5.11 jsdom@30.1.3
$env:AURA_PGLITE_MODULE = "$PWD/.test-deps/node_modules/@electric-sql/pglite"
$env:AURA_UI_TEST_MODULES = "$PWD/.test-deps/node_modules"
python -m unittest discover -s evaluation -p 'check_*.py'
node --test tests/frontend/studyPlan.dom.test.mjs tests/frontend/studyPlanModel.test.mjs
python -m evaluation.phase4 --gate
npm run build
```

CI installs a smaller test dependency set and stubs external providers; full local runtime setup remains in README. Optional OCR checks require their model assets. No live Docker/provider calls are claimed by these checks.

## Clean-database demo checklist

Use a separate empty demo database and synthetic material, following README initialization. Do not delete your working database.

1. Start the backend/frontend, register a demo learner, and create a course.
2. Upload a small synthetic slide deck; wait for preparation to finish and select it.
3. Ask a supported question, inspect its citation, then ask an unsupported one and confirm the background label. Ask for an example and for plain prose/no emoji to check preferences.
4. Create a study plan. Leave and return during progress; reopen the saved result and check off a task in Today.
5. Generate and submit a source-checked quiz. Confirm that only graded evidence changes the mastery estimate.
6. Enable Your study rhythm and choose a timezone/hour. Create today's brief with Update due topics; refresh the page and confirm it persists. Newly studied topics become due later; do not falsify practice timestamps to imply learning gains.
7. Open Progress → Quality & evaluation. Confirm offline results and pending human calibration are labelled accurately. Pause reminders and check that due items disappear.
8. Log out. Confirm private API reads require login, then use a second account and confirm it cannot read the first account's course, tasks or reminders.

This path is documented and covered in parts by isolated integration/DOM checks; a real uploaded-file/browser demo against your local Windows environment still needs to be run. The previous long-summary target-length issue is not declared solved by this presentation work.

## Files and contracts

| Area | Implementation |
| --- | --- |
| Teaching presentation | `src/components/TeachingText.tsx`, `.css`; `TutorReply.tsx`; ChatHome, StudyWorkspace, AgentPanel and CodeResult integrations |
| Teaching instructions | `backend/agents/runtime.py`, versioned answer/depth/summary prompts, `backend/ai/summary_answer.py`, `backend/study_tools.py` |
| Digests and spaced review | `backend/study_rhythm.py`, `.sql`; `src/services/rhythmApi.ts`; `src/components/StudyRhythm.tsx`, `.css` |
| Evaluation summary | `backend/evaluation_status.py`, `src/components/EvaluationSummary.tsx` |
| Controlled tasks/injection cases/calibration | `evaluation/phase4.py`, `phase4_baseline.json`, `calibration_cases.json`, `check_phase4.py` |
| UI regressions and CI | `tests/frontend/studyPlan.dom.test.mjs`, `.github/workflows/phase4.yml` |

Additive authenticated API endpoints: `GET /study/rhythm`, `PATCH /study/rhythm/settings`, `POST /study/rhythm/refresh`, `POST /study/rhythm/snooze`, `GET /study/evaluation`, each with `course_id`. Settings payload: `{enabled, timezone, daily_hour}`. Snooze payload: `{source_id, topic_key}`. Four additive tables: `aura_study_rhythm_settings`, `aura_review_events`, `aura_review_schedule`, `aura_study_digests`. Existing chat, agents, tasks, memory and study-tool contracts remain intact. Clarification/follow-up rendering consumes fields the chat backend already supplies; no assumed backend fields were invented.
