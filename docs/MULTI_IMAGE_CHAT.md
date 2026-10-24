# Multiple screenshots in one Chat question

Chat previously stored one `uploaded` source and cleared it before every upload.
Preparation callbacks selected only the first job in each batch, and `/chat`
received one source ID. Keeping two file chips alone would therefore not fix a
question whose table/schema and answer options are in separate screenshots.

## Behavior

- Attach up to five JPEG/PNG screenshots, together, one at a time, or by pasting
  screenshots into the question box. Text already typed/pasted is retained.
- Each screenshot has its own ordered attachment slot, readiness state and
  remove control. A failed upload cannot erase a ready screenshot or silently
  submit a partial group. Retry reuses the failed slot and preserves image order.
- Ready attachment metadata and pending preparation job IDs survive refresh in
  the existing account/course-scoped draft storage. Raw image bytes are not
  copied into browser storage. A browser-interrupted upload without a job ID is
  shown as failed instead of pretending to be ready.
- Questions retain a visible snapshot of the screenshot names used. Removing an
  attachment affects the conversation selection; the uploaded material is still
  retained by the existing material system.
- Screenshots are grouped together; documents retain the existing single-active
  material behavior. Switching between a screenshot group and documents requires
  explicitly removing the current attachments. Mixed screenshot/document batches
  are not silently reduced to one file.

## Existing API plus an optional field

`POST /chat` still accepts the existing `source_id` request. It additionally
accepts `source_ids`, at most five distinct positive integer IDs. The primary
`source_id`, when present, must belong to that list. Groups currently support
images only; mixed/document groups return 422. No database fields or routes were
added. Single-image and document requests retain their prior response contracts.

Every attachment must belong to the authenticated student and the selected
course before any image/model work. Missing, foreign and other-course sources
fail the whole request. The backend never answers from only the last accessible
image after another attachment fails ownership/original-file validation.

`backend/multi_image_tutor.py` resolves all owned originals before model calls,
then reads each original in a separate vision request. The reader returns flat
visible facts, including any question/options written in that screenshot; it
does not have to solve a whole problem from one partial image. Each transcription
is checked against that same original. The server assigns image numbers and
source attribution instead of asking the model to invent an image mapping.
Two files both named `image.png` retain their distinct source IDs and order.
If a readable partial image is labelled unanswerable by the reader, its checked
facts can still be combined with the other image. Per-image limitations are kept
for both reasoning and final review; the writer cannot erase those uncertainties.

When all required images can be read, the configured Nebius deep model combines
the server-labelled facts into a solution, with a separate text review of the
derived reasoning. SQL-writing questions use the existing SQL reasoner, including
when the instruction is inside a screenshot and the typed goal is only
`solution`. Other MCQ/calculation questions use `backend/visual_reasoning.py`.
History is supplied as referent context, not source evidence. Reader narration
is not published as the answer. Numeric arrays/indices inside code are not
mistaken for citation markers; source links are added by the server.

An unreadable or rejected transcription identifies the affected `Image N` and
does not silently answer from the other screenshot. Rejected joint reasoning is
withheld. Original-image source records keep each approved transcription separate.
`verified=false` and the visual-interpretation label remain: model consistency
does not establish factual accuracy or human judge calibration.

The frontend checks the returned source IDs against the submitted group. If an
older backend ignores `source_ids` and returns only one screenshot, Chat shows an
error and retains the group for retry instead of showing that as a joint answer.

## Solve the question, not just describe the image

Single-image chat, the figure viewer and grouped-image chat share the task and
review policy in `backend/visual_tasks.py`. When asked to write SQL, Aura should
derive a query from readable schema identifiers, keys and written requirements,
then explain it briefly. The query itself does not need to appear in the picture.
Writing a query does not require data rows; predicting its output can require
them. Review permits valid derivations while checking names, join/role keys,
filters and requested output column order. It does not execute SQL.

Explicit SQL-authoring requests use separate reading and reasoning stages:

1. The configured vision model reads table/column names, key relationships and
   genuine unreadable details. It is not required to write the SQL.
2. `backend/visual_sql.py` sends the recognized facts and written question to
   Aura's configured Nebius `deep` model. It excludes the vision reader's free-form
   narration. The model returns a dedicated `query` field and brief explanation;
   the server renders that query as a SQL code block. Originals are sent only to
   the configured vision endpoint; the text reasoner receives recognized facts.
3. A single-image request retains the original-image solution review. Grouped
   requests check each transcription against its own original, then review the
   joint solution against all transcribed evidence. A failed review withholds
   the solution. Ownership and per-image attribution remain enforced.

The text model is selected through existing `NEBIUS_DEEP_MODEL`/`NEBIUS_MODEL`
configuration, including the existing Ultra quality profile when applied. It
uses the configured writing reasoning controls, a 4096-token output budget, and
at most one repair for incomplete/invalid SQL output. It has no execution tool
or database access and does not claim to have run the query. Connection failures
do not silently downgrade to the local vision model. Genuine missing identifiers
or join endpoints can still produce a specific clarification.

SQL statement detection accepts plain SQL and common Markdown fences. Missing
backticks alone no longer causes `task_incomplete`. Detection is not a SQL parser
or a correctness guarantee; visual reading and model review remain fallible.

## Response-format recovery

The vision endpoint receives each Pydantic JSON schema in Ollama's `format`
field, as well as in the prompt. Plain `format: "json"` guarantees neither the
required answer fields nor their types. The single-image answer requires an
actual boolean `answerable`, a string explanation, and string lists for visible
observations and limitations. Each grouped-image reader also returns flat
observation strings; the server assembles the numbered group objects. The review
response requires a boolean `supported`.
See [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs).

`backend/vision_contracts.py` validates these outputs and performs at most one
revision for malformed/truncated JSON, missing fields or wrong types. SQL reading
does not use a query-completion gate; the separate text reasoner handles query
completion. Review also permits one response-format repair. Missing booleans/evidence are never
invented, and string booleans are not coerced into approval. Repeated malformed
output is withheld; transport/authentication failures are not retried as schema
errors. Existing ownership and attribution checks still apply to all originals.

Safe backend warnings identify the stage (`single_image_read`, `multi_image_read_N`,
non-SQL answer, or review), attempt, failure code and failing field paths
and types. They omit prompts, images, raw model responses, validation input and
unknown field names. `vision_request=failed` separately records transport error
type and HTTP status when available. After pulling, restart the backend and
retry the same selected material; re-uploading is not required.
For SQL requests expect `visual_sql=started route=deep`, the ordinary Nebius
usage log with `task=deep`, then `visual_sql=completed`. Text-model errors have
separate `visual_sql=invalid`/`visual_sql=unavailable` diagnostics.
Grouped requests also log `multi_image_read=started image=N total=M`, rejected
transcription indices, and `multi_image_reasoning=started`. Text-generation and
review failures identify their stage without logging private image/question data.

`evaluation.check_visual_solving` replays the reported schema-only response for
one and multiple images, checks bounded revision and withholding, and preserves
real missing-evidence handling. Its four-table schema, images and SQL are authored
fixtures. Only the static fixture query is run against an in-memory test database;
no student SQL or model output is executed in production or in these checks.
`evaluation.check_visual_sql` covers plain/fenced SQL, the configured text-model
handoff, evidence-only payloads, reading/reasoning/review order, missing evidence,
bounded text repairs, negative review, provider failure and instruction isolation.
`evaluation.check_multi_image_reasoning` covers a short `solution` goal, a question
inside the second screenshot, duplicate filenames, exact server-owned attribution,
unreadable/rejected individual images, bounded joint-answer repair, negative
reasoning review, provider failure, history isolation and numeric code arrays.

## Configuration and bounds

The existing `OLLAMA_VISION_MODEL` and `OLLAMA_BASE_URL` settings are reused.
Existing Nemotron/Token Factory configuration is reused for SQL reasoning. No new credentials
or runtime dependencies are required. The Ollama REST chat request uses its
documented base64 `images` array; see
[Ollama vision](https://docs.ollama.com/capabilities/vision) and
[chat API](https://docs.ollama.com/api/chat).

There are at most five originals, existing per-image pixel limits, and a 24 MiB
aggregate PNG limit for multi-image model calls. Requests keep the existing
300-second vision read timeout, bounded generation/review output and a bounded
context window. Missing or incompatible local vision configuration returns a
recoverable error; it does not silently fall back to OCR of only one screenshot.

Pull the update and restart **both** FastAPI and Vite. For a clean local test,
remove the previously selected attachment, paste an MCQ question, attach its
first screenshot, then attach the second. Confirm both chips remain before
sending. Test refresh and individual removal as well.

## Validation

`evaluation.check_multi_image_chat` exercises ordered original-image transport,
per-image attribution, malformed output, failed visual review, backward-compatible
single-source request validation, and actual PostgreSQL/API authorization across
accounts/courses. The frontend DOM suite covers sequential and batch uploads,
pending/ready refresh recovery, failed upload removal/retry, pasted images, legacy
single-image drafts and older-backend detection. Fixtures are independently
authored; no private screenshot or hosted/local model request is used in tests.
Live recognition quality and real-browser visual QA remain separate checks.
`evaluation.check_vision_contracts` exercises schema serialization, missing/wrong
fields, bounded recovery, malformed/truncated JSON, review rejection, transport
classification, grouped-image retention and content-free diagnostics. These
checks use authored fixtures and mocked HTTP responses, not a live vision model.
