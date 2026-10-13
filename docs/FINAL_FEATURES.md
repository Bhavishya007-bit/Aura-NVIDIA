# Figures, numerical practice and evaluation

## Multiple-file uploads

Both upload controls accept up to five files in one selection, 100 MiB per file.
Each transfer creates its own durable preparation job. The existing worker
processes jobs through its queue; uploading a batch does not start five competing
model processes. Empty, unsupported and oversized files have separate errors;
one failed transfer does not discard the successful files. Retry failed uploads
only when capacity is available. The backend queue has five active/queued slots
shared across the local application, so other pending jobs can reduce capacity.

Pending job IDs are saved so fast completions are noticed after a refresh.
Browser File objects for failed transfers are not persisted; after reloading,
reselect a file that failed to upload. Uploaded preparation jobs have their own
durable retry button. Each prepared file remains an individual selectable material.

## Figures and diagrams

Click a source citation, open the original PDF page or presentation slide, and
expand **Explain this figure or diagram**. Ask about the visible arrows, axes,
labels or relationships. The protected POST `/study/sources/{id}/figure` endpoint
checks source/course ownership, renders that exact original location, and sends
its PNG to a separate local image-capable Ollama model. A second visual call
checks the proposed interpretation against the same image. Text inside the
image and the student question are treated as data.

Responses separate visible observations, interpretation and limitations. Model
interpretations can be wrong, especially for small labels or dense graphs. This
is on-demand original-page interpretation for PDF/slide figures. New JPEG/PNG
uploads can also index marked, checked visual interpretations; they are not
used as verified numerical answer keys. PDF, PPT/PPTX and original JPEG/PNG
images are supported. PPT previews require the existing LibreOffice setup.
Video-frame interpretation is not added. See IMAGE_AND_ANSWER_QUALITY.md.

Install a local vision model, for example `ollama pull gemma3:4b`, then add
`OLLAMA_VISION_MODEL=gemma3:4b` to backend/.env and restart. Gemma 3 4B supports
images; the smaller 1B model is text-only. This setting leaves OLLAMA_MODEL and
your embedding/GPU configuration intact. CPU can run local inference when a
GPU is unavailable, with model-memory requirements and longer response times.
Two visual model calls can take several minutes on CPU.

## Numerical practice and feedback

In Assessment, choose **Numerical (with units)**. Generation selects an explicit
source-supported formula and builds hypothetical practice inputs. The model
selects the formula; the server computes the key with a bounded arithmetic AST
and dimensional checks. A separate model call checks the stem, formula and
variable meanings against the exact cited source. Unsupported or ambiguous
quantitative relationships are rejected instead of inventing problems.

Supported expressions use addition, subtraction, multiplication, division and
small integer powers of up to six named quantities. Calls, attributes, code,
arbitrary functions, matrices and symbolic proofs are not supported. The unit
table covers basic length, time, mass, amount, volume, concentration, speed,
acceleration, force, energy, pressure and frequency. Unsupported units fail
explicitly. Celsius/temperature offsets and unrestricted compound units are
not supported. Accepted compatible units are converted to SI internally.

The question displays its 1% relative tolerance and small absolute tolerance.
Students enter one number and a supported compatible unit (scientific notation
is accepted). Required physical units cannot be silently omitted. The computed
key and internal numeric specification are hidden before submission. Saved
assessments use the existing transaction, ownership, retry and mastery paths.
Numerical answers use the prototype non-MCQ guessing prior; it is not calibrated
against real student data. No database migration or new app dependency is needed.

Feedback includes the cited formula, calculation and expected result. Numerical
patterns can suggest sign or scale errors. Incorrect MCQ/short-answer responses
may receive a model-generated misconception hypothesis only if it quotes both
the student's answer (selected choice for MCQ) and source evidence. These hints
are labelled possible, can fail or be wrong, and never change the grade.

## Evaluation

`evaluation/demo_material.pdf` is a small self-authored four-page fixture with
two labelled diagrams and two quantitative formulas. Its source generator is
included. `course_cases.json` contains six on-material questions with annotated
pages and two off-material questions. Upload this PDF as a new material before
using the default benchmark; do not apply these page annotations to another deck.
Expand the fixture set with your actual course examples for the final submission.

`collect_live.py` authenticates to the production private API and calls real chat
retrieval/generation. It records responses, validation traces, retrieved context,
latency, location precision/recall, reciprocal rank and off-material refusal rate.
It asks for the account password without echoing it if an environment token is
not supplied. Credentials/tokens are never written into the result file. Do not
use a remote API URL unless you intend to send your account credentials there.

`score_ragas.py` uses pinned RAGAS 0.2.15 with local Ollama judge/embedding wrappers
for faithfulness, answer relevancy, context precision and recall. Use a separate
evaluation virtual environment so app dependencies stay intact. Missing scores
remain null with failure counts; source-only responses are scored so outside
knowledge does not artificially reduce faithfulness. Off-material refusals are
reported separately and should also be manually reviewed. Local model judging
is not an objective guarantee, and the tiny fixture is not representative of a
whole course. The evaluator uses a different model by default from the text tutor.

`simulate_students.py` runs 60 synthetic learners for each of adaptive/random
policies, three initial profiles, eight sessions and five items/session. It uses
the actual BKT update and difficulty thresholds, with a declared synthetic
response/learning process and finite question bank. Reports include per-session
estimated mastery, synthetic latent knowledge gains and repetition rate. Bank
exhaustion intentionally permits repeats. These are policy simulations, not
live-generated assessments, empirical learning gains or evidence of human benefit.

Included simulation results are from seed 42. The live RAGAS report must be
generated on your own running models/material; no model scores are fabricated.
Framework imports/constructors, arithmetic, protected figure transport, source
recovery and frontend controls were tested during packaging using controlled
responses. Actual visual reasoning and numerical generation quality still need
the live checks below.

## Live checks and demonstration

1. Ask a NEW treadmilling question in the original deck. If full paraphrase
   verification fails, its exact definition should remain as partial evidence.
2. Open an original-page citation, ask about arrows/axes, and manually compare
   the observations and explanation with the image. Check an unreadable figure.
3. Upload demo_material.pdf. Generate one numerical question focused on speed
   or force. Try an equivalent unit, an incorrect sign and a missing unit.
4. Confirm the saved report, possible-error hint, source button and mastery update;
   retry a submission and confirm it is not counted twice.
5. Run the live collector, RAGAS scorer and simulations; inspect failed metrics.
6. Record the required 3–10 minute YouTube demonstration using DEMO_SCRIPT.md.

These steps are required before describing the prototype as fully verified.
