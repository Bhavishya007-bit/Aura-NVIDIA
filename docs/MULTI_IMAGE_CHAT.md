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

`backend/multi_image_tutor.py` loads each owned original separately and passes the
ordered image array and exact pasted question to the existing local vision
endpoint. The generation schema requires visible observations attributed to
each image. A second model call checks the joint answer against the same ordered
originals; rejected output is withheld. Original-image source records keep
per-image observations separate. `verified=false` and the visual-interpretation
label remain: model consistency does not establish factual accuracy.

The frontend checks the returned source IDs against the submitted group. If an
older backend ignores `source_ids` and returns only one screenshot, Chat shows an
error and retains the group for retry instead of showing that as a joint answer.

## Configuration and bounds

The existing `OLLAMA_VISION_MODEL` and `OLLAMA_BASE_URL` settings are reused.
Nemotron/Token Factory text-model configuration is unchanged. No new credentials
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
