# Tutor source retention and outside examples

The reported judge-build question was “Explain separate chaining and open addressing with an example.” The synthetic notes define both strategies but do not contain that worked collision example. Partial coverage is therefore reasonable: it must not erase the definitions or turn an invented example into cited document content.

## Changed behavior

- The existing two source-writing attempts and citation checks remain. When an otherwise relevant draft contains both supported and unsupported claims, complete approved claims and their original citation IDs can survive. The rejected claims, introductions and broken fragments are not published.
- If those attempts produce no usable checked synthesis, Aura retains exact excerpts only from passages cited by the coverage decision's supported parts. It explicitly labels these as excerpts rather than a complete explanation. It does not quote arbitrary unrelated passages or change an unknown/not-covered verdict into full coverage.
- The separately labelled background writer receives the retained source text and the missing parts. It is asked to develop the missing example/application instead of repeating the definitions.
- Ordinary tutor background now uses the same model-based accuracy/relevance/scope review already used for long-summary background. A rejected draft gets one revision and one recheck at most. An identical rejected draft is never rerolled for approval. Malformed/unavailable review withholds the background and leaves source evidence available.
- The review guidance addresses the reported incorrect hash-table alias, unjustified fixed load-factor guarantees, worst-case claims and numerical examples. The review is fallible model assessment, not web verification or established general accuracy. Approved background remains `verified=false` and cannot contain document citations.
- An unavailable additional explanation gets a retry notice instead of being silently omitted. Citation/schema contracts, routes, ownership and saved answer text remain unchanged. No dependencies were added.

## Update the Docker judge build

From the Aura repository root in PowerShell, with Docker Desktop running:

```powershell
git pull origin main
docker compose --env-file judge/.env.judge -f judge/compose.yaml up -d --build app
```

This rebuilds/recreates the app while preserving the database volume and local credentials. Open http://localhost:8888 and send a **new** question with Aura Demo Study Notes.pdf selected. Existing replies are not rewritten. A Git pull alone does not update an already-running container image.

If model logs show provider HTTP 401, check the private `NEBIUS_API_KEY` and its matching `NEBIUS_BASE_URL` in `judge/.env.judge`, then recreate the app. A healthy container proves server availability, not valid provider credentials or answer quality. Do not share the private env file.

## Validation and remaining limits

`evaluation/check_tutor_sections.py` uses the actual authored synthetic collision notes with controlled model/verifier responses. It tests source retention, citation IDs, unsupported and off-topic draft removal, bounded background correction, unchanged rejection, missing/malformed review and forbidden document citations in background.

These tests verify enforcement, not that the live model always recognizes an error. Retest the reported question using the real local provider credential, inspect the citations and the hypothetical example, and record its actual source-check diagnostics if synthesis still falls back to excerpts. The long-answer length issue and human coverage calibration remain separate open quality work.

## Follow-up: unsupported clauses and deletion strategies

The next live reply showed two false acceptances: a sourced load-factor definition acquired an extra claim about collision/performance effects, and background text said open addressing requires tombstones for deletion.

`backend/ai/teaching_checks.py` adds two deliberately limited English checks:

- When all cited load-factor sentences match a recognised table-fullness-only definition, and the cited text contains no explicit causal/performance statement, an added causal claim is rejected. The standalone definition remains usable. Explicit causal evidence and other wording still go through semantic verification; the check never establishes coverage or approves a claim.
- Recognised unqualified statements that open addressing requires/needs tombstones are rejected before a model vote. Common qualifiers, negations, explicit corrections and implementation/lazy-deletion scoping are left to the reviewer. A rejected background gets the existing single revision opportunity, with no silent factual rewriting.

Both individual and batch citation verification enforce the source check. Both ordinary tutor and long-summary background share the deletion check through `review_background`. Writer/reviewer prompts also require clause-by-clause support and distinguish an algorithm family from an implementation choice. No route, payload, database field or dependency changed.

The [Chalmers/Gothenburg course textbook, section 11.5](https://chalmersgu-data-structure-courses.github.io/dsabook/html/section-11.5.html) describes lazy deletion with tombstones and reinsertion of the rest of a linear-probing cluster as distinct strategies. Alternatives must be compatible with the probing scheme; the change does not prescribe one deletion strategy for every implementation.

`evaluation/check_teaching_claims.py` includes the actual reported sentences and synthetic source notes, deliberately approving model fixtures, batch record/citation checks, positive source definitions, explicit causal evidence, qualified deletion statements and bounded correction/withholding. Passing these cases shows the recognised mistakes are blocked independently of an approving model. It does not establish general fact-checking accuracy or resolve human judge calibration. A fresh local answer is still required after rebuilding.
