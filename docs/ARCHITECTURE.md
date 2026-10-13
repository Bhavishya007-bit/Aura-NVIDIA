# Aura prototype architecture

React/Vite uses the existing bearer-authenticated API client and a route-limited
proxy to the private FastAPI application. Students see only their own course,
source and assessment data. PostgreSQL stores source chunks, embeddings, study
artifacts, quiz results and per-topic learner evidence.

## Source tutor and original navigation

Upload/preparation workers extract document, slide, OCR and transcript text.
Chunk origin fields preserve page, slide or timestamp. Scoped semantic retrieval
is supplemented by exact concept matches and adjacent pages/slides. The tutor
checks citation numbers, question relevance and claim support. If a full answer
fails, an exact named-concept definition can remain as explicitly partial source
evidence. Outside explanation is separately labelled and consistency checked.
It does not become a verified source claim or a learner observation.

Citation buttons preserve their source numbers and group identical original
locations. Authenticated source-viewer endpoints resolve files only under the
backend upload root. PDF/PPT previews render originals in isolated workers;
presentation conversion includes hidden slides to preserve slide numbering.
On-demand figure requests send the displayed rendered page to a separate local
vision model and check the interpretation against the same image.

Standalone JPEG/PNG material uses bounded image decoding, OCR and optional
vision interpretation during ingestion. Indexed visual text is explicitly
marked model-generated; its source location opens the original image. English
tutoring uses compact intact source sentences and checks output language. The
selected file identity is supplied to relevance checking, and failed generation
gets a checked compact-synthesis pass before short labelled evidence fallback.

## Assessments and learner model

Source-backed generation creates MCQ, short-answer or bounded numerical items.
Novelty checks compare earlier questions. Numerical keys are calculated in code
after source-formula and dimensional checks. Public assessment payloads remove
keys, explanations, internal formula specifications and evidence quotes until
submission. Server grading determines correctness; misconception hints are
separate tentative feedback and cannot change the grade.

The existing submission transaction locks the artifact, saves one result, and
updates BKT evidence/mastery atomically. Unique learner/question events prevent
duplicate updates. Diagnostics establish limited initial evidence; checked tutor
answers and quizzes update mastery. Simply reading a tutor/figure explanation
does not. Numerical items use the non-MCQ guess prior. BKT parameters are fixed
prototype assumptions, not calibrated estimates of individual knowledge.

## Evaluation boundary

The live collector calls the same private API as the UI on manually annotated
course fixtures. Pinned RAGAS evaluates real stored responses using local judge
and embedding models. Synthetic multi-session evaluation compares two selection
policies using the production BKT update, with declared latent-learning assumptions.
Controlled test results, live model metrics and synthetic learner gains must be
reported separately. The video demonstrates real local operation and remaining
limitations; no live scores are claimed before those runs finish.
