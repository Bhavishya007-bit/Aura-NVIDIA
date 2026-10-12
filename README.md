# Aura

Aura is a React + TypeScript + Vite study companion. Its upload page can send PDF, PPTX, DOCX, and MP4 files to a small FastAPI prototype. The API stores the original in local disk storage and calls the existing `ingestion` package.

## Run the frontend

In one terminal, from the project root:

```bash
npm install
cp .env.example .env.local
npm run dev
```

On Windows PowerShell, use `Copy-Item .env.example .env.local` instead of `cp`. The frontend defaults to `http://127.0.0.1:8000` when `VITE_API_BASE_URL` is not set.

## Run the API

Use Python 3.10 or newer. In a second terminal at the project root:

```bash
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS/Linux
source .venv/bin/activate
```

Install the API, upload, and extraction dependencies, then start FastAPI:

```bash
python -m pip install -r requirements-api.txt
uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

The API health check is `http://127.0.0.1:8000/health`; interactive endpoint docs are at `http://127.0.0.1:8000/docs`.

Optional API environment variables:

```powershell
$env:FIELDNOTE_STORAGE_DIR = 'backend/.local_storage'
$env:FIELDNOTE_CORS_ORIGINS = 'http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173'
```

`FIELDNOTE_CORS_ORIGINS` is a comma-separated exact-origin allowlist. Set it in the API host to include the deployed frontend origin. Set `VITE_API_BASE_URL` to the separately hosted API URL before building/deploying the frontend. Vercel currently hosts only the frontend; it does not host this FastAPI service.

## Upload API contract

`POST /courses/{course_id}/sources` accepts `multipart/form-data` with one field named `file`. The route validates the filename extension, the 100 MiB size cap, and the file container signature. It stores the original file under a generated ID (the client's filename is metadata only), creates a source record through a repository interface, and passes the bytes to `ingestion.ingest_file`.

Successful source creation returns HTTP `201` with a JSON response like:

```json
{
  "source_id": "a generated UUID",
  "course_id": "foundations-of-biology",
  "filename": "chapter-4.pdf",
  "file_type": "pdf",
  "upload_status": "uploaded",
  "processing_status": "success",
  "content_unit_count": 12,
  "warnings": [],
  "created_at": "2026-10-02T00:00:00Z"
}
```

`processing_status` mirrors the existing extraction result: `success`, `partial`, `empty`, `not_configured`, or `error`. A supported file can be stored even if its extraction fails; in that case the response is still `201`, has `processing_status: "error"`, and includes warnings. Invalid extensions return `415`, files over the cap return `413`, and invalid/corrupt container signatures return `422`, each with FastAPI's JSON `detail` message. Storage failures return `500`.

The upload runs synchronously in this prototype. The response includes the number of extracted content units and warnings, not the extracted text. The content units are currently transient; no database or durable extraction-result store has been selected.

## Frontend API integration boundary

The frontend authentication API contract, for when it is connected, is:

- `POST /auth/register` with `{ "full_name": "...", "email": "...", "password": "..." }`; return a JSON object on success.
- `POST /auth/login` with `{ "email": "...", "password": "..." }`; return `{ "access_token": "..." }`.
- `GET /auth/me` with `Authorization: Bearer <access_token>`; return `{ "id": "...", "full_name": "...", "email": "..." }`.

The current login and sign-up pages are a frontend-only demo: the dashboard remains accessible before sign-in, and either form returns to the dashboard after validating its required fields. Demo sign-in does not verify credentials or call the API; the username is used as the dashboard display name, while passwords are never persisted. The API authentication endpoints still need to be implemented and connected before real accounts or credential verification are available. `src/services/authApi.ts` contains the existing API client functions for that integration.

React components call service functions in `src/services/`; HTTP transport, the `VITE_API_BASE_URL`, bearer-token injection, HTTP errors, and response decoding are centralized in `src/services/apiClient.ts` and `src/services/studyApi.ts`. The current FastAPI contract only implements source upload, so course/material reads, tutor, notes, summaries, flashcards, quiz generation/submission, and learner insights have typed service interfaces but intentionally make no requests until their endpoint contracts are agreed. Add endpoint paths and wire-format mappers in the service layer only; do not add database or AI-service access to the frontend.

The upload path and snake_case response mapper are implemented against the documented FastAPI route. UI code receives a camelCase result. The authentication client can supply the existing `setApiAuthTokenProvider` hook from an access token held in `sessionStorage` when real authentication is connected; passwords are never persisted. Existing study samples stay in the demo data adapter. Tutor fallback copy is explicitly marked demo, contains no generated answer, and carries no fabricated citation.

The main Quizzes navigation opens the assessment center, separate from contextual practice in AI Tutor. `studyApi.ts` exports typed `generateQuiz` and `submitQuizAnswers` service contracts with assessment scope, material/topic IDs, answer submissions, overall results, and topic performance. These calls intentionally remain unconfigured until FastAPI endpoint paths and payloads are agreed. The assessment page only uses the existing static sample question as a one-question demo when it matches the selected scope; it does not generate questions or fabricate assessment coverage/results.

## Tests

After installing `requirements-api.txt`, run all extraction and API tests from the project root:

```bash
python -m unittest discover -s tests -v
```

The existing `npm run test:upload` checks browser-side file selection and limits. `npm run build` checks the frontend TypeScript and production bundle.

## What is implemented and what remains

- **Implemented prototype:** FastAPI health route and upload route; PDF/PPTX/DOCX/MP4 extension, size, and signature validation; generated source IDs; local original-file storage; replaceable repository and storage interfaces; synchronous invocation of the existing ingestion package; frontend uploading/result/error states. The frontend prevents another batch submission while one is in progress.
- **PDF/PPTX/DOCX:** Uses the existing page/slide/paragraph extraction and shared content-unit schema. Extracted text is not persisted yet.
- **MP4:** The existing pipeline returns `not_configured` without a selected transcription adapter; no transcript is fabricated.
- **Images:** Not accepted by the current upload endpoint. `ingestion/extractors/image.py` only defines an adapter protocol; OCR/image understanding is not implemented.
- **Temporary:** Source metadata uses an in-memory repository and disappears when the API restarts. Original files stay on local disk under `FIELDNOTE_STORAGE_DIR`. The API has no authentication, authorization, malware scanning, background job system, or production-grade storage.
- **Not included:** PostgreSQL/pgvector, RAG, embeddings, quiz generation, learner modeling, or OCR.

## Team decisions before production integration

1. Member 2 should provide the agreed course/source schema, ownership/auth rules, repository transaction behavior, and durable file-storage choice. Replace `InMemorySourceRepository` and `LocalFileStorage` without changing the route's service boundary.
2. Member 3 should confirm the ingestion JSON-to-KnowledgeUnit mapping and whether/where extracted units are stored. The current extraction output remains unchanged.
3. The team should choose authentication, upload retention/deletion rules, hosted backend URL, allowed CORS origins, maximum request size, and a video transcription provider. Production secrets belong in the hosting provider's environment settings, not frontend code.
4. Course IDs in the frontend are demo slugs. Replace them with IDs from the agreed course API/schema before connecting real accounts.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the team's suggested branch and pull-request workflow. Keep frontend, API, ingestion, and future database/AI work in their existing modules. Agree on API and data contracts before changing shared response or content-unit shapes.
