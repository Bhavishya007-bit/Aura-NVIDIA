# Code & data agent

The Study Plan workspace now includes **Code & data**. Describe a calculation,
algorithm experiment or small CSV analysis. Aura writes Python, executes it, reads
the captured output and explains the result. It can correct code once. This is a
bounded code-analysis skill, not a terminal, package installer or full IDE.

## Local setup without another API key

Keep the existing working Nebius LLM configuration. Install/start Docker Desktop
with Linux containers, then from the repository root build the small guest image:

```powershell
docker build -f sandbox/Dockerfile -t aura-code:1 sandbox
```

Set in **backend/.env** (never the Vite environment):

```dotenv
AURA_CODE_BACKEND=docker
AURA_DOCKER_IMAGE=aura-code:1
```

Restart FastAPI. Open Study Plan, choose Code & data and try **Calculate and
explain**. Expect captured output, `program.py` and `results.json` downloads.
No Tavily key is needed. The initial image build needs internet; executions have
networking disabled and never pull images. Capability detection checks config
and Docker CLI presence; an unavailable engine/image will fail the run honestly.
Docker containers share a kernel and are the local/development fallback; use the
VM backend for a public service handling untrusted generated programs.

## Token Factory Sandboxes VM backend

Sandboxes is a separate capability from LLM inference; enable access for your
Token Factory project first. Use its setup guide to identify a project and an
immutable image UUID containing `/usr/local/bin/python` (Python 3 with the standard
library and Linux `resource` module). The existing inference model name is **not**
a sandbox image identifier.

```dotenv
AURA_CODE_BACKEND=nebius
NEBIUS_PROJECT_ID=your_project_id
NEBIUS_SANDBOX_IMAGE=your_immutable_image_uuid
# Reuses the existing server-side NEBIUS_API_KEY.
```

Official setup: https://docs.tokenfactory.nebius.com/sandboxes/start/set-up-access
REST reference: https://docs.tokenfactory.nebius.com/sandboxes/reference/index

The adapter sends one disposable spawn request, with `Project`/bearer headers,
networking disabled, explicit guest environment and non-root UID/GID. It polls
operation state and then checks the guest process result, rather than treating
operation SUCCESS as code success. A possibly accepted submission is never
resubmitted or silently moved to another backend. Cancellation requests are
retried by a cleanup worker until terminal state is observed for known handles.
If a submission response is lost before its handle arrives, the provider's
20-second operation timeout bounds it; the app cannot recover that unknown handle.
Provider access, compatibility and charges still require a live project check.

## Inputs, limits and isolation

- A course is required. Selected material is optional for this skill. Study plans,
  research and quizzes keep their existing material behavior.
- Up to two UTF-8 `.csv` attachments, 16 KiB each. They are stored in the existing
  owned run request, not browser localStorage. No arbitrary host file access or
  upload URL is offered. Attaching another selection replaces the previous one.
- The model receives filenames and a short preview. The guest receives full
  attached CSV text and, if document search was used, the observed excerpts as
  `material.json`. All input/output text remains untrusted data.
- Python standard library only (`csv`, `statistics`, `math`, `json`, etc.). No
  pandas, plotting package, package installation or network access is assumed.
- At most two executions, each with 12 seconds wall time, 10 seconds CPU,
  256 MiB child address space and bounded file/process descriptors. Existing run
  step/token/time budgets and cancellation still apply.
- Captures 16 KiB each of stdout/stderr. Up to four requested regular output files
  in CSV/JSON/TXT/MD/PNG, 128 KiB per file and 192 KiB total, plus a server-derived
  `program.py`. Symlinks and special files are excluded; failed code saves only
  the source program and captured messages. No HTML/SVG files are served.
- Docker additionally uses no network, no host mounts, read-only root, non-root
  UID, dropped capabilities, default seccomp, no-new-privileges, 320 MiB memory,
  64 processes, one CPU and a 32 MiB scratch tmpfs. A local image ID is pinned for
  each execution; image volume declarations and unexpected image environment
  keys are rejected. Only use the reviewed guest image without embedded secrets.
- API credentials stay in the host transport headers, outside the guest. A
  successful exit is not factual/source verification; results are labeled drafts.
- Cancelled/expired runs cannot publish late results. Known execution handles are
  persisted before polling; terminal runs with pending cleanup are reaped after
  cancellation or restart. In-flight runs are interrupted rather than replayed.

## Additive API fields; no new database columns

Existing routes/payloads for other skills are preserved. Added:

| Surface | Addition |
| --- | --- |
| `POST /agents/runs` | `skill: code_analysis`, optional `inputs: [{name,text}]` |
| `GET /agents/capabilities` | `code_execution`, `code_backend`, code skill/tool |
| Saved steps | Validated code action, observed status/streams/artifact metadata; private artifact bytes and cleanup handle |
| Run result | `code_result` with observed status/streams/artifact metadata; `verified: false` |
| `GET /agents/runs/{id}/artifacts/{filename}?course_id=...` | Account/course-owned download, attachment, no-store and nosniff |

Artifact bytes remain private in existing run JSONB, omitted from run-list/detail
responses and model prompts. Downloads resolve only the latest completed code
execution, including when a later plan explanation fails. Output and source are
rendered as text, never HTML. The frontend never turns model-invented links into
file downloads. No backend fields were assumed; all additions above are implemented.
No production dependencies were added.

## Validation

Run `evaluation/check_code_agent.py` with the optional PGlite integration configured,
the existing frontend DOM suite and `npm run build`. Tests cover contract limits,
transport settings, bounded uncertain submission, execution checkpointing,
cancellation/expiry, account isolation, authenticated downloads, result rendering
and no-material execution. Fixed, authored fixture programs test the guest wrapper;
no model-produced code is executed on the test host. Transport tests simulate the
provider/Docker engine. A live configured sandbox remains an operator smoke test.

Last implementation check: 34 focused code-agent checks and 43 frontend checks
passed, alongside the full backend suite (283 passed, two optional OCR skips) and production build.
Live Docker/Nebius execution was not available in the implementation environment.


## When a code run says “Something went wrong”

A successful LLM request does not establish that Python executed. Run the
read-only setup check from the repository root in your activated environment:

```powershell
python scripts/check_code_runtime.py
```

It loads the same `backend/.env`, checks Docker connectivity and the prepared
Linux image, and prints a fixed actionable reason without keys, paths or raw
provider messages. It does not call an LLM, query PostgreSQL, execute code or
contact Nebius. For Nebius it validates configuration format only.

Then explicitly test the complete isolation adapter (one VM operation may incur
provider charges when using the Nebius backend):

```powershell
python scripts/check_code_runtime.py --smoke
```

This runs a fixed CSV calculation inside the configured Docker/VM backend and
checks the actual JSON output. No generated program runs on the host. For a
missing local image, start Docker Desktop and rebuild:

```powershell
docker build -f sandbox/Dockerfile -t aura-code:1 sandbox
```

Execution setup failures now retain a specific safe reason in the server log and
Run details. The result panel maps it to plain-language guidance. Raw Docker
stderr, image environments and provider responses remain excluded. An older run
may still contain only the generic reason; use the check above, then retry.


### Docker works in PowerShell, but Aura's check fails

The host Docker client must retain its context/configuration/TLS settings and
normal Windows temp/system directories. Aura now preserves these specific host
settings (case-insensitive variable-name matching) when invoking Docker. It still
excludes application keys/passwords, and does not forward host Docker settings
into the Python container. The guest environment, no-network policy, resource
limits and image pinning are unchanged.

Pull the update, then run `python scripts/check_code_runtime.py --smoke` from the
same activated terminal. The check reports whether the configured image is the
expected `aura-code:1` or a custom image without dumping environment values. On
failure it prints only the stage and numeric exit/OS error codes, including a
Windows error number where available. This separates process-launch failure
from image-metadata parsing without exposing raw stderr or credential-bearing
connection strings. A successful direct Docker command alone does not establish
which host-process setting caused an earlier failure; confirm with the check.
