# Phase 2: source-aware document answers — first implementation

## Scope and status

The authenticated `/chat` document path now uses `SourceAwareTutor`. It reuses
the existing owner-scoped retriever and citation/relevance verification. The
original image interpretation path is preserved and does not yet return the
new structured contract. Agent execution, web search, durable memory, ingestion
optimization, full UI panels, and a measured production routing table remain
later work. This change does not mark Phase 2's live exit criteria complete.

The current implementation has 27 offline regression checks using controlled
LLM responses and the actual orchestration/citation validators. They test code
behavior, not Nemotron's answer quality. The frontend production build passes;
the pre-existing missing `/images/fieldnote-study.svg` and
`/images/fieldnote-hills.svg` warnings remain.

## Answer behavior

- Fully covered: generate a source-backed answer, verify its claims, and return
  document citations. One repair attempt is permitted if source checking fails.
- Partially covered: answer verified supported parts; label the rest as model
  knowledge when Intelligence mode permits it.
- Not covered: retry broader semantic/lexical retrieval and sample the selected
  document before making a passage-scoped absence statement. In Intelligence
  mode, offer separately labeled model background, without document citations.
- Unknown: retrieval/checking failure or no readable evidence. Never equate this
  with proof that a topic is absent. Background may still be offered with its
  provenance label; document overviews never substitute generic background.

All coverage statements concern retrieved passages, not an exhaustive proof
about a whole document. The retry uses higher top-K, lexical context and diverse
document locations; it is not a guarantee of retrieval recall.

Request fields:

```json
{
  "question": "Explain this idea and its applications.",
  "course_id": 1,
  "source_id": 2,
  "answer_mode": "intelligence",
  "depth": "beginner"
}
```

`answer_mode` accepts `grounded` or `intelligence`. Omitting it preserves the
legacy `include_related_background` mapping. Explicit requests such as "use only
my material" select Grounded mode. Agent is not exposed until tools exist.
`depth` accepts beginner/standard/advanced. Without it, simple/deeper requests
adjust this answer's instructions. "Go deeper" does not save a lasting preference.
Clear prompts should receive no clarification; an ambiguous one can receive at
most one, alongside an answer. This semantic decision still needs live judge
calibration. Structural checks alone cannot establish that a question was clear.

Existing response fields (`answer`, `sources`, `citations`, `citation_validation`)
are preserved. Added fields are:

| Field | Meaning |
| --- | --- |
| `response_schema_version` | `aura-answer-v1` |
| `coverage` | Status, supported/missing parts, scope, retry count, ambiguity |
| `sections` | Sourced or beyond; explicit provenance and verification |
| `mode`, `depth` | Effective settings for this answer |
| `clarifying_question` | Null or one question, only alongside an answer |
| `follow_up_options` | Text suggestions; full interactive UI is Phase 4 |

Coverage and section schemas live in `backend/ai/answer_contract.py`. Stable
system prompts and the depth policy live in `backend/ai/prompts/v1/`.
Only sourced sections can contain document citations. Beyond sections are model
knowledge and explicitly not web verified. Tavily references will need a separate
web provenance type when research tools arrive. Failed source verification never
publishes an unchecked draft as a sourced answer.

## Models and cache measurements

`NEBIUS_MODEL` remains the tested default. Optional candidate overrides:

```dotenv
NEBIUS_COVERAGE_MODEL=
NEBIUS_ANSWER_MODEL=
NEBIUS_DEEP_MODEL=
```

Blank values keep every role on the default model. Coverage checks use the
coverage role; advanced-depth generation can use the deep role if configured.
Existing relevance and claim verification retain the default client. No claim
is made that a candidate tier is better until benchmarked. Lightning/Super/Ultra
assignments are candidates, not measured recommendations.

System instructions precede the changing user payload. Successful calls log
model, task, latency, input/output tokens, cached tokens and a cache-hit indicator.
Missing cache usage stays unknown rather than being counted as a cache miss.
Do not use a different model solely because a user requests more detail.

PowerShell, from the project root:

```powershell
python -m uvicorn backend.main:app --reload 2>&1 | Tee-Object -FilePath aura-backend.log
```

Then, in another terminal:

```powershell
python -m evaluation.summarize_llm_logs aura-backend.log
```

This reports measured request hit rate and cached-input share. It does not infer
cost savings or promise a cache hit.

## Verification and live evaluation

Offline checks, no credentials or database required:

```powershell
python -m unittest evaluation.check_phase2 -v
npm run build
```

Both synthetic suites contain 10 fully covered, 8 partial and 10 not-covered
questions, with development and held-out splits:

- `coverage_cases.json`: text-only fixture for comparing coverage models.
- `course_cases.json`: the existing four-page `demo_material.pdf`, for full API
  collection. Use a clean evaluation workspace containing only that fixture.

Do not use holdout cases to tune prompts. The samples are small: report counts
alongside rates. A false-absence rate at or below 5% here does not establish a
population error bound. The denominator is all gold fully/partially covered
cases; unknown/failed outcomes are reported separately and are not successes.

The following calls spend API credits and must be run only with a newly rotated
key in local `backend/.env`. No live calls were run during this implementation.

```powershell
python -m evaluation.evaluate_coverage --live --models nvidia/nemotron-3-super-120b-a12b --split development
```

Pass multiple exact model IDs to compare candidates. This reports classification
and latency over fixed evidence. It is not a complete routing benchmark: source
answer quality, token/cost totals and human judge agreement are still required.

After uploading the synthetic PDF to an evaluation account, substitute its IDs:

```powershell
python -m evaluation.collect_live --course-id 1 --source-id 2 --split development
```

The collector records the coverage matrix, false absences, API failures,
provenance checks, clarifications and depth. Source-support checks are the runtime
model judge's decisions, not independent human validation. Manually label judge
outputs before trusting them. Do not use the old refusal metric as the success
criterion. Never commit private evaluation responses or API credentials.

## Operational note

A credential-like value was removed from the tracked environment template.
Revoke/rotate that key: deleting it from the latest tree does not remove history.
Keep the replacement only in untracked local configuration. Git history was not
rewritten. The database and its existing users/materials are not migrated by this
change, and no background jobs or code-execution tools are introduced here.
