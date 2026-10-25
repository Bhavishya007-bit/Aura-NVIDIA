# Phase 5 — Deploy and harden

## Current release status

The deployment code and production safeguards are implemented. A public deployment is **not yet created**: this workspace has no configured Nebius CLI, hosting credentials, managed PostgreSQL URL or Token Factory key. No paid infrastructure has been provisioned. Token Factory model credits are not assumed to cover AI Cloud compute or database hosting.

The GitHub **Production container smoke** workflow builds the real image, initializes a fresh PostgreSQL database with pgvector, starts the non-root app, checks anonymous API protection and opens a fresh logged-out Chromium browser. This is a container verification; it is not the required final test against a public URL. The latter remains pending until the account and URL exist.

## What is implemented

| Phase 5 task | Files | Status |
| --- | --- | --- |
| Containerize backend and build frontend | `Dockerfile`, `.dockerignore`, `scripts/serve_production.py` | Implemented; CI builds and tests it |
| One public origin for UI/API | `backend/production/app.py`, `web.py` | Implemented; `/api` forwards to existing API contracts |
| Managed Postgres with pgvector and TLS | `backend/auth_db.py`, `backend/production/config.py`, `bootstrap.py` | Ready for an account-provided connection URL |
| Nebius Serverless Endpoints first | Provider procedure below; `scripts/check_production.py` | Account access missing; live trial pending |
| Container-host fallback | `deploy/compose.production.yaml`, `deploy/Caddyfile` | Prepared; requires a host, DNS and managed database |
| Synthetic judge account and documents | `backend/production/demo.py`, `schema.sql`, auth/profile changes | Implemented; real ingestion queue, no fabricated vectors |
| Per-user/global token limits | `backend/production/limits.py`, `backend/ai/llm.py`, `backend/study_v2/provider.py`, agent context wrapper | Implemented for all Token Factory calls through the existing clients |
| Request/login rate limits | `backend/production/security.py`, `web.py` | Implemented; database-backed across workers |
| Operator AI kill switch | `scripts/production_control.py`, `limits.py` | Implemented; saved work stays readable |
| Persistent logout revocation | `backend/auth_token_store.py`, `backend/production/security.py` | Implemented for production; token digests, not raw tokens |
| Keep demo free/open through judging | Runbook and checks below | Requires funded hosting and the judging end date; not guaranteed by code |
| Public logged-out browser smoke | `scripts/smoke_public.py`, `scripts/smoke_browser.mjs` | Prepared; final public URL test pending |

Local development stays on `uvicorn backend.main:app --reload` and `npm run dev`. Production explicitly uses `backend.production.app` through the container command. Existing API routes, saved content and model routing remain available.

## Architecture and storage

The image contains the compiled Vite frontend and full FastAPI backend. It runs as UID 10001 with one Uvicorn worker. `/api/...` and the frontend share one origin; direct backend route paths remain available for compatibility. A managed database holds users, vectors, jobs, learning records, token reservations and rate counters. A persistent `/data` volume holds original uploads, source previews and downloaded model caches. Do not deploy with an ephemeral filesystem or mount the host Docker socket into the public app.

The app still uses Qwen embeddings, OCR, LibreOffice for old presentations, and Whisper for audio. The Docker image includes their libraries/system tools. Embedding/transcription models download lazily into `/data/models`. Diagram/image reading additionally needs a reachable vision service; the app image does not contain a running Ollama server. The optional `vision` compose profile supplies a private service. Its port is not published to the internet.

A CPU host needs enough RAM for the real embedding model and any vision model. Start by evaluating a 16 GB host for the complete CPU demo, then measure actual memory/latency. This is a planning starting point, not a measured capacity guarantee. A tiny free web-service instance is not assumed sufficient.

## Create the production configuration

After pulling the release, from the repository root:

```powershell
python scripts/create_production_config.py
```

This creates ignored `deploy/.env.production`, refuses to overwrite it, and generates random JWT/demo secrets without printing them. Open that file locally and set:

- `DATABASE_URL`: the managed database connection string, with `sslmode=require` or stronger verification. Its database role must be able to enable pgvector and initialize Aura tables.
- `NEBIUS_API_KEY`: the server-side Token Factory key. Keep existing tested model IDs/role overrides; no browser API key is needed.
- `AURA_PUBLIC_HOSTNAME` and `AURA_ALLOWED_HOSTS`: the real host, without `https://` or a path; keep localhost/127.0.0.1 for container health checks.
- `OLLAMA_BASE_URL` and `OLLAMA_VISION_MODEL`: the reachable private vision service and installed model.
- Optional `TAVILY_API_KEY` and isolated Nebius sandbox settings only if those services are actually enabled for your account.

Run the read-only configuration preflight:

```powershell
python -m scripts.check_production --env-file deploy/.env.production
```

Add `--services` when the database and vision service are reachable from the machine running the check. It checks real connectivity without spending generation tokens or creating resources. Do not send the `.env.production` contents in chat or commit them.

## Try Nebius Serverless Endpoints first

Time-box the live trial to 20 minutes **after** access is available. Required inputs: an AI Cloud project with endpoint quota, a published container image, a managed Postgres URL, a writable persistent filesystem mounted at `/data`, and a vision service if the demo uses images. Access to Token Factory alone does not establish these resources.

Use the Nebius console's Serverless AI → Endpoints form or the documented `nebius ai create` wizard. Configure:

1. Image: the tested release image by commit/digest, or your registry equivalent. The optional manual GitHub workflow input `publish=true` publishes the tested image to GHCR. Make the image accessible to Nebius or supply a registry secret.
2. CPU platform/preset: an account-supported preset with sufficient memory. The official CPU endpoint quickstart uses `cpu-d3` and `4vcpu-16gb`; confirm availability in your project.
3. Container port: `8000`. Keep the image's command.
4. Store credentials in provider secrets and map them to the variables in `deploy/production.env.example`; use the documented `--env-secret` support if using the CLI. Do not put secrets in shell arguments, screenshots or committed manifests.
5. Mount a persistent **filesystem** read/write at `/data`, writable by UID 10001. A bucket mount may have different rename/locking semantics; do not assume it is a drop-in replacement for model caches and LibreOffice profiles.
6. For this browser app, use public access at the platform edge with **Aura's own login protection**. A mandatory edge bearer token would also block the logged-out browser and conflict with Aura's user bearer token; never put such an infrastructure token in Vite.
7. Set `AURA_ALLOWED_HOSTS` to the assigned managed hostname, plus local health-check hosts, before enabling public traffic. Allow egress to the database, Token Factory and model download service. Use `/health` for liveness and `/ready` for database readiness.
8. Verify storage survives a restart, demo ingestion finishes, and the smoke commands below pass. Record the URL, image commit, restart test and trial result in the release checklist.

If project access, persistent filesystem, vision connectivity or acceptable startup time cannot be established within the trial, stop that trial and use the container-host fallback. Stop/delete abandoned trial resources through the console. No endpoint creation command is auto-run by this repository.

Official references reviewed for this setup:

- https://docs.nebius.com/serverless/quickstart/endpoints
- https://docs.nebius.com/serverless/endpoints/manage
- https://github.com/nebius/serverless-ai-cookbook/blob/main/quickstarts/first-endpoint.md

## Container-host fallback

On a Linux Docker host, point your domain to the host, make ports 80/443 reachable and supply the managed database URL. From the repository root:

```sh
# For text-only deployment, omit the vision profile and configure a reachable vision host separately.
docker compose --env-file deploy/.env.production -f deploy/compose.production.yaml --profile public --profile vision up -d --build
docker compose --env-file deploy/.env.production -f deploy/compose.production.yaml --profile vision exec vision ollama pull gemma3:4b
```

Caddy handles HTTPS for the configured public hostname. The app binds only to localhost on host port 8000; the vision service stays private. Upload/model/TLS data use persistent named volumes. Back up the database and `/data`; retain these volumes during upgrades. Do not run `down -v` against a deployed demo.

For an existing container platform, deploy the same image, attach its persistent disk at `/data`, set the environment variables, expose the configured `PORT`, and use the platform's HTTPS ingress. If the ingress forwards client/scheme headers, set `AURA_TRUSTED_PROXY_IPS` to that provider's trusted proxy addresses. Do not blindly trust public forwarding headers.

## Judge account and honest readiness

The judge email defaults to `judge@aura.example.org`; its password is generated in the local ignored configuration. Put these credentials in the private hackathon test-credentials field, not the public README. The profile displays **Demo account**. The shared account cannot upload private documents. Personal accounts remain isolated; public registration is closed by default and can be explicitly enabled with `AURA_ALLOW_REGISTRATION=true`.

First startup creates a six-page original synthetic PDF covering hash tables, collisions, searches and a numerical worked example. It enqueues the normal ingestion pipeline; it does not invent embeddings, citations, mastery or completed results. Seeding is idempotent and refuses to take over an existing personal account with the same email. The application can be live while first model download/ingestion is still preparing; do not record the final demo until the synthetic material is ready.

After readiness, test:

- Source-aware answer and follow-up using the seeded document.
- A study plan, task completion and saved memory preference.
- Mixed assessment and save/resume; flashcard generation/review; notes edit/export.
- Two-image question only after vision preflight passes.
- Code execution only with a real isolated sandbox configured. The public image deliberately refuses the host-Docker backend.

## Credit caps, rate limits and AI pause

Production reservations apply to regular answers, judges, agent calls and v2 generation through the existing Token Factory clients. They use database-day accounting and a deployment-wide lock. Default limits are 500,000 tokens per user/day and 2,000,000 globally/day, adjustable in the production environment. Prompt/output estimates reserve capacity before requests; actual provider usage settles it. Missing usage conservatively charges the reservation. These are token limits, not a promise of dollar cost across different model prices. V2's existing study-specific budget also remains active.

Anonymous login requests and authenticated requests have separate database-backed per-minute limits. Saved work remains readable when the daily generation limit is reached. Anonymous IP limits use the connection address; configure trusted proxy forwarding correctly before treating it as a per-person limit.

To pause new AI work on the compose host:

```sh
docker compose --env-file deploy/.env.production -f deploy/compose.production.yaml exec app python -m scripts.production_control pause
docker compose --env-file deploy/.env.production -f deploy/compose.production.yaml exec app python -m scripts.production_control status
# When ready:
docker compose --env-file deploy/.env.production -f deploy/compose.production.yaml exec app python -m scripts.production_control resume
```

Use the platform's container console with the same Python module on other hosts. No public admin endpoint is exposed. The switch blocks subsequent model calls and commits; v2 streaming checks close the active request. Older synchronous HTTP calls may finish at the provider before their result is discarded. Existing checked partial results remain saved. `AURA_AI_ENABLED=false` provides an environment-level stop as well.

Production uses TLS to the managed database, explicit allowed hosts, same-origin CORS by default, non-root application execution, no-store private responses, safe error messages, security headers and a persistent hashed logout-token denylist.

## Final public smoke and judging-period checklist

On a machine with Python/requests:

```sh
python -m scripts.smoke_public https://YOUR_PUBLIC_HOST
# With AURA_DEMO_PASSWORD set privately in your shell, after synthetic ingestion is ready:
python -m scripts.smoke_public https://YOUR_PUBLIC_HOST --demo-login
```

For the browser check, install Playwright as a test-only dependency outside the repository (as the CI workflow does), set `AURA_UI_TEST_MODULES` to that dependency directory, and run:

```sh
node scripts/smoke_browser.mjs https://YOUR_PUBLIC_HOST
```

This opens a fresh browser with no stored login and verifies the sign-in page and protected API. It does not prove that every model answer is accurate. The HTTP demo-login check additionally verifies the demo flag, ready material and rejected revoked token.

Before declaring Phase 5 complete:

- [ ] Public HTTPS URL is available from a logged-out browser.
- [ ] Managed database and `/data` survive an app restart; backup/restore procedure is recorded.
- [ ] Synthetic material finishes real ingestion; judge credentials work.
- [ ] All advertised tools pass real end-to-end tests with the selected model/vision/sandbox services.
- [ ] Deployment token caps/rate limits and pause/resume have been exercised.
- [ ] Hosting account has enough balance through the actual judging end date; no sleeping/expiring service interrupts access.
- [ ] Public smoke commands pass and the URL/commit/time are recorded.

No hosting account, public URL, judging end date or service budget is invented by this release. These external steps remain pending until configured.
