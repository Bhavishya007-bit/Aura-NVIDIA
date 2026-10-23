# Code & data agent

The Study Plan workspace now includes **Code & data**. Describe a calculation,
algorithm experiment or small CSV analysis. Aura writes Python, executes it, reads
the captured output and explains the result. It can correct code once. This is a
bounded code-analysis skill, not a terminal, package installer or full IDE.

## Teaching explanations and observed evidence

The explanation step now receives the actual program associated with each execution, alongside the captured stdout/stderr. Previously its context contained execution results and file metadata but omitted the program body. This matters when explaining loop bounds, early exits, copies, comparison counts and failed/corrected attempts.

Program text is bounded to 6,000 characters per attempt, and stdout/stderr context to 4,096 characters each. Context shortening sets explicit truncation flags while leaving the full saved execution record and downloads unchanged. Code/comments/output stay untrusted data, and artifact bytes are still stripped from model context. Existing token, time and execution-attempt budgets remain in force.

The code-only teaching policy asks for a worked example, actual printed trace/results, assumptions and complexity. Search examples should print each target/index/count and assert membership consistency. Sort examples should print a short pass/swap trace and assert against a trusted sorted copy. Algorithm comparisons should prefer defined operation counts; explicitly requested timings require repeated trials, suitable sizes and measurement caveats. Copies, recursion and stored traces must be distinguished from an algorithm's auxiliary-space bound.

These changes add no judge call or automatic extra code run. They do **not** deterministically verify arbitrary natural-language explanations. Results remain `verified=false`; live model quality still needs review. Existing saved answers retain their text: regenerate or start a fresh run to use the new context and instructions.

A corrected reference for the reported search example, using ordinary linear search and iterative binary search with the lower midpoint:

| Target | Status | Index | Linear items inspected | Binary midpoint probes |
| ---: | --- | ---: | ---: | ---: |
| 1 | Found | 0 | 1 | 3 |
| 4 | Absent | -1 | 8 | 3 |
| 7 | Found | 3 | 4 | 1 |
| 15 | Found | 7 | 8 | 4 |

Input: `[1, 3, 5, 7, 9, 11, 13, 15]`. A probe counts one examined element, not every primitive comparison. These are deterministic counts, not speed measurements. Bubble sort with early exit has O(n) best-case time on already sorted input and O(n²) average/worst-case time; a nearly sorted list can still require quadratic work. An in-place sorting function can use O(1) auxiliary space while its demonstration's copied input and recorded trace use additional memory.

## Display-plan formatting must not prevent execution

A reported `invalid_action` with a root `value_error` was caused by the old `Decision.bounded_plan` validator. A blank plan step or a step longer than 180 characters rejected the entire decision before code execution; the length rule was missing from the JSON schema, and the retry received only a root-level error.

The schema now declares plan-item length bounds, and direct validation errors point to `plan` and the item index. Provider-envelope normalization replaces blank or overlong display strings with a fixed short intention. This is only presentation metadata: the tool, arguments, source references, selected account, execution limits and permissions are never inferred or changed. Empty lists, wrong types, excessive step counts, unexpected fields and invalid tool arguments still fail. Valid code can run once and complete without an extra formatting-repair call, even if its accompanying narration is long. Discarded narration is not saved as a result or a run step.

The code-run UI now identifies decision-format failures without advising the student to reconfigure execution. Pull the update, restart FastAPI and use Retry; old failed runs keep their original status. These checks reproduce the reported validator condition with controlled provider/tool responses; they do not substitute for a live Nemotron retest.

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

Last implementation check: 39 focused code-agent checks and 44 frontend checks
passed, alongside the full backend suite (288 passed, two optional OCR skips) and production build.
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


### Windows error 193 during image inspection

Windows error 193 is `ERROR_BAD_EXE_FORMAT`: Windows rejected the selected host
program before Docker could inspect an image. A working `docker` command in
PowerShell does not prove Python selected the same file. Aura now explicitly
resolves **docker.exe** on Windows and refuses extensionless scripts or
`.cmd`/`.bat`/`.ps1` wrappers. Image checks, container launch and cleanup share the
same resolver, without enabling a shell. POSIX systems still resolve `docker`.

Pull the update and rerun the smoke check. If native executable lookup still
fails, get the real path in PowerShell:

```powershell
(Get-Command docker.exe -CommandType Application).Source
```

Set `AURA_DOCKER_EXECUTABLE` in `backend/.env` to that exact returned path (quotes
are allowed around paths containing spaces). Restart the backend and rerun the
check. This setting points to the host Docker CLI; it does not change the
container's `/usr/local/bin/python` entrypoint or the database. No reinstall or
image rebuild is required when the native Docker CLI and image already work.

References:
- https://learn.microsoft.com/windows/win32/debug/system-error-codes--0-499-
- https://docs.python.org/3.12/library/shutil.html#shutil.which
