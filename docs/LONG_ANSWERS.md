# Length and format follow-ups

The reported sequence was `summarize the ppt` followed by `in 2000 words`.
The second message lost its subject, skipped the overview path and generated
background that incorrectly described the uploaded file as only a brief outline.
The overview path also capped summaries at eight sentences and used a fixed
4,096-token generation budget.

## Resulting behavior

- Length/style-only follow-ups inherit the last substantive user request without
  a model rewrite. Chains of modifiers preserve the topic; newer counts override
  older counts. Named new topics remain new topics. Assistant history supplies
  conversational references, never source evidence.
- Supported modifiers include numeric/comma/k/thousand word counts, simpler or
  deeper explanations, paragraphs, bullets, tables and language changes. The
  latest constraints are passed alongside the question to generation.
- A 2,000-word request allows more sentences and an 8,192-token answer budget.
  Judge clients retain their original budgets. Long or explicitly detailed file
  explanations read across the owned file through `document_context`, rather
  than only the 16-location overview sample.
- Document context is bounded to 96 distinct passages and 80,000 source
  characters, after an owned query of at most 2,048 chunks. Locations get a
  first passage before extra passages are added. Native teaching text takes
  priority over longer OCR/menu text. Scope metadata reports sampling and
  whether all available chunks were included; this is not a claim to understand
  every image in the original file.
- Summary sentences are rendered into paragraphs, bullets or a simple numbered
  table with their source references. A long fallback of checked points is no
  longer cut to six sentences.
- Word counts exclude numeric citation markers. Ordinary word targets allow
  10% variation. A checked draft that misses the target gets one bounded revision
  with its measured count. A still-short long overview with checked evidence may
  then expand through source-scoped sections, as described below. If the target
  still cannot be met, Aura preserves checked content and reports the shortfall;
  it does not invent missing file sections or fill the count with unsupported claims.
- Long answers check nonliteral claims in batches of at most 12, retaining an
  independent result and evidence for every claim. Missing, duplicate or invalid
  decisions cannot approve claims. Literal source statements retain their exact
  membership fast path.

## Operational bounds

The application currently accepts a maximum word target of 5,000 per response
and reports when a larger request is capped. Generation budgets have a default
ceiling of 16,384 tokens, adjustable through `AURA_MAX_ANSWER_TOKENS` in local
backend configuration (bounded between 4,096 and 32,768). The configured model
must accept that output budget. A word target is separate from the token budget;
reasoning and JSON also consume output tokens.

No prompts can guarantee any length for unreadable or insufficient evidence.
Checks measure length and source support separately, and preserve that distinction.
Model-based support decisions still require calibrated live evaluation.

## Validation

```powershell
python -m unittest evaluation.check_phase2 evaluation.check_summary_recovery evaluation.check_tutor_recovery evaluation.check_long_answers -v
```

With the optional local PGlite PostgreSQL engine configured through
`AURA_PGLITE_MODULE`, also run:

```powershell
python -m unittest evaluation.check_lexical_postgres evaluation.check_document_context -v
npm run build
```

Across these modules, 89 tests report 87 passed and two opt-in OCR tests skipped.
The frontend builds successfully with the existing two decorative SVG warnings.
The controlled `summary -> in 2000 words` regression returns exactly 2,000 words,
with valid references across 39 synthetic source locations, without background
or a refusal. This is a controlled model fixture, not a live Nemotron benchmark.

The actual attached 39-slide presentation was converted and its 37 locations
with native text were passed through the real long-context SQL query and
selector in PostgreSQL. All 37 were returned. This test intentionally uses native
text only; previously prepared OCR/figure passages remain available in the real
index. No hosted model or user database was accessed for these checks.

## Apply

Pull `main`, restart the backend, select the already prepared presentation, and
repeat the two-turn request. Existing indexed material can be reused. Live
Nemotron output on the user's database remains the final integration check.

## Diagnose provider failures

The supplied live log shows coverage JSON failing schema validation and two
answer calls rejected as invalid provider responses, before source checking.
Those older log lines did not identify why the responses were rejected.
The subsequent diagnostic reproduction established `finish_reason=length`:
of an 8,192-token allowance, 7,524 tokens were reasoning in one attempt and
all 8,192 were reasoning in the next. Coverage completed without a schema
warning in that reproduction. This establishes answer-generation truncation,
not a new failure to retrieve the presentation.

New `provider=nebius status=invalid_response` lines include `failure_code`, task,
JSON mode, the requested token budget, a bounded finish reason, and numeric
prompt/completion/reasoning usage when reported. Codes distinguish
`output_truncated`, `empty_content`, `content_json`, `content_shape`,
`response_json`, `response_shape`, `completion_shape`, `unexpected_redirect`
and `unexpected_finish_reason`. Missing usage remains unknown.

Coverage and summary schema failures log the error count and at most eight
field paths/types. Unknown field names, input values and validation messages
are omitted; private model responses and credentials are not logged.

Eight controlled failure/redaction regressions are available via
`python -m unittest evaluation.check_llm_diagnostics -v`.

## Reserve output for the long summary

Long file summaries now clone the writing client and request
`reasoning_effort: "none"` for the exact model
`nvidia/nemotron-3-super-120b-a12b`. This is a top-level request field in the
[Nebius chat API](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion).
It is not an OpenAI SDK `extra_body` wrapper or an assumed NVIDIA NIM parameter.
Short summaries, coverage checks, source verification and non-summary deep
answers retain their existing settings. Other routed models keep provider
defaults unless explicitly configured.

Optional `NEBIUS_SUMMARY_REASONING_EFFORT` overrides that policy for long
summaries. Blank uses the model-specific default; `provider` omits the field;
other accepted API values are `none`, `minimal`, `low`, `medium`, `high`, `xhigh`.
No environment change is required for the observed model.

If the first draft still truncates and the provider reports reasoning usage,
the existing single retry adds those measured reasoning tokens to the writing
allowance, respecting `AURA_MAX_ANSWER_TOKENS`. The observed allowances become
15,716 or 16,384 tokens on that retry. Unknown usage is not guessed. Incomplete
JSON remains rejected, and a second failure still returns the honest fallback.
There is no additional retry loop or unbounded output increase. Logs include
the requested effort and actual usage so ignored controls remain detectable.

Eight new controlled regressions exercise the real HTTP parser with both
reported truncations, successful checked 2,000-word recovery, cap enforcement,
missing usage, client isolation and rejection of complete-looking JSON returned
with a truncated finish reason. Run:

```powershell
python -m unittest evaluation.check_summary_reasoning evaluation.check_llm_diagnostics evaluation.check_phase2 evaluation.check_summary_recovery evaluation.check_long_answers -q
```

These 81 checks pass locally. No hosted call was made: model-specific compliance
with the documented effort field and live generation quality still require a
run on the user's configured endpoint. Pull `main`, restart the backend and
repeat the two-turn request using the already prepared presentation.

## Follow-up: successful generation, rejected drafts

The next live run confirmed `reasoning_effort=none` was honored: both writing
calls reported zero reasoning tokens. The first returned 809 completion tokens
and raised a plain `ValueError` while rendering; the second returned an empty
`sentences` list. The old log cannot distinguish which render rule failed, so
it does not prove the first draft's exact contents or cause. Coverage separately
failed because one part referenced more than the previous 24-ID schema limit.

Coverage now permits at most 96 IDs per part, matching the maximum supplied
context, and receives its actual schema and valid ID range. All IDs must still
resolve within the owned passages; booleans, out-of-range IDs and oversized
lists remain invalid. This coverage change does not approve answer claims.

Summary generation receives a `draft_contract` with the actual schema,
per-request sentence cap, allowed source range and total word bounds. A
2,000-word target explicitly requests 1,800–2,200 prose words and suggests about
80 developed sentences. The prompt states that this overrides the brief default.

Redundant inline numeric citations are now canonicalized when all appear in the
point's structured citation IDs. Conflicting or foreign IDs remain errors; the
resulting prose still undergoes the same source-support checks. Render errors
have safe codes: `citation_metadata_mismatch`, `citation_out_of_range`,
`empty_sentence` and `sentence_budget_exceeded`.

Repairs receive the rejected draft and its specific error, with source evidence
kept separate. Schema messages contain paths/types only. A valid short draft
gets measured expansion feedback; if the retry is empty, that checked short
answer survives with an explicit length shortfall. Empty or unverified output
cannot replace it. Draft logs report sentence/word counts without private text.

Ten new regressions cover these failure modes, including 96 valid coverage
references, 2,000-word repair, preserved short drafts and rejection of unsupported
facts despite normalized citation formatting. Run the prior suite plus
`evaluation.check_summary_drafts`: all 91 relevant checks pass. These use controlled
provider responses; the user endpoint still needs to demonstrate live requested
length and quality after restart. No new upload or database migration is needed.

## Follow-up: intact scientific claims and section expansion

The latest visible answer retained only 498 words of checked points and included
`coli) to 25%...`. The prose citation parser split the original statement at the
period in `E. coli`, then checked/recovered only the tail. This failure is
reproducible locally without a hosted model. It does not prove why every other
point in the live draft was rejected; those judge decisions were not supplied.

Structured summaries now keep each model point intact through verification.
The rendered prose, bullets or table must match those exact structured units;
the pipeline cannot verify one statement while displaying another. Each whole
unit still needs valid citations and support for **all** its factual parts.
Recovery rejects unbalanced-parenthesis fragments, keeps original qualifiers
and does not infer missing text. Plain unstructured answers retain their
existing parser. Exact whole-passage membership is also recognized without
splitting scientific abbreviations.

When a file overview requesting at least 1,200 words still falls short after
the existing two draft attempts, and at least one point passed source checking,
Aura can expand by section. It does not start this path when source verification
is unavailable. Native text, OCR and image interpretations from the same slide
or page stay together. Each section receives only its assigned passages with
their original IDs; references to other sections are rejected. A 2,000-word
request over the 39-slide fixture produces four 500-word section targets.

Every section is generated and checked separately, including relevance and
complete-point support. Checked points survive an imperfect section. The two
shared repair calls target the largest remaining section deficits, rather than
rewriting successful sections. Sections are assembled in source order,
deduplicated, formatted using the overall request and counted again. If the
result is worse than the previously checked answer, that prior answer survives.

Expansion bounds:

- At most eight sections and two shared repairs, with at most one repair per
  section. A 2,000-word request uses at most six additional writing calls after
  the two original attempts; a 5,000-word request uses at most ten additional
  writing calls. Successful whole drafts return without any section calls.
- Section writing uses a request-scoped 4,096-token budget within the operator
  ceiling, preserving the summary reasoning control. Judge calls retain their
  existing budgets. Extra calls consume credits and increase latency.
- A 180-second elapsed-time check stops starting new expansion steps. An active
  generation/check retains its existing provider timeout; this is not a hard
  deadline that interrupts in-flight HTTP requests.
- Failed schema checks, foreign references, unsupported points or unavailable
  judges never approve content. A final shortfall remains explicitly visible.

Thirteen new regressions cover intact `E. coli`/`Fig. 2`/decimal claims,
display-to-proof binding, all section sources, targeted repair, unavailable
verification, deadlines and exhausted repair budgets. The controlled sequence
of two 200-word drafts now expands to 2,000 checked words across 39 fixture
locations. This measures orchestration with controlled provider output, not
live Nemotron quality or judge agreement.

Run `evaluation.check_sectioned_summaries` with the earlier suites. The relevant
suite contains 104 passing local checks. The broader retrieval/recovery suite
reports 128 tests: 126 passed and two optional OCR checks skipped. Pull `main`, restart the backend and
reuse the existing prepared presentation. New logs use `summary_section` for
section attempts alongside `summary_draft` and `source_answer_check`.
