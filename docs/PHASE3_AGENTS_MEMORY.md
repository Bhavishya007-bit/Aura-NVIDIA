# Phase 3 — agent runtime and editable memory

Status: first usable increment, in progress. The summary-length bug is deferred
at the user's request; neither the Phase 2 live exit checks nor all Phase 3 exit
checks are claimed complete.

## Try it

Pull `main`, restart the backend and frontend, sign in, and open **Study tools →
Study Plan**. Tasks are in **Today**; Memory is in the account menu under **What Aura remembers**. No new production
Python or npm dependency is required beyond the existing requirements.

The backend applies `backend/agents/schema.sql` at startup under a migration
lock. It creates new tables without replacing existing study material. Keep the
existing database and `.env`; do not rerun database initialization.

1. Open What Aura remembers from your account menu. Save a preference with text, preferred depth and/or examples.
   Its typed settings feed subsequent text tutor answers in this workspace.
2. Ask an ordinary tutor question. Explicit depth in a request overrides a saved
   preference; “go deeper” also overrides a saved beginner preference.
3. Return to Study Plan and select Study plan. Example goal: “Create a three-day
   revision plan for this material and save a task for each day.”
4. Watch its progress timeline, then open Today to mark work complete.
5. Try Research a topic. With TAVILY_API_KEY configured, it adds linked web findings. You can also cancel an active run. Previously
   committed tasks remain; cancellation prevents further tool effects.
6. Edit or delete a memory. Turn memory off to stop new tutor personalization and
   subsequent agent memory reads/writes. Turning it off does not erase records or
   information already present in a conversation or earlier run observations.

## Implemented

- Strict, discriminated Pydantic tool actions with validated arguments and
  server-enforced skill allowlists. Model output cannot supply an account ID.
- JSON plan–act–observe–check loop using the existing Nemotron/Token Factory
  client. This is server-dispatched tool calling over JSON decisions, rather
  than reliance on a provider-specific `tool_calls` response format.
- PostgreSQL queue, run request, plan/tool observations, draft result and state.
  Two workers per backend process claim queued jobs atomically with `SKIP LOCKED`.
  The browser polls progress; leaving the page does not cancel a run.
- Document search within the authenticated workspace and optional selected file;
  memory read/write; task list/create. Search uses PostgreSQL full-text ranking,
  returning up to four bounded passages with stable document reference IDs. If
  no query terms match, the introductory results are still samples, not proof
  that the requested topic is covered or absent.
- Study-plan and uploaded-material/web research-brief skills. A brief must consult
  the document tool before finishing. Unknown document references are rejected.
- Five memory types: preference, decision, event, task progress and learner fact.
  Records are isolated by user and workspace, normalized for deduplication,
  editable/deletable and controlled by an on/off setting. At most 100 memories
  are saved per workspace; duplicates update the existing record.
- Typed depth/example preferences feed text tutoring. Arbitrary memory text is
  not interpolated as system instructions or treated as document evidence.
- Study Plan/Today UI with persisted run history, progress, cancel, task completion,
  account-menu memory controls and separate uploaded/web research source sections.

## Runtime bounds and recovery

Defaults are eight actions/model decisions, 32,000 tokens and 120 execution
seconds. Server bounds are 2–12 actions, 4,000–64,000 tokens and 15–180 seconds.
Queue waiting is separate from execution time. There are at most two active
runs per user and 20 active/queued runs globally.

Before every model call the runtime reserves the prompt's UTF-8 byte count plus
system/wrapper headroom as a conservative token ceiling. Completion output is
capped at 1,536 tokens for study plans or 3,072 for research, within the remaining allowance. Afterwards it accounts for
reported input/output usage, falling back to a conservative estimate if usage
is missing. Late usage from an already cancelled/expired call is still visible
in provider logs but may not be added to the run's checkpointed token count;
these counters are not billing records.

Each provider call gets one attempt and a bounded read timeout. One invalid
action can be repaired within the same step/token/time budgets; a second
invalid decision stops the run. Provider/tool errors fail the run with a safe
error code. There is no automatic replay of completed mutations.
Agent SQL has a five-second statement limit and two-second lock limit; database
connections have a ten-second connection timeout. Active runs are listed ahead
of finished history so their cancel controls remain reachable.

Database tool effects and their observations commit together under the run row lock.
Web searches first reserve a bounded attempt, release the transaction during network
I/O, then re-check ownership/state/deadline before committing the observed results.
Cancellation takes the same lock. After cancellation is acknowledged, a late
model response cannot save a new task or memory or mark the run complete.
Already committed effects remain visible. Deadline checks and the dispatcher
stop expired runs; a timeout is committed before refusing a late tool effect.

Queued jobs survive restarts and can be claimed by the next worker. Running
jobs are marked interrupted on orderly shutdown; after a crash they time out
from their original start time. Their recorded progress is retained. They are
not blindly resumed, because that could repeat side effects.

## Authorization and provenance

Every public endpoint requires the existing bearer authentication. The server
checks workspace ownership; selected material must belong to that workspace and
student. Memory, task and run reads/edits carry both owner and workspace filters.
Only the internal dispatcher performs global queue/expiry maintenance.

Memory writes from an agent require the explicit per-run checkbox, an enabled
memory setting, and a typed allowed action. The prompt permits saving only
information the user's goal asks to remember. Study tasks can be created by the
study-plan skill; the research-brief skill has no task-write permission.

Passages and saved memories are labelled untrusted data in observations and the
agent system prompt. Research may use a fixed-endpoint, bounded Tavily Search tool
when configured. No shell, arbitrary HTTP or code-execution tool is exposed. There are no keys in the frontend or tool results.

Agent results are labelled **drafts**, with `verified=false`. Reference-ID
validation proves that a reference was observed; it does not prove every claim
is factually supported. The existing citation-grounded tutor remains a separate
path. Do not present these initial agent drafts as source-verified explanations.

## Still needed for the complete Phase 3

- Token Factory Sandbox integration and a locked-down execution fallback.
- Agent assessment/quiz generation and code/data-analysis skills.
- “Save as a note” directly from a beyond-material answer.
- Stronger agent-result support checks and live skill/quality evaluation.
- Full exit validation of all skills, cancellation and personalization with the
  actual hosted model. Reminder jobs and polished artifact panels are Phase 4.

The authenticated `/agents/capabilities` endpoint reports only implemented tools
and skills; web reports its server-side configuration state. Code execution and the
assessment agent still report false.

## Verification

Run the deterministic loop and optional synthetic PostgreSQL/API tests:

```bash
python -m unittest evaluation.check_agents -v
# Optional: point AURA_PGLITE_MODULE at an installed @electric-sql/pglite package.
# AURA_PGLITE_MODULE=/path/to/package python -m unittest evaluation.check_agents -v
npm run build
```

The PostgreSQL tests use synthetic users/material, exercise actual SQL and API
auth boundaries, and run the real dispatcher with controlled model decisions.
They cover memory dedup/edit/delete/toggle, user isolation, queue claims/caps,
allowed writes, persisted tool observations, cancellation, rollback on checkpoint
failure, deadlines, shutdown and an end-to-end draft/task run. These checks do
not measure hosted-model task success or judge agreement.

Validation for this increment: all 20 new checks pass, including a saved agent
preference affecting the next tutor settings and a real background dispatch
through the API. The broader suite reports 175 tests: 173 passed and two optional
OCR checks skipped. `npm run build` and Python compilation pass. No live hosted
agent run was performed in this environment.

## Follow-up: repeated searches exhausted the first live plan run

The attached screenshot shows six document searches and one rejected action,
with no saved daily plan. The corresponding logs show seven successful provider
calls using 18,646 reported tokens. The old byte-reserve preflight then stopped
another model request. The budget was not proof of an external credit problem;
the runtime had accumulated repetitive context without enforcing progress.

The runtime now keeps completed action/query history and limits document search
to two executions. Case, punctuation and spacing variants of an identical query
are rejected before execution. Memory and task-list reads are limited to one
each. The store enforces read limits under the run lock as well. Repeated
passages are deduplicated by reference ID in the model context, capped at eight
600-character excerpts; the original tool observations remain in saved history.
Only current allowed actions and their reachable JSON-schema definitions are
sent to the model. Validation feedback identifies safe field paths/types or
specific day/reference/duplicate failures without copying model inputs or source
text into logs. One invalid action can be repaired; repeated invalid decisions
still fail closed within the existing action, token and time caps.

A new `study_plan_create` action accepts an overview and 1–14 sequential daily
activities. For an unambiguous requested day count, a multi-day plan must use
this action and match that count. It consults the document tool first. Its
references must have been observed in this run. Ambiguous goals containing
different day counts are not assigned an invented numeric constraint.

The executor saves all daily tasks and their plan observation in one transaction.
A checkpoint failure rolls back the whole batch. Task deduplication for this
action is scoped to the run, so a new plan does not silently inherit completed
tasks from an older plan. The runtime renders the typed plan directly and
finishes without spending another generation call. A cancellation between tool
commit and final checkpoint can still leave the saved plan/tasks visible in
progress while preventing the run from being marked complete. Draft provenance
and all ownership/deadline checks remain in force.

For a three-day goal, the controlled happy path is two model calls: search,
then daily-plan creation. Additional permitted memory or task reads remain
optional, and the runtime reserves its last actions for producing the result.
No default action/token/time budget was raised for this follow-up.

Stopped history is not replayed. After pulling and restarting, start a new run
with the three-day goal; the old exhausted run remains available for inspection.
Live planning quality and provider compliance with the new action schema still
need a hosted retest. This follow-up does not change the deferred summary issue.

Thirteen new controlled regressions cover two-call three-day completion, duplicate
search rejection, a rejected third search followed by a valid plan, compact
schemas/context, field-specific repair, invalid day/reference rejection, late
cancellation, real background API dispatch, and all-or-none task saving. The
full suite reports 188 tests: 186 passed and two optional OCR checks skipped.
The frontend build and Python compilation pass.


## Tavily research increment

Research now reads uploaded material before a bounded Tavily lookup. It persists
actual source URLs and separates uploaded and web findings. Missing configuration,
failed searches and absent usable results have explicit material-only fallbacks.
The feature, API additions, credit limits, validation and setup are documented in
[TAVILY_RESEARCH.md](TAVILY_RESEARCH.md). No database migration or dependency is added.
