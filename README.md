# Aura

**A personalized AI study workspace built around your own materials.**

Upload course material, ask questions with source citations, create a study plan,
practice with flashcards and assessments, and track what you have studied.
Aura uses React and TypeScript (Vite), FastAPI, PostgreSQL with pgvector, and
NVIDIA Nemotron through Nebius Token Factory.

## Get started

The same installation and personal-account flow applies to everyone. There is
no required shared account or preloaded course. The source repository is public:
[Bhavishya007-bit/Aura-NVIDIA](https://github.com/Bhavishya007-bit/Aura-NVIDIA).
These instructions run Aura on your computer at **http://localhost:8888**;
they do not create an internet-hosted website.

### What you need

- **Git** to download and update the source.
- **Docker Desktop**, running with **Linux containers**, and Docker Compose v2.
  On Linux, Docker Engine with Compose v2 also works.
- A **Nebius Token Factory API key** with access and balance for the configured
  Nemotron model. AI requests consume the owner's provider credits.
- Enough memory, disk space and internet bandwidth for the application and local
  model downloads. Around **16 GB RAM** is a planning starting point for the full
  CPU setup, not a measured minimum. Vision needs additional memory.

The Docker setup includes the frontend, backend, PostgreSQL, OCR, LibreOffice
and audio-processing dependencies. You do **not** need to start `npm run dev`,
Uvicorn, or a Python virtual environment when using it. An NVIDIA GPU is not
required; the packaged embedding runtime uses CPU.

### 1. Download Aura

Open PowerShell and run:

```powershell
git clone https://github.com/Bhavishya007-bit/Aura-NVIDIA.git
cd Aura-NVIDIA
```

Already have this repository? Open its folder in PowerShell and use
`git pull origin main` instead. Commit your own edits before pulling; resolve
any reported conflicts rather than overwriting your work.

### 2. Start the application

For text documents and the study workspace:

```powershell
powershell -ExecutionPolicy Bypass -File judge/start.ps1
```

For screenshots, image questions and visual interpretation, enable the optional
vision service during first setup instead:

```powershell
powershell -ExecutionPolicy Bypass -File judge/start.ps1 -Vision
```

On macOS/Linux, use `bash judge/start.sh` or `bash judge/start.sh --vision`.
The existing `judge/` directory name is retained for script compatibility;
these are the normal local setup scripts for all users.

The script builds the image, asks for your **Token Factory API key** using hidden
input, generates private local settings, starts the database and app, and opens
Aura. This key is different from a Tavily key, an Aura password, or an email
password. The initial configuration selects Nemotron Ultra; access depends on
your provider account. Existing settings are preserved.

**First installation can be slow.** It downloads large system/Python packages;
on slow connections it can take over an hour. Docker's changing elapsed times
are per-step timers, not a countdown. Later builds reuse completed layers when
possible. The first document can also trigger a separate embedding-model
download. Vision setup downloads Gemma separately. No fixed completion time is
guaranteed.

Private configuration lives in `judge/.env.judge` and is ignored by Git. Keep
it on your computer; never upload it, paste it into an issue, or put its API key
in frontend/Vite settings.

### 3. Create your personal account

Open **http://localhost:8888**, choose **Sign up**, enter your email and choose a
new Aura password. Aura does not connect to Gmail; do not use your email-account
password. Existing users can sign in normally.

Each account has its own workspace. A fresh account has no uploaded material.
Accounts, documents, local settings and downloaded models are not transferred by
GitHub. Someone installing on a different computer configures their own instance.

### 4. Add and select materials

1. Open the study workspace and choose **Add material**.
2. Upload PDF, PPT/PPTX, DOCX, JPEG/PNG, supported audio, or MP4 material.
   Each file must be at most **100 MiB**. Compress/split larger files or upload a
   transcript where appropriate.
3. Wait for preparation to finish. Processing files cannot be selected yet.
4. Use the material checkboxes to select **up to five** ready files.
5. Check the **Using** chips above the tutor or study tool. Remove a chip or
   choose **Change** to adjust the selection.

A **study set** saves a named group of materials, so you can select the same group
again in one step. It does not merge or duplicate the original files. Select the
files, use the study-set save/create control in Materials, and give the set a
name. You can rename or delete the group later.

Start with a small document and a question whose answer you can verify manually.
Large presentations, scanned PDFs, media transcription and visual interpretation
can take longer. Leave the preparation running and return to the workspace;
avoid repeatedly reuploading the same file while it is still processing.

## Using Aura

| Area | What to do |
| --- | --- |
| **Tutor** | Ask about the selected materials, continue with follow-up questions, or attach screenshots and text together. |
| **Notes** | Generate study notes, then review and use the available editing/export controls. |
| **Summary** | Request an overview or a more detailed explanation of the selected content. |
| **Flashcards** | Choose the number of items and optional focus, generate cards, and review them. |
| **Assessment** | Choose a supported question type, answer the questions and submit to save feedback. |
| **Progress** | Review recorded assessment results and topics that need more practice. |
| **Study Plan** | Give Aura a goal, choose an outcome and optional study preferences, then create a plan or research brief. |
| **Today** | Resume saved study tasks and mark completed work. |
| **Account → What Aura remembers** | Review, edit or delete saved memories, and control whether memory is used. |

Try a goal such as **“Make a three-day plan for this material, 30 minutes per day”**.
Study plans should be structured by day and task. Plans and background runs keep
their saved progress when you leave the page. Available actions depend on your
configured services and ready materials.

In chat, **Enter** sends and **Shift+Enter** adds a line. During generation,
use **Stop** or **Esc**; job-based work may briefly show **Cancelling…**.
Keep any partial results available in the interface, then edit/resend or retry.
Stopping a browser request may not immediately stop a provider-side calculation.

### Sources and answer quality

**From your material** identifies claims checked against retrieved evidence;
citations point to the material name and available page, slide or timestamp.
DOCX excerpts may have no physical page number. Open citations to inspect the
source. **Beyond your material** is separately labelled background; it must not
be mistaken for content present in your files. Web-backed findings are separately
identified when web search is configured.

OCR, visual interpretation and generated explanations can be wrong. A citation
establishes source support, not independent factual correctness. Long requested
word counts can still fall short when generation or verification fails; a short
fallback is not a completed long summary. Check important claims against the
original. Successful Python execution likewise does not prove its explanation or
underlying data is correct.

### Prototype model and usage policy

The local Docker stack uses **NVIDIA Nemotron 3 Ultra 550B** for coverage,
answers, agents and deep reasoning through Nebius Token Factory, including
existing installations after rebuild/recreation. `AURA_NVIDIA_MODEL` can override
this shared Docker selection. Ultra is a text model; OCR, embeddings and the
optional local vision service remain separate. There is no automatic downgrade
when model access fails.

Aura's daily user/global/study token blocking is **disabled by default** for the
prototype (`AURA_DAILY_LIMITS_ENABLED=false`). Existing usage records remain and
new requests are still accounted for; old daily totals no longer block new work.
No database reset is needed. Cancellation, finite agent/generation budgets,
per-request size limits, authentication and the AI pause switch remain active.
Provider credits and provider rate/context limits still apply. To re-enable daily
blocking later, set `AURA_DAILY_LIMITS_ENABLED=true` and recreate the app.

For a native backend using an existing `backend/.env`, run
`python scripts/configure_model_quality.py --apply` and restart Uvicorn to select
the same Ultra profile without replacing keys or database credentials. In Docker,
the Compose configuration applies the model and daily-limit policy automatically.

Official model and event references:
[Nebius Ultra quickstart](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-ultra-550b-a55b.md),
[hackathon rules](https://nebiusglobalaihackathon.devpost.com/rules).
A larger model does not guarantee accurate answers; source and duplicate checks
remain in place.

### Optional: Code & data

After the base installation, on Windows run:

```powershell
powershell -ExecutionPolicy Bypass -File judge/enable-code.ps1
```

This starts the separate local Docker execution service and tests a fixed Python
program with CSV output. Wait for **“Python execution verified”**, refresh Aura,
and choose **Code & data**. Runs can show captured output, generated Python and
file downloads. This is a bounded Python environment, not unrestricted terminal
access or a general package installer.

The local execution service uses privileged Docker-in-Docker without mounting
the host Docker socket. It is intended for a trusted local installation; do not
expose this service publicly. Public hosting needs a separately configured
supported isolation backend. [Execution details](docs/CODE_ANALYSIS.md).

### Optional: Web research and vision

- **Web research:** set `TAVILY_API_KEY` privately in `judge/.env.judge` if you
  have Tavily access. It is a separate service/key; a Nebius key cannot replace
  it. Document study does not require Tavily.
- **Vision:** the `-Vision` setup option starts a private Ollama service and
  downloads `gemma3:4b`. It adds image interpretation; OCR alone cannot reliably
  solve questions about relationships in diagrams. For an existing installation,
  set `AURA_JUDGE_VISION_MODEL='gemma3:4b'` in the private local settings and run
  the start script again. If Code & data was enabled, run `enable-code.ps1`
  afterwards to retain that overlay.

Configuration changes require recreating the app container, not just refreshing
the browser. Never share the configuration file.

## Updating and restarting

From the repository root:

```powershell
git pull origin main
```

**With Code & data enabled**, update/build and restart with the same overlay:

```powershell
powershell -ExecutionPolicy Bypass -File judge/enable-code.ps1
```

**Without Code & data**, use:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml up -d --build --wait app
```

Git updates source files on the host. A running container keeps its old image
until rebuilt/recreated. Pulling alone does not update Python scripts or UI inside
it. Keep Docker's build cache; avoid `--no-cache` unless diagnosing a specific
cache problem. Completed dependency layers are reused when their inputs match.

To start an already-built installation without rebuilding, use the same Compose
files as before with `up -d --no-build`. To stop it, use `stop` with those same
files. Database/uploads/model caches live in persistent named volumes. **Do not
use `down -v` or delete these volumes** if you want to keep your data.

## Check an installation

Run these on the computer where Aura is running, from the repository root.
They assume Code & data is enabled; otherwise omit
`-f judge/compose.code.yaml` from the feature/status/log commands.

**Service status** — the app, database and optional code service should be healthy:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml ps -a
```

**Python execution**, without model requests:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml exec -T app python -m scripts.check_code_runtime --smoke
```

**Database and routes**, without model requests:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml exec -T app python -m scripts.check_features
```

**Model connectivity** — replace the placeholder with an existing Aura login
email. This is an operator diagnostic run in your local container, not a public
API. It makes three small real requests and retains the AI pause switch:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml exec -T app python -m scripts.check_features --live --account-email "YOUR_AURA_EMAIL"
```

**Slow document preparation**, without model requests or document-content output:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml exec -T app python -m scripts.check_preparation
```

Passing checks do not replace testing a real upload, supported question, generated
study tool, saved memory and assessment in the browser.

### Troubleshooting

| Symptom | Next action |
| --- | --- |
| Cannot connect to Docker / missing Linux-engine pipe | Start Docker Desktop, select Linux containers, and wait for the engine to be ready. |
| `--account-email` is unrecognized | The container still has an older diagnostic. Pull the source and use the script-only check below. |
| `No module named backend` | Invoke diagnostics with `python -m scripts.check_features`, not an old direct-path script. |
| A service is unhealthy | Collect service logs below; the setup script's final exception alone is not the cause. |
| AI paused / daily allowance reached | Daily limits are off by default for the prototype. Check whether your installation explicitly enables them; AI pause controls remain separate. |
| Upload remains preparing | Run the preparation check. First model downloads, queued uploads, OCR and optional vision can dominate runtime. |
| File exceeds 100 MiB | Compress, split, or supply a smaller document/transcript. Repeated retry cannot change the limit. |
| Study generation fails despite healthy services | Check the live model test, selected ready materials and application logs; a healthy container is not proof of a valid generated response. |

For the **diagnostic script only**, execute the freshly pulled host script inside
an existing container without rebuilding or writing to its read-only filesystem.
This PowerShell command replaces the old script just for this check; replace the
email placeholder first:

```powershell
Get-Content -Raw scripts/check_features.py | docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml exec -T app python -c "import sys; exec(compile(sys.stdin.read(), '/app/scripts/check_features.py', 'exec'), {'__name__': '__main__', '__file__': '/app/scripts/check_features.py'})" --live --account-email "YOUR_AURA_EMAIL"
```

Normal application updates still require a build. This diagnostic does not alter
the image, overwrite settings or disable production controls.

Collect logs with:

```powershell
docker compose --env-file judge/.env.judge -f judge/compose.yaml -f judge/compose.code.yaml logs --tail=100 app code db
```

Review logs before sharing. Never post API keys, passwords, private configuration
or sensitive document content. Do not reset the database to diagnose a generation
error.

## Development, hosting and validation

The repository includes the Vite frontend (`src/`), FastAPI backend (`backend/`),
configuration/diagnostics (`scripts/`), local Docker stack (`judge/`), isolated
execution image (`sandbox/`), production manifests (`deploy/`) and regression
evaluations (`evaluation/`, `tests/`).

Native development uses Python 3.12, Node.js, PostgreSQL with pgvector and the
system tools required by your selected file formats. Configure `backend/.env`
using `scripts/create_local_config.py`, replace database values with your own
local PostgreSQL credentials, configure the server-side Nebius key/model, install
`requirements.txt` and `npm ci`, and initialize the intended database with
`scripts/init_database.py`. Then run `uvicorn backend.main:app --reload` and
`npm run dev` in separate terminals. Docker setup is the primary reproducible
path above; do not mix its private database settings with a native installation.

Public hosting needs a reachable HTTPS host, persistent uploads/model storage,
PostgreSQL with pgvector, server-side provider credentials and sufficient memory.
The local `localhost:8888` address is only accessible on your computer. A public
GitHub repository supplies source code, not a live application URL. Hosting is
not automatically provisioned by cloning or starting Aura.
[Production deployment procedure](docs/PHASE5.md).

Evaluation scripts and documented results are in `evaluation/`. Synthetic tests,
real provider runs and human-labelled calibration are different forms of evidence;
none establishes universal answer accuracy. See [evaluation guidance](docs/PHASE4.md)
and the [architecture](docs/ARCHITECTURE.md) for technical detail.
