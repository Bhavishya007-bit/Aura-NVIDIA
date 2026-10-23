# Tavily-backed research in Aura

Research a topic now combines the selected uploaded material with optional Tavily web search. Study-plan generation and the ordinary Tutor keep their existing source policies.

## Enable it locally

1. Get a Tavily API key from your own Tavily account. Keep it server-side.
2. Add this line to your existing `backend/.env`, replacing the placeholder locally:

   ```dotenv
   TAVILY_API_KEY=your_actual_tavily_key
   ```

3. Pull `main`, then restart FastAPI. Keep the existing database, Nebius configuration and frontend setup. No dependency installation or migration is needed.
4. In **Study Plan**, select a ready material, choose **Research a topic**, enter a topic, and click **Start research**. For example: “Explain the beta-barrel proteins in my slides and compare them with public scientific sources.”
5. The result separates **From your material** and **From the web**, with source chips and a research-limitations note. Download includes observed source URLs.

If the key is absent, Research stays available using the uploaded material and says web search is unavailable. A configured key means the provider can be attempted, not that the key/quota has been validated. Provider failures and searches without usable results become explicit limitations rather than fabricated web-backed findings.

## Topics outside the upload

Research can return a web-only brief when the selected upload is unrelated (for example, a bubble-sort question with biology slides selected). Missing material evidence is represented by an omitted or null `from_material`, with a coverage note in `limitations`; it is not a sourced finding. An entirely blank optional section is normalized to null before strict validation. Nonempty uncited text, unknown fields, fake IDs and cross-source citations still fail validation.

When a nonempty section has no citations, the bounded repair receives an explicit instruction to omit the irrelevant section or supply genuine observed references. That repair can only finish the result; it cannot repeat a paid search. If neither source type supplies usable findings, Aura returns an honest no-findings result rather than inventing citations. Schema validity does not establish that a live model's findings are factually correct.

Research explanations now share the safe teaching renderer for headings, bold text, lists and code. Inline citation chips still use only server-observed sources; model-written links and HTML remain literal text.

For runnable Python examples, select **Code & data**. Research intentionally uses document/web sources and does not execute code. After pulling the fix and restarting the backend, use Retry on a failed research run to create a new run; old failed runs keep their original status.

## Runtime and provenance

- A validated `web_search` action is allowed only for `research_brief`, and only when configured. It is removed from the actual model action schema otherwise. A completed document read is required first; after that read, a configured research run must attempt web search before finishing.
- At most two Tavily calls per run, including failed calls. Duplicate normalized queries are blocked. Each call uses fixed `basic` depth, at most four retained results, no generated Tavily answer, no full-page/raw-content retrieval, no images, and no transport retries.
- The key is used only in the Authorization header to the fixed `https://api.tavily.com/search` endpoint. The browser and model never receive it. The query schema rejects obvious credential/email inputs; the model is instructed to use public topic keywords instead of private excerpts or memory. Only the query field is sent, not the full uploaded material or conversation. These measures do not claim perfect resistance to every possible prompt injection.
- Requests use bounded connection/read timeouts and a 15-second elapsed-time check between streamed chunks; response size and retained snippets/titles are capped, and returned URLs are limited to public HTTP(S) links without embedded credentials or unusual ports. The backend does not fetch model-provided URLs.
- An attempted search is reserved in the existing run JSON before network I/O. No database transaction is held during the request, so cancellation remains responsive. Results are committed only after checking ownership, run state and deadline again. Cancelled or expired calls can still incur provider usage, but their late results cannot revive or complete the run.
- Source IDs are created from observed data: `D...` for uploaded evidence and stable `W...` IDs for returned URLs. Unknown references and cross-type source citations are rejected. Results' clickable URLs are derived from observations, never from model-written links.
- New typed research sections separate uploaded findings from web additions. Agent output remains `verified=false`: retrieving a web snippet is not independent factual verification. A missing or irrelevant source section can be omitted; source-backed claims require references. No evidence means no invented sourced section.
- Existing run step, token and time budgets still apply. Reported Tavily credits are kept separately from LLM tokens, inside saved observations. Run details shows call count and known credit usage; unreported usage stays unknown. Per-account/global spending limits remain deployment-hardening work.

## Contracts and files

Existing API routes and run-start payload keys remain unchanged. No tables or columns are added.

- `/agents/capabilities` now reports `web_search` according to server configuration and includes the tool only when available.
- Internal decisions add `web_search {query}` and optional `from_material`, `from_web` and `limitations` fields on `finish`.
- Research results add `research_sections`, `sources`, `web_status` and `limitations` inside existing JSON result storage. Each section has `kind`, `text`, `references`; observed source metadata contains `reference`, `kind`, `title`, and optional URL/slide/page/retrieval time. Legacy material-only research remains readable.
- Backend: `backend/agents/web.py`, `contracts.py`, `planning.py`, `runtime.py`, `store.py`, `routes.py`.
- Frontend: `ResearchResult.tsx`, `AgentPanel.tsx`, `AgentPanel.css`, `agentApi.ts`.

## Validation and limits

Twenty new controlled backend checks cover Tavily request authentication/shape, limits and sanitization, malformed/empty results, role/argument allowlists, observed-reference integrity, material-only fallback, injection attempts that request disallowed mutations, real PostgreSQL reservations, cancellation, expiry, paid-attempt limits, capability/auth boundaries, and an end-to-end background API run saving both source types.

The full backend suite reports **220 tests: 218 passed, 2 skipped**. Frontend production build passes, along with 18 DOM interaction tests and 11 model/contrast tests. Four new DOM cases exercise source-separated output, safe observed links, search-failure disclosure and research input behavior/availability.

These tests use synthetic provider replies and a local PGlite PostgreSQL engine; no private student database or real search key is used. Live Tavily/Nemotron quality and desktop/mobile visual review still need a configured local retest. No live credentials are available in the agent environment.

```bash
python -m unittest evaluation.check_web_research -v
# Set AURA_PGLITE_MODULE to an installed @electric-sql/pglite package to run SQL/API checks.
# Full controlled regression suite:
python -m unittest discover -s evaluation -p 'check_*.py'
npm run build
```

## Provider reference

Implementation parameters and authentication were checked against the official [Tavily Search API reference](https://docs.tavily.com/documentation/api-reference/endpoint/search). Its basic search currently costs one API credit per call; explicit basic depth prevents automatic promotion to a more expensive search mode. Provider pricing may change. Usage returned by the provider is the recorded value, not an estimate of billing.
