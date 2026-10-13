# Aura — a source-based study tutor

Aura runs on the evaluator's own laptop. No hosted website, paid API key, or
cloud database is required. The frontend is React/TypeScript, the API is FastAPI,
the database is PostgreSQL with pgvector, and generation runs through local
Ollama. Internet is needed initially to install software and download models.

## What to try

1. Create an account and sign in. A new account starts with its own materials.
2. Open the study workspace and upload a small text-based PDF or PPTX.
3. Wait until it is ready. Ask **“What is this material about?”** for an overview,
   then ask a specific question supported by the document.
4. Use Notes, Summary, Flashcards, or Assessment on the selected material.
5. Submit an assessment and open Progress to see scores, topic counts and history.
6. Refresh to check saved work. Create another account to check material isolation.

In Tutor, **Enter sends** and **Shift+Enter adds a line**. Messages scroll above
the composer. Guest access supports general questions; uploaded material and
study tools require an account. Source-backed claims show citations and source
excerpts with page, slide or timestamp metadata. General background is explicitly
labelled as unverified against the uploaded material.

## Prerequisites

Install these before starting:

| Software | Use |
| --- | --- |
| [Python 3.12](https://www.python.org/downloads/) | Backend and local AI packages |
| [Node.js 22 LTS](https://nodejs.org/en/download) | Frontend; Node 22.18+ recommended for the test command |
| [Git](https://git-scm.com/downloads) | Clone the repository |
| [Ollama](https://ollama.com/download) | Run the local tutor model |
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) or an existing PostgreSQL + pgvector installation | Database |
| [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/) | Convert legacy `.ppt` and render original PPT/PPTX slide previews; PDF/media previews work without it |

A practical demo laptop should have about **16 GB RAM** and several GB of free
disk space for models, dependencies and Docker. This is a planning estimate,
not a measured minimum. CPU and NVIDIA CUDA embeddings are supported. CPU processing can take several
minutes for a large presentation; use a short material for the first demo.

The instructions below use **Windows PowerShell** from the repository root.

## 1. Get the code

```powershell
git clone https://github.com/Bhavishya007-bit/aura.git
cd aura
py -3.12 -m venv .venv
```

If you received a ZIP, extract it and open a terminal in the folder containing
`package.json` and `backend`, then create `.venv` there. The repository must
contain this revised package before the clone instructions reproduce it.

Use the virtual environment's executable directly; activation is optional.

## 2. Create local configuration

```powershell
.\.venv\Scripts\python.exe scripts/create_local_config.py
```

This creates `backend/.env` with a random local database password and JWT secret,
and `.env.local` with `VITE_API_BASE_URL=/api`. Existing configuration files are
preserved. Real `.env` files are ignored by Git; the `.env.example` files contain
placeholders only. Do not commit the generated credentials.

## 3. Install dependencies and choose CPU or GPU

A GPU is optional. Both modes use **Qwen/Qwen3-Embedding-0.6B in FP32**.
CPU mode supports laptops without a compatible NVIDIA GPU. It can take longer;
this choice does not substitute a smaller embedding model. Floating-point
results can differ slightly between devices.

First update pip:

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
```

### Option A: CPU — works without an NVIDIA GPU

For a new virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install "torch>=2.2,<3" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe scripts/configure_embeddings.py --device cpu
```

### Option B: NVIDIA GPU — CUDA

Install a compatible NVIDIA driver. At the [official PyTorch installation
selector](https://pytorch.org/get-started/locally/), choose Windows, Pip, Python,
and a CUDA build compatible with your hardware and driver. Run its command
using `.\.venv\Scripts\python.exe -m pip` in place of `pip3` or `pip`.
Aura needs torch; torchvision and torchaudio are not required by this backend.
Use a torch version satisfying `torch>=2.2,<3`.

If replacing CPU-only PyTorch, stop the backend and reinstall torch from the
chosen CUDA index with `--upgrade --force-reinstall`. Do not run the CPU
installation command on an already working GPU environment.

Then:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -c "import torch; print('PyTorch:', torch.__version__); print('CUDA build:', torch.version.cuda); print('CUDA available:', torch.cuda.is_available())"
.\.venv\Scripts\python.exe scripts/configure_embeddings.py --device cuda
```

`CUDA available` must be `True`. Explicit `cuda` mode reports an error when
CUDA is unavailable instead of silently choosing CPU.

For a 4 GB GPU, start with batch size 1 before warming up the model:

```powershell
.\.venv\Scripts\python.exe -c "from dotenv import set_key; set_key('backend/.env', 'AURA_EMBEDDING_BATCH_SIZE', '1')"
```

Batch size controls how many chunks are encoded together. It does not change
the model or precision. Available VRAM also depends on other applications;
full-precision Qwen may not fit on every GPU. If batch size 1 still fails with
an out-of-memory error, choose CPU or use a GPU with more available memory.

### Auto selection or interactive choice

```powershell
.\.venv\Scripts\python.exe scripts/configure_embeddings.py
```

The menu offers Auto, NVIDIA GPU (CUDA), and CPU. Alternatively:

```powershell
.\.venv\Scripts\python.exe scripts/configure_embeddings.py --device auto
```

Auto selects CUDA when `torch.cuda.is_available()` is true; otherwise it uses
CPU. It does not guarantee that the model fits in GPU memory. Restart the
backend after changing the device. Existing database and authentication
configuration is preserved. This choice controls embeddings; OCR remains on
CPU and Ollama manages the tutor model separately.

### Complete the shared setup

```powershell
.\.venv\Scripts\python.exe -m pip check
npm ci
ollama pull qwen2.5:3b
```

One root `requirements.txt` contains all backend dependencies. Install the
selected PyTorch build first; installing requirements without `--upgrade`
keeps a compatible installed build. On macOS install torch from PyPI and
select CPU. On Linux use the matching PyTorch selector and `.venv/bin/python`.

Keep Ollama running. If needed, run `ollama serve` in another terminal. If its
port is already occupied, the service may already be running.

### Gemma 3 4B — required for figure interpretation

Ollama runs the local models. The existing `qwen2.5:3b` model handles text
tutoring; **Gemma 3 4B** is the separate image-capable model used for figures,
diagrams and optional visual interpretation of new JPEG/PNG materials.
Gemma reads images and generates text explanations; it does not generate images.

Install and configure it from the repository root:

```powershell
ollama pull gemma3:4b
powershell -ExecutionPolicy Bypass -File scripts/configure_vision.ps1 -Model "gemma3:4b"
```

The configuration script sets `OLLAMA_VISION_MODEL=gemma3:4b` in the existing
`backend/.env` and backs up the previous file. It preserves the text model,
embedding settings and database credentials. Restart the backend after changing
this setting. Use a version of Ollama supporting Gemma 3 (0.6 or later).

To try it, click a citation, open its original page/slide/image, and expand
**Explain this figure or diagram**. Ask about visible arrows, labels or axes.
Gemma runs for this action and optional image-upload interpretation; it does
not automatically replace the ordinary text tutor. Text-based features can run
without configuring the vision model. Images without readable OCR text may need
vision configuration and a preparation retry to become searchable.

CPU inference is possible but can be slow. Ollama manages model placement
separately from the embedding device configuration. Visual interpretation uses
two model calls and can take several minutes. Small labels, dense diagrams and
model interpretations require comparison with the original image.

## 4. Start a fresh database — choose ONE option

### Option A: Docker database (recommended for a new judge laptop)

Start Docker Desktop, then:

```powershell
docker compose --env-file backend/.env up -d --wait db
.\.venv\Scripts\python.exe scripts/init_database.py
```

Only the database is containerized. It uses the official
[pgvector PostgreSQL image](https://github.com/pgvector/pgvector#docker), binds
locally, and defaults to host port **5433** to avoid an existing PostgreSQL on
5432. The named Docker volume keeps database data between restarts.

`init_database.py` creates the base schema plus authentication, private workspace,
study tool, archive-preference and learner-evidence tables in one transaction. It refuses to
initialize a nonempty database and does not delete existing records.

For later sessions, start the same database container; do not initialize again.
Do not recreate `backend/.env` with a different password while keeping the
existing database volume: its stored database password remains unchanged.

### Option B: Existing native PostgreSQL with pgvector

Create a NEW empty database named `aura` in pgAdmin. The pgvector extension
package must already be installed on that PostgreSQL server; plain PostgreSQL
alone is insufficient. See the [official installation instructions](https://github.com/pgvector/pgvector#installation).

Edit `backend/.env` to use your actual database name, user, password and port
(usually 5432), then run:

```powershell
.\.venv\Scripts\python.exe scripts/init_database.py
```

If updating an existing working Aura installation, **keep its configuration and
database**. Do not run initialization. Earlier installations already applied
`auth-migration.sql`, `backend/private_workspaces.sql`, `backend/study_tools.sql`
and `backend/material_preferences.sql`; only apply a missing migration after
checking its state. Do not run legacy attribution or seed scripts for a fresh
judge account. They are manual maintenance tools, not setup requirements.

## 5. Check setup and preload embeddings

```powershell
.\.venv\Scripts\python.exe scripts/check_local_setup.py
.\.venv\Scripts\python.exe -c "from backend.ai.embeddings import get_embedding_model; m=get_embedding_model(); v=m.embed_query('Test embeddings'); print('Device:', m.device); print('Dimensions:', v.shape[-1])"
```

The check reports missing Python modules, schema columns or the Ollama model.
Preloading embeddings downloads/caches the Qwen model before the demonstration.
The first audio/video upload also downloads Whisper `base`. Subsequent runs use
cached weights. Expected dimensions: 1024. Device should match your selection. Warm-up verifies
that the model can load and encode on the selected device. It does not measure
full-document processing time.

The database stores **1024-dimensional** vectors. Keep the supplied embedding
model for this setup; switching to a model with a different dimension requires
a separate database/index migration and reindexing.

## 6. Run Aura — two terminals

Terminal 1, from the repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Terminal 2, also from the root:

```powershell
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open **http://127.0.0.1:5173**. The `/api` proxy forwards frontend requests to
127.0.0.1:8000. API health: http://127.0.0.1:8000/health; API docs:
http://127.0.0.1:8000/docs. Documentation describes the private API exposed by
`backend.main:app`, not every older function still present in `main.py`.

For a production frontend build running locally:

```powershell
npm run build
npm run preview
```

Stop the development server before previewing; both use 5173. The backend,
Ollama and database must remain running while Aura is used.

### macOS/Linux command equivalents

Use `python3.12 -m venv .venv`, then `.venv/bin/python` wherever the Windows
instructions use `.\.venv\Scripts\python.exe`. Docker and npm commands remain
the same. LibreOffice must be discoverable as `soffice`/`libreoffice` for `.ppt`.
The executable has been automatically detected on Windows in the standard
LibreOffice installation paths; `LIBREOFFICE_PATH` can override it.

## Supported materials and practical limits

- PDF, PPTX and DOCX text is extracted with page/slide/paragraph provenance.
- Legacy PPT is converted by LibreOffice before extraction.
- Audio and MP4 speech use local Whisper, retaining segment timestamps.
- JPEG, JPG and PNG are accepted as individual materials, including in multiple-file
  uploads. Images are limited to 20 megapixels and 100 MiB. Readable text uses
  OCR; a configured vision model can also index a checked visual interpretation.
  Images without readable text need the vision model to produce usable content.
- OCR can extract image text in PDFs/slides. It is not full visual reasoning:
  unlabeled arrows or a diagram's spatial meaning may not be established.
- Citation buttons open the original PDF page, rendered presentation slide or
  recording at the cited timestamp. References to one location are grouped and
  unrelated retrieved passages are not displayed as answer citations.
- Slide previews require LibreOffice and are cached after the first conversion.
  Hidden slides are included to preserve numbering. Fonts/formatting can differ
  slightly from PowerPoint. Unsupported document locations retain an excerpt
  and original download instead of claiming an exact page mapping.
- Uploaded files and generated tools are stored locally; this is a laptop demo,
  not a production hosted service. Chat UI state is restored from browser storage
  scoped to the account; it is not a cross-device synchronized chat history.
- Generated content is checked against available passages; requests may return
  fewer verified items than requested. Local-model checks are fallible.
- Progress reports assessment performance and estimated per-topic mastery.
  Source-graded quizzes and Check my understanding replies update the persistent
  learner model. Reading explanations alone does not update mastery. Fixed BKT
  parameters are prototype assumptions, not measured human learning gains.
- Numerical practice, diagnostic/adaptive assessment and possible misconception
  feedback are implemented with the limits described below. This does not by
  itself establish that every Track D requirement has been fully validated.
- Seeded synthetic student-policy simulation results are included. They do not
  demonstrate human learning gains or benchmark the live question generator.
  Live RAGAS scores require running the separate evaluation workflow below.
- Authentication tokens expire after 30 minutes. Refresh restores the session
  while its token remains valid. Logout-token revocation is process-local.

## Verify your installation

```powershell
npm run build
.\.venv\Scripts\python.exe scripts/check_local_setup.py
```

With services running, check signup, login, a small material upload, a cited
tutor explanation, study-tool generation, assessment submission and Progress.
Confirm a second account cannot access the first account's materials.

## Material preparation

The backend accepts uploads and prepares them in the background. The workspace
shows preparation status and progress; wait for Ready before asking questions
about a new material. Refreshing restores persisted job progress. Failed or
interrupted jobs support retry. Keep the backend running during preparation.

Qwen is reused within a backend process and text is encoded in batches.
Chunks and embeddings use bulk database writes. Repeated images reuse OCR
results, with bounded OCR workers for slide images. Background processing
keeps the workspace usable but does not by itself reduce processing time.
Measure extraction and indexing timings on your own laptop.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| `AUTH_JWT_SECRET is missing` | Generate `backend/.env`, then restart the backend |
| `email_validator` / `jwt` / `pwdlib` missing | Install the root requirements in the interpreter used by uvicorn |
| `password_hash` / `owner_student_id` / study table missing | Fresh database: initialization; existing installation: missing migration only |
| `extension vector is not available` | Use the supplied Docker image or install pgvector on native PostgreSQL |
| Port 5433 occupied | Change `DB_PORT` before starting the new Docker database |
| `.ppt` conversion unavailable | Install LibreOffice or use `.pptx` |
| Very slow first upload | Model downloads, OCR and CPU embeddings can take time; preload and use a shorter deck |
| Summary says it cannot verify | Check that the selected material is ready and its extracted text supports the request |
| Figure action asks for a vision model | Install `gemma3:4b`, run `scripts/configure_vision.ps1`, and restart the backend |
| JPEG/PNG has no readable content | Configure the vision model for a text-free diagram/photo and retry preparation; inspect OCR/vision limitations |
| UI still shows an old answer | Ask a new question; saved messages are not rewritten by backend updates |
| Preview still shows old UI | Stop preview, run `npm run build`, restart preview and refresh |

All services run locally; no hosting deployment is needed.

## Personalized practice and topic mastery

After a material is ready, Overview offers a short starting-point diagnostic.
The diagnostic samples supported topics, with up to five verified questions.
Untested topics remain unknown; this is not a full-course placement exam.

Assessment offers adaptive practice, a diagnostic, or a manually selected
level. Adaptive practice selects the weakest recorded topic in the selected
material and uses its estimated mastery to choose a level. An explicit new
focus starts at beginner instead of borrowing another topic's score.

Tutor includes a collapsible **Check my understanding** section. Its single
verified short-answer question is graded against the material; the checked
reply updates mastery. Asking for explanations or simply reading an answer
does not increase mastery. Normal tutor answers use available topic evidence
to adjust explanation style while retaining the citation checks.

Overview and Progress show estimated topic mastery, checked-answer counts,
limited-evidence labels and a practice action. Existing assessment accuracy
remains separate from mastery; tutor checks are not counted as full quizzes.

On backend startup, the additive learning migration creates its tables and
imports existing account-owned graded assessments once. Repeated startup and
submission retries do not double-count evidence. Existing uploads, GPU/CPU
configuration, authentication and quiz results are preserved. Do not rerun
fresh-database initialization on an existing database.

See [docs/LEARNER_MODEL.md](docs/LEARNER_MODEL.md) for the learner-model method,
fixed prototype parameters, evidence boundaries and validation limits.

## Original-source viewer

Click a citation in Tutor, Chat home, Notes, Summary, Flashcards, an assessment
or its feedback. PDF and slide citations open the cited original location, with
Previous, Next and Back to citation controls. Video/audio citations open a
player and seek to the citation's time. Playback requires a browser-supported
codec. The player currently fetches the authenticated recording as a Blob;
large files can take time before playback begins.

Source access checks both the student's material ownership and course ownership.
Original files are restricted to the backend upload directory; no permanent
public links or access tokens in URLs are created. Missing originals retain
available extracted excerpts. DOCX paragraph references do not imply an exact
original page; such locations offer an excerpt and original download.

No database migration or embedding refresh is needed for this feature. The
backend uses the original files stored at upload time. Existing chat entries
also use the corrected cited-source display; their answer text is preserved.

## Source-first tutor with related explanations

Tutor combines semantic retrieval with exact topic matches and nearby slides or
pages in the selected material. It first tries a cited, checked explanation. If
that paraphrase fails but relevant extracted text exists, it can retain exact
supporting excerpts instead of discarding useful evidence.

An optional, separately labelled **Additional explanation — outside the uploaded
material** section expands the same topic. Generation is anchored to the source
definition; a model consistency check rejects off-topic, contradictory or
uncertain supplements. This check is not independent factual verification, and
outside details are never credited to source citations. No fixed percentage of
extra information or accuracy improvement is promised. Extra generation and
checking calls may increase response time on CPU and GPU.

Ask "Use only the presentation" or "Keep it to 2–3 sentences" to suppress extra
background. API clients can set `include_related_background: false` on private
chat requests. Reading additional context does not update mastery; practice
grading remains source-based. Existing saved answer text is not rewritten.

Source-grounded tutoring uses extracted evidence; the separate vision feature
below handles original images and figures. Neither establishes measured human
learning gains. See
[docs/TUTOR_GROUNDING.md](docs/TUTOR_GROUNDING.md) for behavior and live checks.

## Figure interpretation, numerical questions and evaluation

Chat home and Study workspace accept up to five files in one selection (100 MiB
per file). Transfers create individual preparation jobs, and model processing
uses the existing queue. Each file has its own status. Failed transfers can be
retried without uploading the successful files again. If the shared preparation
queue is full, wait for capacity and retry the failed uploads. Each prepared file
appears as a separate material in the workspace; choose it to scope your tutor.

The original-source viewer now offers **Explain this figure or diagram** on PDF
pages, slides and uploaded JPEG/PNG images. It reads the displayed image with a separately configured
local vision model (`OLLAMA_VISION_MODEL`), rather than inferring relationships
from OCR labels. Returned interpretations include limitations and need visual
review. `gemma3:4b` is an image-capable example; install the model with Ollama
before configuring it. New standalone image uploads can index checked visual
interpretations. Existing PDF/slide visual content is interpreted on demand.

Assessment offers **Numerical (with units)** for material with an explicit
quantitative relationship. Formula support is model checked; bounded arithmetic
and unit dimensions determine the hidden server answer key. Feedback can flag
possible misconceptions, independently of correctness grading. Saved results
retain the existing ownership, retry and mastery protections.

The `evaluation/` directory contains an annotated demo PDF, live API collector,
pinned local RAGAS scorer and seeded multi-session student-policy simulations.
Included simulation results are synthetic; live model metrics require running
the collector and scorer on your own uploaded material. See
[docs/FINAL_FEATURES.md](docs/FINAL_FEATURES.md),
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) and
[docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). The demonstration video still needs
to be recorded and uploaded.

## Run optional live evaluation

Application Python packages belong in the root `requirements.txt`; optional
RAGAS evaluation packages belong in `evaluation/requirements.txt`. Frontend
packages are installed through `npm ci`. Ollama models, PostgreSQL/pgvector and
LibreOffice are separate installations rather than pip dependencies.

Upload `evaluation/demo_material.pdf` as a new material. Replace the two ID
placeholders below with its actual course and source IDs, then collect responses
from the running local backend:

```powershell
.\.venv\Scripts\python.exe evaluation/collect_live.py --course-id YOUR_COURSE_ID --source-id YOUR_DEMO_SOURCE_ID
```

The collector asks for your Aura account email and a hidden password unless an
`AURA_BENCHMARK_TOKEN` is supplied. It saves responses and source-location metrics
in `evaluation/results/live_responses.json`, which is ignored by Git because
responses may contain private material. The default test set is a small fixture;
add manually annotated questions from your actual course for a meaningful report.

Install pinned evaluation dependencies in a separate environment and score the
collected responses with local Ollama models:

```powershell
.\.venv\Scripts\python.exe -m venv .venv-eval
.\.venv-eval\Scripts\python.exe -m pip install -r evaluation/requirements.txt
ollama pull nomic-embed-text
.\.venv-eval\Scripts\python.exe evaluation/score_ragas.py --judge gemma3:4b --embedding-model nomic-embed-text
```

This uses `gemma3:4b` as the optional evaluation judge, separately from its
vision role in the app. The scoring script writes faithfulness, answer relevancy,
context precision/recall and failure counts to `evaluation/results/ragas_metrics.json`.
Null scores indicate failed metric evaluation; they are not fabricated successes.
Local model-judged scores require review and can take time on CPU.

To reproduce the included synthetic policy simulation:

```powershell
.\.venv\Scripts\python.exe evaluation/simulate_students.py --seed 42 --students 60 --sessions 8
```

Live model validation and the actual 3–10 minute YouTube demonstration remain
separate completion steps. See the evaluation and demonstration documentation.

## English answer quality and evidence limits

Tutor responses default to English for English questions. Unrequested Chinese,
Japanese or Korean annotations are rejected in generated answers and omitted
from fallback quotations. The original indexed text and original files remain
unchanged for inspection. English explanations use a compact set of intact,
relevant source sentences, a shorter teaching prompt and the selected file's
identity in the relevance check. A failed draft gets a bounded repair rather
than a long repeated collection of verification text. Checked compact synthesis
is attempted before a short, clearly labelled evidence fallback.

These changes reduce quote dumping and topic drift but cannot guarantee the
configured local model's factual accuracy. Source citations establish agreement
with extracted material, not independent scientific truth. OCR and visual-model
interpretations can be wrong. Ask a NEW question after restarting: saved answers
are not rewritten. Response `pipeline_version` is `aura-image-english-tutor-v5`.
No reindex is needed for the answer-language changes. New image support requires
Pillow, included in requirements.txt. See docs/IMAGE_AND_ANSWER_QUALITY.md.
