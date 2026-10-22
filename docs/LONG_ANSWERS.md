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
  with its measured count. If the target still cannot be met, Aura preserves the
  checked content and reports the shortfall; it does not invent missing file
  sections or fill the count with unsupported claims.
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
Those older log lines do not identify why the responses were rejected. They
do not establish truncation or a reasoning-budget problem.

New `provider=nebius status=invalid_response` lines include `failure_code`, task,
JSON mode, the requested token budget, a bounded finish reason, and numeric
prompt/completion/reasoning usage when reported. Codes distinguish
`output_truncated`, `empty_content`, `content_json`, `content_shape`,
`response_json`, `response_shape`, `completion_shape`, `unexpected_redirect`
and `unexpected_finish_reason`. Missing usage remains unknown.

Coverage and summary schema failures log the error count and at most eight
field paths/types. Unknown field names, input values and validation messages
are omitted; private model responses and credentials are not logged.

After pulling, restart the backend and repeat the request against the existing
prepared presentation. Use these diagnostic lines to choose a targeted fix;
the diagnostic update itself does not establish that live 2,000-word output
now succeeds. Eight controlled failure/redaction regressions are available via
`python -m unittest evaluation.check_llm_diagnostics -v`.
