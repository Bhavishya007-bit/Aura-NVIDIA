# Code & data agent

The Study Plan workspace now includes **Code & data**. Describe a calculation,
algorithm experiment or small CSV analysis. Aura writes Python, executes it, reads
the captured output and explains the result. It can correct code once. This is a
bounded code-analysis skill, not a terminal, package installer or full IDE.

## Teaching explanations and observed evidence

The explanation step now receives the actual program associated with each execution, alongside the captured stdout/stderr. Previously its context contained execution results and file metadata but omitted the program body. This matters when explaining loop bounds, early exits, copies, comparison counts and failed/corrected attempts.

Program text is bounded to 6,000 characters per attempt, and stdout/stderr context to 4,096 characters each. Context shortening sets explicit truncation flags while leaving the full saved execution record and downloads unchanged. Code/comments/output stay untrusted data, and artifact bytes are still stripped from model context. Existing token, time and execution-attempt budgets remain in force.

The code-only teaching policy asks for a worked example, actual printed trace/results, assumptions and complexity. Search examples should print each target/index/count and assert membership consistency. Sort examples should print a short pass/swap trace and assert against a trusted sorted copy. Algorithm comparisons should prefer defined operation counts; explicitly requested timings require repeated trials, suitable sizes and measurement caveats. Copies, recursion and stored traces must be distinguished from an algorithm's auxiliary-space bound.

Before publishing an explanation, Aura now makes a separate, strict JSON review call against the latest executed program, captured output and any retrieved document evidence. The reviewer checks results, traces, count/timing semantics, assumptions, file-inspection claims and execution status. It must not trust comments or instructions in the supplied data. A review flags unsupported wording such as calling the sixth element the middle, calling an inferred walkthrough observed, or interpreting loop counters as elapsed time.

A flagged draft can receive **one text-only revision followed by one recheck**. This means one additional model call for a clean draft, or at most three for review/revision/recheck. It adds latency and uses the existing API credits, step/token/time budgets and cancellation checks. Every call has `max_retries=1`; code is never rerun to fix prose. The final save also needs a step, so a deliberately tiny run budget can stop before a checked explanation is ready.

Rejected, malformed or unavailable reviews do not release the draft as the answer. Actual Python output and authenticated downloads remain available with a clear recovery message. Only a checked final answer is saved as result text; rejected drafts are not stored as run actions. The UI shows **Checking your explanation** during this work. Existing saved answers retain their text; start a fresh run or regenerate to use this path.

This is a model-based review, **not a deterministic proof of arbitrary explanations**. The reviewer can make mistakes and has not been calibrated against independent human labels. Results remain `verified=false`; live model quality still needs review. Cancellation and exhausted budgets cannot publish a late or unchecked answer.

### Local checks for a confirmed reviewer miss

A completed three-step run showed that the model reviewer approved an answer labelling 23 as the middle of a nine-element list whose middle was 16. It also approved an unqualified comparison conclusion despite a table row where linear search used fewer checks. This is recorded as a reviewer false acceptance, not an installation/version problem.

`backend/agents/explanation_checks.py` now checks internal consistency for recognized English claims about an explicit small numeric list: first/last/absent labels and the middle of an odd-length sorted list, including parallel target/label lists. A second check detects an unqualified empirical "results confirm binary uses fewer" claim when the answer's one comparison table supplies a contrary row. Numbers are parsed as bounded decimals; generated programs are never executed for these checks.

These findings force the corresponding review verdict to false even if the model approves. They enter the existing one-revision/recheck path, with no extra model calls or Python execution. An unchanged contradiction after revision is withheld despite another model approval. Regression tests replay the reported answer with deliberately approving model responses, and verify one execution, bounded calls and preserved output.

The checks establish contradictions **within recognized answer text**, not truth of its data relative to execution. Unknown syntax/languages, dynamic or oversized lists, multiple distinct arrays/tables, even-length middle interpretations, and other kinds of claims remain outside this guard. The separate model review still compares the explanation with execution evidence. This narrows a demonstrated failure; it does not make arbitrary explanations verified.

### Timing-only experiments

A later answer reported correct indices and `0.00s` times, then added unrecorded comparison-count estimates and attributed the lack of a visible timing difference to `perf_counter` precision. The execution-aware guard now recognizes search reports containing indices and times. When the visible output provides no counter labels or traces, concrete numerical comparison claims and count tables trigger correction even if the model approves them. The editor removes these unsupported estimates and can retain qualitative complexity; it does not rerun Python to repair prose.

When all displayed times are zero, recognized claims that the timer lacks precision or that observed searches finished in microseconds/nanoseconds are also flagged unless supporting clock/duration evidence is visible. A `0.00s` display alone cannot establish clock resolution or those durations. Actual counters/traces permit count discussion, and precise recorded durations permit corresponding timing discussion; the model reviewer still owns correctness of those claims.

Tests replay the reported timing answer with approving model verdicts and check both successful correction and withholding of a repeated failure. These checks use the same bounded review/revision/recheck allowance and introduce no additional calls, dependencies or API fields. They are conservative English-pattern checks for recognized timing reports, not proof of arbitrary performance claims. Other output formats and kinds of claims still need model and human review.

### Duplicate wording and a reviewer batch audit

Returning any matching index handles duplicates; it does not promise the first or last occurrence. A narrow whole-clause check now flags the reported self-contradiction, “Does not handle duplicate values (returns any match).” It leaves “duplicates were not tested”, correct first/last limitations, quoted corrections and other unknown wording to the reviewer. An approving model cannot override this finding. The existing single text revision/recheck repairs it without executing Python again.

To measure more than individual examples, explicitly run this optional local audit:

```powershell
python -m evaluation.code_quality --collect-live
```

It makes at most **eight paid-provider requests** using the configured production review model, reasoning settings, strict schema and evidence compaction. Each request has one attempt, a 1,024-token output budget and a read timeout of at most 30 seconds. It does not execute Python, invoke tools, revise answers, access student records or query the database. Synthetic program/output pairs cover position/table errors, timing claims, duplicate semantics and CSV arithmetic. They are authored fixtures, not new sandbox execution results. An optional `--model EXACT_ID` compares another model; use a new `--packet` path for each collection.

The ignored `evaluation/results/code_quality.json` is checkpointed after every request and existing packets are never replaced by collection. It contains requests, valid model verdicts and verdicts after local checks. Malformed outputs/provider failures are recorded as unknown using a fixed error, with no raw error text. The summary separates model false acceptances from failures caught by local rules. The CSV pair deliberately tests arithmetic outside these rules. Do not treat fixture agreement as human calibration or general teaching accuracy.

Read each program, output and draft independently, then record a person's judgment explicitly:

```powershell
python -m evaluation.code_quality --review-case csv-bad --label unsupported
python -m evaluation.code_quality
```

Labels are `supported` or `unsupported`; all eight start unlabelled. The report shows human agreement only for labelled cases, separately from assistant-authored expectations. Eight synthetic cases are a diagnostic sample, not a release-quality claim. This audit has been tested with controlled model responses; no live model accuracy is claimed from those tests. It does not replace Phase 4's separate 30-output coverage-judge calibration. No application API, database field or dependency is added.

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
