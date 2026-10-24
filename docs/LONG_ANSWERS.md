# Length and format follow-ups

## Live 2,124-word result: length passes, integrity work remains

The matching answer and backend trace confirm the actual application count:
1,603 sourced words plus 521 separately labelled background words = 2,124, within
the 1,800–2,200 range. The configured Ultra model ran with `reasoning_effort=none`.
Background was enabled, its first draft was rejected, and a revised draft passed
model review. This run was not stopped by output truncation or a credit limit.

The trace also reveals remaining issues. Coverage returned too many parts;
the topic outline failed partition validation and used the page-order fallback;
the last of six source sections failed relevance checking twice and was omitted.
The final background brought the word count into range but did not restore those
missing source topics. Reaching a word target must not imply a complete summary.

Coverage-list overflow can now receive one format repair, asking the model to
group requested topics within the existing 12-part limits. The server never
truncates missing/covered parts or accepts a negative verdict by rerolling it.
An invalid outline partition can receive one repair with explicit allowed location
IDs, schema bounds and the required section count. The accepted partition still
must include every location exactly once. Repeated invalid output uses the safe
fallback. Connection, schema and provider failures do not create retry loops.

Section expansion now reports checked/missing section counts in its existing
validation diagnostics. When a selected expansion has an empty section, the
student gets a plain-language notice that source parts were omitted, regardless
of the combined word count. This does not publish rejected claims or bypass the
relevance judge; full source completeness remains a separate concern.

Grouped inline reference markers such as `[1,2]` were not recognized by the
single-ID citation parser and survived inside a source point. They are now
rejected before publication, including in recovery and background. The server
does not guess what ambiguous numbers refer to or silently rewrite source data.
Models must put source IDs only in citation metadata; the renderer emits the
canonical `[1][2]` form. Grouped numeric arrays inside inline/fenced code remain
data. Ambiguous numeric groups in prose require an explicit formatting repair.

The response also contains conflicting transport-direction explanations and
unsupported quantitative extrapolation from a hypothetical composition ratio.
Background review now explicitly compares both sections: an outside correction
must identify the source statement it corrects instead of silently contradicting
it, and a ratio alone cannot establish a measured diffusion rate or distance.
Manual checks used primary research on
[P4-ATPase phosphatidylserine transport](https://pubmed.ncbi.nlm.nih.gov/31371510/)
and [mitochondrial presequence structure](https://pubmed.ncbi.nlm.nih.gov/10721992/).
This inspection concerns the generated response, not an independent verification
of every uploaded slide. Model review remains fallible and uncalibrated; stronger
instructions and a positive verdict are not proof of scientific accuracy.

`evaluation.check_summary_live_followup` covers controlled reference rejection,
code-literal preservation, bounded structural repairs, truthful partial-summary
notices even at 2,124 words, and the review context/requirements. These are
protocol regressions, not a live error-detection benchmark. No private uploaded
answer or material is committed as a fixture. Existing model settings can stay;
pull the update and restart FastAPI before the next live check.

## Short source-only result after the routing fix

The 937-word follow-up is a checked-point result with no background section.
Its prose repeats the same hash-table definitions, and it does not meet the
2,000-word request. There are no matching backend logs, so the response does not
identify whether background was disabled, blocked by source-only mode, rejected
by review, or interrupted by the provider. Do not call it a successful length fix.

Code inspection found a separate configuration inconsistency: the source writer
uses `for_summary()`, but the background writer previously bypassed it. Background
writing now applies the same `NEBIUS_SUMMARY_REASONING_EFFORT` setting without
mutating the base, coverage or reviewer clients. The quality profile sets `none`;
explicit operator choices such as `low` or `provider` are still respected.

A truncated background writing response can use the already permitted second
writing attempt. It requests the complete final text again and can reserve only
measured reasoning overhead within the existing operator token ceiling. Partial
provider text is neither published nor submitted to the reviewer. Truncation
twice still withholds background. A review failure never restarts the writer or
rerolls a negative verdict. No source/accuracy checks or budgets were removed.

Long-summary logs now distinguish `summary_background=skipped` with fixed reasons
(`disabled`, `source_only`, `excerpt_only`, `no_checked_summary`, `length_met`,
`no_remaining_budget`) from `start`, `rejected`, `generated` and `withheld`.
Unavailable calls record the stage (`configuration`, `generation`, `validation`,
`review`) and a fixed failure category. These diagnostics never include student
text, keys, filenames, reviewer comments or arbitrary provider error bodies.
They establish what actually ran before any further quality or model changes.

The wire-level regressions in `evaluation.check_background_reasoning` use real
request serialization and response parsing with authored HTTP responses. They
check a 937+1,063-word shape, reasoning settings, bounded truncation recovery,
review failure, source-only/disabled policy and redaction. They do not establish
live Nemotron accuracy or imply that adding arbitrary prose meets teaching goals.
For the intended summary-plus-background behavior, enable the existing profile
and restart the backend:

```powershell
python scripts/configure_model_quality.py --apply
uvicorn backend.main:app --reload
```

`--apply` makes no model request and keeps credentials/database settings. It
selects the profile's documented Ultra configuration and enables separately
labelled, model-reviewed background; it does not bypass explicit source-only
requests. If the next answer is still short, inspect the matching
`summary_background=` lines and provider logs, rather than infer a cause from
the word count alone.

## Broken PDF wording and selected-file binding

`Summarize the P indf 2000 words.` did not match the document-summary
detector, so it could enter ordinary question answering and finish with only a
verification notice. With a selected material, the Tutor now repairs narrowly
defined split PDF references (`P indf`, `p df`, `p d f`, `pd f`, `PDFin`) only
after an explicit summarize verb and only when the remainder consists of format
constraints. It does not guess filenames, subjects, standalone `P`, or topical
restrictions. The original user message remains available unchanged.

An already explicit generic selected-file summary no longer goes through the
conversation rewrite model: "this PDF" refers to the selected file, even if old
messages discuss something else. Named topic questions and actual conversational
references keep their existing resolution. Owned document retrieval, length
budgets, citation checks and source-preserving quote recovery remain in force.
No selected file means no inferred binding or correction.

The controlled regressions in `evaluation.check_summary_request_typing` exercise
the reported wording through full document retrieval and a measured long answer,
plus stale history, failed-writer quotation recovery and negative routing cases.
These tests establish routing and recovery behavior, not live provider accuracy.
The displayed notice alone contains no provider failure trace; if it persists
after updating, inspect the matching `tutor_request`, `summary_draft`, `source_answer_check` and
`source_answer=unavailable` log entries before changing model settings.

## Background review and the 2,343-word follow-up

The attached follow-up contains 1,105 sourced words and 1,238 background words,
for 2,343 total. Source/background labels worked, but the total exceeded the
2,200-word upper bound. It also contained incorrect generalizations and runtime
claims. A model-knowledge label is provenance disclosure, not an accuracy check.
The attachment has no provider trace; it does not establish which model or call
produced the answer. Do not infer those details from the prose alone.

Background writing now follows the actual requested depth, preferring a simple
valid worked example over unsourced runtime/version claims, cache counts or
implementation thresholds. It receives a separate model-based review for
accuracy, relevance and scope. A negative verdict permits one corrected draft
and one new review; an unchanged rejected draft cannot reroll its verdict.
Malformed/unavailable checks or a repeatedly rejected revision cannot publish
that draft. A previous approved short background may remain as a fallback.
Background remains `verified=false` and **not web verified**. The reviewer can
make mistakes; these changes are not external fact verification or calibration.

The final source-plus-background count is checked together. If a draft exceeds
the total upper bound, only complete trailing paragraph/fenced blocks may be
dropped before review. The selected prefix is then reviewed exactly as displayed;
there is no shortening after approval, partial-sentence slicing, source rewrite
or citation remapping. An overlong unsplittable block gets the existing single
revision opportunity and is otherwise withheld. Safe partial output keeps an
honest shortfall notice. This does not guarantee exact length for every model.

The added review costs at most two small review requests per background lesson,
plus the existing targeted JSON-truncation recovery where applicable. The limit
of two background writing requests remains unchanged. There are no new routes,
database fields, dependencies or changes to the strict source-only mode.

The regressions in `evaluation.check_background_review` replay the reported word
counts with independently authored text, reject partial code/heading cuts, and
enforce controlled negative verdicts for the reported claim types. The negative
verdict fixtures do not establish that a live reviewer catches those errors.
Manual findings were checked against primary references: Python's
[hashability glossary](https://docs.python.org/3/glossary.html#term-hashable),
[dict complexity](https://docs.python.org/3.14/builtins/time-complexity.html#dict),
and [PEP 456](https://peps.python.org/pep-0456/). The actual uploaded response and
private material are not committed as test fixtures.

## Quality profile and separately labelled teaching depth

The next attachment contains a 1,112-word answer after the earlier 1,110-word
answer. It contains no backend diagnostics, so it does not identify which
provider call or verification step prevented completion. Both answers repeat
several definitions; counting words alone is not a teaching-quality check.

The quality profile uses the exact model ID documented by Nebius:
`nvidia/Nemotron-3-Ultra-550b-a55b`, through the `us-central1` endpoint. It selects
Ultra for the base, coverage, answer and deep roles, sets normal writing budgets
to 16,384 tokens, allows a 32,768-token operator ceiling, and uses a 180-second
provider read timeout. Writing and verification use the Token Factory API's
`reasoning_effort: none` control so their output allowance is available for the
requested text/JSON; this does not make source verification optional. Generic
deep reasoning calls keep their existing provider-default reasoning behavior.
The optional smoke test checks access, JSON format and the configured reasoning
control with one small synthetic request. This environment has no account key,
so model access and live improvements must be checked locally. No silent model
downgrade occurs if Ultra is unavailable.

```powershell
python scripts/configure_model_quality.py --apply --smoke
```

With both flags, the smoke test runs before changing configuration; a failed
check keeps the previous working settings. The command atomically updates only
profile settings in `backend/.env`. It preserves
keys, database configuration, comments and unrelated settings; it never prints
credentials or provider response bodies. Existing shell environment variables
still take precedence. Restart FastAPI after applying it. The command makes no
provider request without `--smoke`; that option spends one small paid request
without uploading student material. Run `git pull origin main` first.

The profile enables `AURA_SUMMARY_BACKGROUND=true`. When a checked long overview
still falls short, Aura may add a separate **Beyond your material — model
knowledge, not web verified** lesson. It explains related mechanisms, assumptions
and clearly hypothetical examples without claiming they appear on unseen slides.
It receives the remaining word target and at most one length revision. Only the
sourced section carries uploaded-material citations; background stays
`verified=false`. This is a combined summary and additional lesson, not a claim
that 2,000 words came from the file. A source-only request ("using only my
material") or grounded mode always disables it. It also stays off for excerpt-only
fallbacks and answers with no checked summary. The default policy is off until
explicitly enabled in configuration, including by the profile command.

The profile increases section recovery to at most six shared replacement drafts
and a 300-second elapsed-time allowance. Operator bounds are 0–8 repairs and
30–600 seconds; each section still gets at most one repair, and active requests
retain their own timeouts. It does not remove agent step limits, cancellation,
account isolation or source checks. More time and model capacity are options,
not evidence that the final explanation is correct or sufficiently detailed.
Live cost, latency and teaching quality must be measured separately.

Provider references: [Nebius Ultra model guide](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-ultra-550b-a55b.md),
[Token Factory chat API](https://docs.tokenfactory.nebius.com/api-reference/inference/create-chat-completion).

## Current recovery: topic-led complete sections

The latest reported answer reached 1,110 words but repeatedly redefined hash
tables, collisions and collision resolution. Longer output did not establish
better teaching. The append-only recovery kept a compact overview and added
paraphrases around it; exact-text deduplication could not prevent that pattern.

Recovery now makes **one bounded outline request**, grouping related locations
under distinct teaching topics (including nonadjacent pages). The server checks
that every supplied location is assigned exactly once, that all IDs exist, and
that titles are unique. Native text, OCR and image interpretations from one
location stay together. A malformed outline falls back to page-order sections;
a connection failure stops recovery. An outline is organizational context,
never source evidence, and its headings are not rendered as verified claims.

Each writer produces a **complete section**, normally around 333 words across
six sections for a 2,000-word request. Its repair rewrites that section instead
of appending more prose. The original checked overview stays with the caller as
a fallback and is not prepended to the new lesson. Completed sections are given
as context, without source IDs; the existing relevance check now also rejects
sections that merely paraphrase them rather than developing their assigned
focus. Brief bridges and substantive elaboration are allowed. Per-point source
support and local citation remapping still run independently. This model-based
focus check needs live evaluation; a controlled test is not proof of reliable
semantic deduplication.

Topic paragraphs stay separate in ordinary prose. Requested bullet/table or
paragraph-count layouts retain their existing behavior. The writing prompt asks
for mechanisms, relationships and supported examples, and for preserving the
source's qualifications instead of converting simplified statements into
universal guarantees. It does not silently insert outside corrections under
uploaded-material citations. Repeated same-page passages that differ only by
known extraction headers are deduplicated; distinct evidence, image uncertainty
and identical text on different pages are retained.

After the two existing whole-file attempts, recovery can make one outline call,
six section calls and two shared repairs for a typical 2,000-word request:
**up to nine extra generation requests**, plus independent verification. Across
all supported lengths, the limit is one outline, eight sections and two repairs.
The 180-second elapsed-time checks still stop new work, without interrupting an
in-flight provider request. This costs more calls than the previous four-section
path, only when the initial drafts fall short. Unavailable verification or a
lost connection stops new writing. Failed or worse repairs retain the checked
predecessor; a shorter overall rewrite cannot replace a longer checked overview.
No new API routes, database fields, dependencies or retry loops were added.

The regressions in `evaluation.check_summary_topics` cover grouping nonadjacent
repeated concepts, invalid partitions, redacted diagnostics, connection loss,
complete replacement, repeated-topic rejection, failed rewrites and extraction
header duplicates. Existing controlled recovery fixtures still reach roughly
2,000 words with valid source bindings. These fixtures do not establish live
Nemotron length, factual accuracy or teaching quality on the uploaded PDF.
Human judge calibration remains pending. The real-material check below remains
required before declaring the long-summary issue resolved.

The diagnostics later in this document describe earlier releases; this section
supersedes their append-only and four-section recovery behavior.

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

## Recovery after two unusable whole-file drafts

The repeated short-excerpt path had a separate gate: section expansion required a positively checked sentence from an earlier generated draft. When both whole-file drafts were empty, malformed or truncated, the application could retrieve ample material yet stop at exact excerpts without attempting section-based synthesis.

Long overview requests of at least 1,200 words now also allow the existing bounded section path after those recoverable generation failures or rejected whole-file prose. Every new point still passes the same relevance, citation and source-support checks. Only retrieved source passages supply facts for the rewritten explanation; raw excerpts, rejected claims and assistant history never become new source evidence. The prior checked answer remains a separate fallback. A file with no short literal excerpt can also start from its retrieved passages. Foreign-section citations remain invalid.

The current limits are one outline request, one initial writing call per section, and two shared repairs, at most eight sections, with the existing elapsed-time checks. A 2,000-word request normally creates six sections, so recovery can add up to nine generation requests plus source-verification requests after the two initial attempts. It uses existing provider credits and adds latency only when recovery is needed. Network failures do not trigger this bootstrap, and a connection lost during expansion stops further writing calls. An unavailable verifier also stops recovery. If no supported improvement is produced, the checked answer or exact excerpts remain, with an honest length shortfall.

`python -m unittest evaluation.check_summary_bootstrap` reproduces the initial failure with controlled empty/truncated/rejected drafts and verifies a 2,000-word source-backed recovery across 39 synthetic locations. It also checks unavailable verification, connection loss, preserved checked drafts, and bounded failure with excerpts. These are orchestration regressions, not evidence that a live model will always reach the requested length or understand every diagram. No API route, database schema or application dependency changes.

## Citation scope and the 287-word live result

The supplied live trace at `e036c48` identified concrete losses: whole-file drafts had 404 and 199 words, sections 1 and 2 were rejected with `citation_outside_section`, section 3 added 88 checked words, and section 4 ended with `verification_unavailable`. The retained 199-word seed plus those 88 words explains the 287-word answer. These calls finished without output truncation. The trace did not include raw model drafts or the exact malformed verifier response, so it does not establish which returned IDs were wrong.

Section generation and verification now use an explicit local `1..N` citation namespace. The server keeps the mapping to original passages, and remaps only positively checked points before rendering the final global citations. Existing checked context is sent without citation IDs, and prior conversation text is omitted from the section-writing prompt to avoid mixing citation namespaces. This is a declared protocol, not a guessed repair of invalid citations. Out-of-range IDs remain rejected; checking still uses the actual selected source passages.

Verification batches also use local `1..N` claim IDs and explicitly map decisions back to the original claim indices. Missing, duplicate, extra or malformed decisions still invalidate the entire batch. Safe `citation_batch=unavailable` codes now distinguish response shape, size, claim-ID and value errors without logging document or model text. An unusable verifier still stops expansion and cannot approve added prose.

Long overview and section writing use `summary_long.txt`, which has no brief-summary default or short-sentence example. It asks for explanatory development of supported concepts and allows elaborating an earlier brief mention while rejecting duplicate padding and invented source facts. The short-summary prompt is unchanged. Call and output limits are unchanged; this does not add a verifier retry loop or claim that a live word target always succeeds.

The controlled citation-scope replay previously failed when section citations restarted at 1; it now produces 2,000 words with each final citation tied to its correct original passage. Other tests cover shuffled batch decisions, sparse original claim indices and fail-closed handling of malformed batches. These tests establish protocol correctness, not live model teaching quality. Look for `summary_expansion=finished` alongside per-section logs when evaluating a fresh live run.

## Real-material follow-up check

Use the prepared presentation in Aura after pulling and restarting the backend. Record the outputs and relevant server diagnostics for this sequence:

1. Ask “Explain the beta-barrel membrane proteins shown in this presentation. Describe the examples that are actually shown and cite the slides.” Check each named example and citation against the slide, including diagram labels. Text-only coverage tests do not establish image-reading accuracy.
2. Ask “Explain that more simply, with an example.” Confirm that the subject and selected material persist.
3. Ask “Summarize the PPT”, then “in 2000 words”. Count the answer body, excluding numeric citation markers. The current acceptance range is 1,800–2,200 words. Verify that the explanation covers the presentation rather than repeating one topic, and inspect its citations and scientific claims. A word-count pass alone does not establish quality.
4. Ask a question whose requested facts are absent from the presentation. Check source/background labels independently of answer length.

Keep the separate live coverage-judge calibration marked pending until its human judgments and gate satisfy the stated criteria. Real-material retrieval, follow-up coherence, teaching depth and requested length need their own checks; passing the synthetic judge set does not establish them.

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
JSON remains rejected. If bounded recovery cannot produce checked synthesis,
the honest fallback remains available.
There is no additional whole-file retry loop or unbounded output increase. The
separate bounded section recovery described above can follow two unusable drafts.
Logs include
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

## Historical follow-up: carry forward the checked 1,110-word draft

The attached live run generated 1,427 words first, then a fully checked
1,110-word revision. Expansion did run: three initial sections failed
`question_relevance`; the other initial section retained 311 words. Repairs
retained 355 and 354 words in two sections, so the combined replacement was
shorter than the existing answer. The pipeline correctly kept the 1,110-word
draft, but the expansion strategy failed its goal. The log contains 45 provider
calls with a combined reported provider latency of 282.70 seconds.

Section validation previously received the whole 2,000-word user request.
It now receives an explicit `selected_material_section` intent context, a local
section question and excerpts of that section's assigned passages. The intent
judge measures topic match, not word count or completeness of the entire file.
Word count remains server-measured. Topic rejection still rejects an off-topic
section, and all factual support checks still run before accepting additions.

Expansion now seeds itself from the prior answer's positive whole-point support
results. Seed units keep their original order, including pronoun antecedents;
new checked units are appended in section order. Existing proof metadata is
preserved on recovered checked points so they can seed later expansion too.
Rejected or malformed units cannot seed it.

Each writer receives `already_explained` context and a target for **additional**
text: the lesser of the section deficit and remaining overall words, with an
80-word minimum when a section still needs work. It is asked for new supported
details, terms and relationships, rather than a rewrite. Exact repeats do not
increase the count. New points are accepted only after checking and only when
they improve the overall word distance. Calls stop as soon as the measured
overall target is satisfied. Section/source, token, retry and time bounds remain
in force. Logs distinguish generated, newly checked and retained words.

Structured groups of 2–12 nonliteral points now share the same independent
per-claim batch checker as larger summaries, rather than making up to 12 serial
requests. The batch cap remains 12, and missing/invalid decisions still fail
closed. A single point and plain unstructured short answers retain their
existing verification paths.

Nine new regressions reproduce a checked 1,110-word fixture and complete it to
2,010 words with source-checked additions, reject repeated-text padding, retain
seed order, check partial-section intent, reject off-topic sections, and verify
small-batch independence and missing-decision failure. This is controlled model
output, not a live generation benchmark. The full suite reports 137 tests:
135 passed and two optional OCR checks skipped. Provider compliance with word
targets and live content quality remain unverified after this change.

## Follow-up: verifier reasoning exhausted its output budget

The next attached run returned 809 words. Its first writer generated 1,374 words
in 30 structured points. One citation-check request then consumed all 4,096
completion tokens as reasoning (`finish_reason=length`,
`reasoning_effort=provider_default`). The summary stopped at
`verification_unavailable`; no expansion calls ran. This was an unavailable
checker, not proof that the uploaded deck lacked sufficient material.

Citation batch checks, single-claim checks and intent checks now use a separate
verification client. On the exact tested Nemotron Super ID it defaults to
`reasoning_effort=none`, matching the working summary-writing control. Other
models retain provider defaults. `NEBIUS_VERIFICATION_REASONING_EFFORT` can
explicitly select a level or `provider` to opt out. Coverage routing, deep
reasoning and ordinary answer clients remain unchanged. Logs identify these
requests with `task=verification`.

A typed `output_truncated` error triggers at most one retry of that exact judge
request, with `max_retries=1` on each provider call. Its output budget adds only
reported reasoning tokens, capped at 8,192 and the existing operator ceiling;
missing reasoning usage does not invent extra headroom. Successful batches are
not rechecked, and valid negative decisions are never retried into approval.
Partial JSON is never accepted. A second truncation, malformed or missing
decisions, nonboolean support, duplicate IDs or other provider errors continue
to fail closed. Every new summary addition still requires source checks.

Eight new controlled regressions cover the observed 4,096-reasoning-token
failure, targeted batch recovery with an independent negative verdict, repeated
failure and token caps, strict batch decisions, single-claim and intent recovery,
operator/model scoping, and checked expansion to 2,010 words after recovery.
These tests exercise real HTTP-response parsing with mocked provider responses;
they do not establish live requested-length reliability or judge calibration.
The broader suite reports 145 tests: 143 passed and two optional OCR checks
skipped.

## Follow-up: whole-file task relevance was blocking factual checking

The next attached log shows the updated verification client working:
`task=verification`, `reasoning_effort=none`, no truncation. Each of two writer
attempts produced 21 points and 916 words. Both returned
`stage=question_relevance` before any grounding batches ran. With no checked
points to retain, recovery selected 264 words of literal excerpts. The precise
reasons for the two topic rejections are absent from the log; they cannot be
attributed conclusively to word count or to an incorrectly identified subject.

For a generic request such as "summarize the ppt", task relevance can be
established by grounding the proposed summary in that selected file. It does
not need a second model to infer the task from the filename and answer alone.
`generic_material_summary` recognizes only whole-file requests and presentation
modifiers. Named subjects, focus restrictions and new topics after an apparent
format marker are excluded. This is deliberately narrower than overview retrieval.

The validation path applies only to structured points whose rendered text
matches the displayed answer, with an explicit overview context bound to the
source ID requested in `answer()`. Every retrieved source must have that ID.
Language and citation-number checks run first. Every complete point must still
pass the unchanged per-claim factual verifier against its cited evidence. A
foreign-topic claim with a selected-file citation, unavailable support checker
or negative support result remains a failure. Successful factual support in the
selected file establishes relevance for this generic overview task; it does not
establish external scientific accuracy or completeness of the summary.

Named/focused questions and unstructured or unbound answers continue through
the semantic intent judge. Section checks retain their scoped local questions
and topic validation. Word count remains a separate server-side check, and
short checked drafts can proceed to the existing bounded expansion. Logs now
identify `intent_method=bound_material_overview` on this narrow path.

Ten controlled regressions include two 21-point, 916-word drafts progressing to
1,991 source-checked words, rather than the quote fallback. They also cover
focused-topic rejection, foreign claims, mismatched/mixed source bindings,
rendered-answer mismatch and verification unavailability. All provider decisions
in these tests are controlled fixtures. Live requested-length generation and
judge calibration remain unverified.
The broader suite reports 155 tests: 153 passed and two optional OCR checks
skipped.
