# Aura's active learner model

This milestone connects learner evidence to the signed-in workspace. It is
implemented in `backend/learning.py`, with persistent PostgreSQL state in
`aura_topic_mastery` and an audit trail in `aura_learning_evidence`.

## Evidence and update method

The server uses the topic and question kind stored with a verified question,
and its graded answer. The client cannot submit a mastery value, correctness
flag or topic label. MCQs are checked against their stored key. Short answers
use the existing source-based model grader; that grader is fallible and fails
closed when its response is invalid or unavailable.

The fixed Bayesian knowledge tracing prototype starts each topic at P(known)
= 0.20. Given a correct response, posterior P(known) is:

`p * (1 - slip) / (p * (1 - slip) + (1 - p) * guess)`.

For an incorrect response it is:

`p * slip / (p * slip + (1 - p) * (1 - guess))`.

Slip = 0.10, guess = 0.25 for four-option MCQs and 0.05 for short answers.
After quiz or tutor-check feedback, a transition of 0.10 is applied:
`posterior + (1 - posterior) * learn`. Diagnostics use learn = 0 to estimate
starting knowledge without crediting a learning transition. Probabilities are
bounded at 0.001 and 0.999 for numerical stability.

These are declared prototype assumptions, not parameters fitted to student
data. The model version is `bkt-fixed-v1`. Changing them requires a versioned
replay/migration, not silently applying a different rule to existing states.
See [BKT parameter discussion, EDM 2024](https://educationaldatamining.org/edm2024/proceedings/2024.EDM-long-papers.2/index.html).

## Adaptation

- Fewer than three observations or mastery below 0.40: beginner.
- Otherwise, fewer than five observations or mastery below 0.75: intermediate.
- Otherwise: advanced.
- Mark estimates based on fewer than five answers as limited evidence.
- With no selected focus, adaptive practice targets the weakest recorded topic
  associated with the selected material. With an explicit focus, it uses the
  matching topic's state; an unknown focus starts at beginner.
- A source-verified focused adaptive question keeps the target's canonical
  topic label, preventing a newly generated subheading from losing its history.
- Tutor style uses matching topic evidence to adjust depth; source retrieval,
  factual grounding, refusal logic and requested answer format remain in force.

Topics are shared within one student's course. Case and whitespace variants
merge; unrelated topics are not stemmed together. Semantically synonymous
labels may still be separate. A future curriculum map can supply stable IDs
and explicit concept/prerequisite relationships.

## Conversation evidence and diagnostics

Tutor's understanding check asks one verified short-answer question. Its
answer is graded and recorded as conversation evidence. Plain chat questions,
reading explanations, elapsed time, or a student's "I understand" assertion do
not raise mastery. Arbitrary free-form chat is not automatically graded.

A diagnostic samples available passages across the selected material and
requests distinct supported topics. Source verification or duplicate exclusion
can return fewer than five questions. It only establishes evidence for tested
topics; it does not certify coverage of the entire course.

## Persistence, ownership and recovery

Every profile and artifact endpoint sits behind authenticated course/material
ownership checks. Mastery and event queries also filter student and course IDs.
An event is unique for learner, course, assessment and question ID. Result,
evidence and mastery writes share one transaction. An artifact row lock protects
submission retries; a transaction advisory lock for the learner/course protects
simultaneous submissions of different artifacts. The grade is never accepted
from the client.

Backend startup applies an additive SQL migration and imports old account-owned
assessment results in completion order if their events are absent. It uses the
stored grade without calling a model or changing old results. Historical manual
quizzes use the same declared quiz update rule. Authentication settings, uploads,
embedding models and preparation jobs are untouched.

## Validation and remaining work

Controlled API/database-double tests cover evidence updates, duplicate retries,
rollback, unknown-focus behaviour, source scope, grading failure, hidden keys,
and account boundaries. React interaction tests cover diagnostic actions,
mastery display, restored tutor checks and checked replies. The frontend proxy
is tested against a local upstream server. SQL is parsed as PostgreSQL syntax,
and the TypeScript/Vite production build is checked.

Real PostgreSQL concurrency, startup import on the user's database, local
Ollama grading and explanation quality still require a live test. No real CUDA
execution or measured student learning gains are claimed by this milestone.

Numerical questions now use bounded arithmetic/unit checks and the non-MCQ guess
prior. Possible misconception hints are separate from grading. On-demand visual
interpretation, a local RAGAS runner and multi-session simulations are available;
see FINAL_FEATURES.md for their limits. Included simulated gains are synthetic;
live course/model evaluation and the demonstration recording remain necessary.
Exact source navigation uses the protected original-file viewer.
