# Study Plan screen redesign

The original redesign changed frontend presentation and behavior only. A separately approved backend provider fix is described in the screenshot follow-up below. No API routes, database fields, request keys, or dependencies in package.json were changed. The internal `Agents` tab identity and saved workspace keys remain compatible; the visible name is **Study Plan**.

## Requirement checklist

| Requirement | Implementation | Status / limits |
| --- | --- | --- |
| A — naming and navigation | `src/components/StudyWorkspace.tsx`, `src/components/AgentPanel.tsx` | Study Plan navigation/title; Plan and Today views; one filename in the Using chip; Change focuses material search; primary action requires a selected, ready material. |
| A — account memory | `src/components/AccountMenu.tsx`, `src/components/MemoryDialog.tsx`, `src/components/AgentPanel.tsx` | Account-menu entry in both Chat and workspace, including mobile. List, add, edit, delete, workspace memory toggle, inline save notice and Undo. **Account-wide toggle needs backend support**; the current switch explicitly says workspace. |
| B — goal-first input | `src/components/AgentPanel.tsx`, `src/components/AgentPanel.css`, `src/components/studyPlanModel.ts` | Native radio outcome cards, three example chips, goal input, collapsed Options, optional time/day constraints and depth, memory permission switch, correct primary labels. Options are natural language in the existing `goal` string, never new JSON keys. Research accurately promises uploaded-material research; web access is not advertised. |
| C — progress | `src/components/AgentPanel.tsx`, `src/components/studyPlanModel.ts` | Re-fetch persisted runs on mount, prefer active work when no saved selection, poll while active, recover after fetch failures, friendly observed-step labels, checkmarks, current-step spinner, cancel, polite live announcements. Unreported current action uses the fallback label; no invented progress percentage. |
| D — results | `src/components/AgentPanel.tsx`, `src/components/studyPlanModel.ts`, `src/components/StudyWorkspace.tsx` | Structured day cards, saved-task checkboxes using exact returned task IDs, observed slide chips, source/topic links into existing tools, safe text-only Markdown/day-heading fallback, markdown download, regenerate, collapsed run metadata. Time shows the student's saved time budget, labelled as such; **backend estimates are unavailable**. Legacy Markdown without task IDs remains readable and does not attach unrelated tasks. |
| E — run states | `src/components/AgentPanel.tsx`, `src/components/studyPlanModel.ts` | Done, stopped early with partial saved content, failed/Retry, cancelled/Start again, queued/running progress, friendly empty state. Make it simpler requests a one-day, 20-minute, quick plan through the same POST contract. Also handles timed out/interrupted runs as stopped early. `PreparationStatus.tsx` and `UploadBatchStatus.tsx` use a simple presentation on this page so raw preparation warnings/errors are also withheld. Internal planning narration is never a result; status/error/tool codes appear only inside Run details. |
| F — recent runs | `src/components/AgentPanel.tsx` | Goal, timestamp, friendly state, reopen, and browser-local removal with Undo. **Permanent server deletion is unavailable** and the UI explicitly says this; active runs cannot be hidden. |
| G — polish and accessibility | `src/components/AgentPanel.css`, `src/components/StudyWorkspace.css`, `src/components/AccountMenu.css`, `src/components/studyPlanModel.ts` | Scoped orange/dark design tokens, deliberate spacing/type scale, tested secondary-text contrast, visible focus, native keyboard controls, responsive stacked materials, reduced motion, actual extension labels, display names and ID fallback. Account menu supports a demo badge, but **auth does not provide a demo flag**, so it is not inferred or fabricated. Layout is implemented but real-browser visual QA remains outstanding (see validation). |
| H — optional Chat entry | `src/components/ChatHome.tsx`, `src/components/ChatHome.css`, `src/App.tsx` | A goal-shaped student message offers Turn this into a study plan. Transfers goal and attached source into the existing workspace. |

## Navigation and persistence

The app still uses `/` and its existing internal tab state. Frontend-only query parameters make tool destinations reloadable:

- `?view=study&tab=Agents&source=7&goal=...` opens Study Plan with an optional goal.
- `?view=study&tab=Flashcards&source=7&topic=...` opens the existing tool with its Focus input filled. `Assessment` and `Summary` work the same way.
- Source selection is checked against the existing owned materials response. A day action uses that plan's original source; if archived or unavailable, the workspace explains how to restore it. It does not generate paid model output just by opening a link.
- Draft goals, options, selected run and hidden recent IDs are browser-local and scoped by account/course. Tasks, run state and memory remain server-owned.
- The Today view is a workspace checklist, not a claim that undated tasks are due today.

## Actual backend data used

No backend fields were invented. The TypeScript run type now describes fields already returned by `public_run` and `plan_result`:

- `state`, `request.goal`, `request.skill`, `source_id`, `created_at`, `started_at`, `updated_at`, `steps`, `tokens_used`, `error_code`.
- `result.text`, `result.verified`, `result.structured_plan.{overview,days}`, `result.task_ids`.
- Day entries: `day`, `title`, `details`, `references`; task records: `id`, `title`, `details`, `done`.
- Document-search observations: `passages[].reference` and `passages[].slide` for explicit slide chips. A reference ID or document page is never guessed to be a slide.
- Completed `study_plan_create` observations: `plan` and `tasks` recover partial content if the run stopped after saving it.
- Completed `memory_write` observations: `id`, `record`, `updated_at`. Undo restores the previous record when a write updated it; otherwise it deletes the new record. Old historical saves do not generate new notifications on page load.

## Backend support still needed

1. **Account-wide memory settings.** Current `/agents/memory/settings` is keyed by course. A global preference must be enforced by the server across workspaces; this redesign does not fake one using browser storage.
2. **Permanent run deletion.** There is no delete route. Recent removal currently hides the run on this browser, with an explicit notice and Undo.
3. **Demo-account flag in authenticated user data.** `/auth/me` returns only student ID, name and email. `AccountMenu` accepts a UI demo flag, but no backend field is assumed or decoded.
4. **Per-day estimated minutes / separate topic list**, if required as authoritative data. The UI uses the existing title for Topics and shows a user-entered time budget or Time not set, never a fabricated estimate.
5. **Run model names and token breakdown**, if judges need them. Only aggregate `tokens_used` is returned; Run details says models are not reported. Duration is derived from existing timestamps.
6. **Task due dates and legacy result/task links**, if Today needs calendar scheduling or old Markdown plans need persistent checkboxes. Modern structured plans already return task IDs.

## Validation

- `npm run build` passes TypeScript and Vite. The two existing decorative SVG path warnings are unchanged.
- `node --test tests/frontend/studyPlanModel.test.mjs`: 11 passing contract/presentation tests, including partial recovery, narration isolation, exact task IDs, Markdown cards, reference integrity, status labels, option serialization, ID hiding and contrast calculations. Requires Node 22.18+ or Node 24 for built-in TypeScript stripping.
- `tests/frontend/studyPlan.dom.test.mjs`: 14 passing DOM interaction regressions using synthetic API responses. Covers the unchanged POST payload, task PATCH persistence, budget recovery, cancel/remount, recent removal/Undo, memory edit/delete/toggle, material switching, source/topic deep links, full-app prefill, Chat goal transfer, edited-draft restoration, material URL persistence, and safe load errors.
- The optional DOM runner uses **jsdom only for testing**, supplied outside the app's package manifest. It is needed to exercise React interactions without a reachable browser. Install into a separate location and set `AURA_UI_TEST_MODULES` to its `node_modules`, or install without saving: `npm install --no-save --package-lock=false jsdom`. Then run `node --test tests/frontend/studyPlan.dom.test.mjs`. The runner uses Vite's existing esbuild and does not need a new app dependency.
- These checks use fixture data, not hosted Nemotron calls. **Real-browser desktop/mobile screenshot QA has not completed:** the cloud browser could not reach the local Vite server, and a local Chromium download failed. No screenshot or live-model success is claimed.

## Screenshot follow-up

The Flashcards screenshot exposed a legacy 503 message naming Ollama and an auth name containing an institutional ID/email. Generation failures now show provider-neutral copy while retaining the material/topic, and the account-name fallback also covers ID prefixes, truncated IDs and email-shaped names. These are presentation changes only.

The initial UI patch did not fix generation. After explicit approval to change the backend, `backend/study_tools.py:model_json` was migrated to the existing authenticated Nebius client. Generation, source verification and short-answer grading now use that shared client with bounded per-call output and separate writing/judge reasoning settings. Existing source checks and API contracts remain in place. See [STUDY_PROVIDER_FIX.md](STUDY_PROVIDER_FIX.md) for validation and local retest steps.
