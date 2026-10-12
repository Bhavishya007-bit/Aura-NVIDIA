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
| [LibreOffice](https://www.libreoffice.org/download/download-libreoffice/) — optional | Convert legacy `.ppt`; not needed for `.pptx` |

A practical demo laptop should have about **16 GB RAM** and several GB of free
disk space for models, dependencies and Docker. This is a planning estimate,
not a measured minimum. A GPU is optional. CPU processing can take several
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

## 3. Install dependencies and download the tutor model

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install "torch>=2.2,<3" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm ci
ollama pull qwen2.5:3b
```

The PyTorch command uses the [official CPU wheel index](https://pytorch.org/get-started/previous-versions/). For a GPU installation, use the official PyTorch selector instead. On macOS, install `torch` from PyPI without the CPU index flag.

Keep Ollama running. The desktop application normally starts its service; if
needed, run `ollama serve` in a separate terminal. If it reports the port is
already occupied, the service may already be running.

Install all backend dependencies using the single **`requirements.txt`**. It
includes authentication, embedding, OCR and audio packages used by the active
application. Qwen3 embeddings require Transformers 4.51 or later; the requirement
file includes that constraint. Model: [Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B).

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
study tool and archive-preference tables in one transaction. It refuses to
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
.\.venv\Scripts\python.exe -c "from backend.ai.embeddings import EmbeddingModel; EmbeddingModel()"
```

The check reports missing Python modules, schema columns or the Ollama model.
Preloading embeddings downloads/caches the Qwen model before the demonstration.
The first audio/video upload also downloads Whisper `base`. Subsequent runs use
cached weights. This does not remove the CPU time required to encode a new file.

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
- OCR can extract image text in PDFs/slides. It is not full visual reasoning:
  unlabeled arrows or a diagram's spatial meaning may not be established.
- Source buttons display cited text and origin metadata. A full original-file
  viewer opening the exact PDF page/video timestamp is not implemented here.
- Uploaded files and generated tools are stored locally; this is a laptop demo,
  not a production hosted service. Chat UI state is restored from browser storage
  scoped to the account; it is not a cross-device synchronized chat history.
- Generated content is checked against available passages; requests may return
  fewer verified items than requested. Local-model checks are fallible.
- Progress currently reports assessment performance. It is not evidence of
  measured learning gain or a fully evaluated conversation-driven learner model.
- Legacy learner-model/adaptive modules remain in the repository, but their
  presence does not imply the current UI implements all Triad B requirements.
- No RAGAS/DeepEval/TruLens benchmark results or simulated mastery gains are
  claimed in this package. Those require a separately executed evaluation set.
- Authentication tokens expire after 30 minutes. Refresh restores the session
  while its token remains valid. Logout-token revocation is process-local.

## Verify your installation

Run `npm run build` and then run
`.venv\Scripts\python.exe scripts/check_local_setup.py`.

With the services running, check signup, login, a small material upload,
a source-based tutor answer, study-tool generation, assessment submission
and Progress. Confirm a second account cannot access the first account's materials.

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
| UI still shows an old answer | Ask a new question; saved messages are not rewritten by backend updates |
| Preview still shows old UI | Stop preview, run `npm run build`, restart preview and refresh |

All services run locally; no hosting deployment is needed.
