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
