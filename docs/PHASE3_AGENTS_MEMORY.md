# Phase 3 — agent runtime and editable memory

Status: first usable increment, in progress. The summary-length bug is deferred
at the user's request; neither the Phase 2 live exit checks nor all Phase 3 exit
checks are claimed complete.

## Try it

Pull `main`, restart the backend and frontend, sign in, and open **Study tools →
Agents**. The Memory and Tasks panels live inside this page. No new production
Python or npm dependency is required beyond the existing requirements.

The backend applies `backend/agents/schema.sql` at startup under a migration
lock. It creates new tables without replacing existing study material. Keep the
existing database and `.env`; do not rerun database initialization.

1. Open Memory. Save a preference with text, preferred depth and/or examples.
   Its typed settings feed subsequent text tutor answers in this workspace.
2. Ask an ordinary tutor question. Explicit depth in a request overrides a saved
   preference; “go deeper” also overrides a saved beginner preference.
3. Return to Agents and select Study plan. Example goal: “Create a three-day
   revision plan for this material and save a task for each day.”
4. Watch its short plan and tool timeline, then open Tasks to mark work complete.
5. Try a Research brief from your material, or cancel an active run. Previously
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
- Study-plan and uploaded-material research-brief skills. A brief must consult
  the document tool before finishing. Unknown document references are rejected.
- Five memory types: preference, decision, event, task progress and learner fact.
  Records are isolated by user and workspace, normalized for deduplication,
  editable/deletable and controlled by an on/off setting. At most 100 memories
  are saved per workspace; duplicates update the existing record.
- Typed depth/example preferences feed text tutoring. Arbitrary memory text is
  not interpolated as system instructions or treated as document evidence.
- A minimal Agents/Memory/Tasks UI with persisted run history, progress, cancel,
  task completion and source snippets for reviewing an agent draft.

## Runtime bounds and recovery

Defaults are eight actions/model decisions, 32,000 tokens and 120 execution
seconds. Server bounds are 2–12 actions, 4,000–64,000 tokens and 15–180 seconds.
Queue waiting is separate from execution time. There are at most two active
runs per user and 20 active/queued runs globally.

Before every model call the runtime reserves the prompt's UTF-8 byte count plus
system/wrapper headroom as a conservative token ceiling. Completion output is
capped at 1,536 tokens and the remaining allowance. Afterwards it accounts for
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

Each tool effect and its observation commit together under the run row lock.
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
agent system prompt. No shell, arbitrary HTTP, web-search or code-execution tool
is exposed by this increment. There are no keys in the frontend or tool results.

Agent results are labelled **drafts**, with `verified=false`. Reference-ID
validation proves that a reference was observed; it does not prove every claim
is factually supported. The existing citation-grounded tutor remains a separate
path. Do not present these initial agent drafts as source-verified explanations.

## Still needed for the complete Phase 3

- Tavily web search and its provenance handling.
- Token Factory Sandbox integration and a locked-down execution fallback.
- Agent assessment/quiz generation and code/data-analysis skills.
- “Save as a note” directly from a beyond-material answer.
- Stronger agent-result support checks and live skill/quality evaluation.
- Full exit validation of all skills, cancellation and personalization with the
  actual hosted model. Reminder jobs and polished artifact panels are Phase 4.

The authenticated `/agents/capabilities` endpoint reports only implemented tools
and skills; web, code execution and the assessment agent currently report false.

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
