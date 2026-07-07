# ActiveGate Compatibility Intelligence Sprint Backlog

## Goal
Create a stable, graph-backed compatibility intelligence system for Dynatrace ActiveGate with reliable ingestion, explainable compatibility reasoning, CLI/API/UI access, and deployable Docker workflow.

---

## Sprint 1: Stabilize and Fix Foundations

### 1.1 Align runtime and deployment
- [ ] Audit and fix Docker Compose files so the local development and web deployment stacks match actual services.
- [ ] Ensure the API service starts correctly and is reachable from the UI proxy.
- [ ] Clean up `Dockerfile` and `Dockerfile.simple` so they use only required runtime dependencies.
- [ ] Update deployment docs to reflect the final startup workflow.

 ### 1.2 Clean dependency and packaging drift
 - [x] Audit `requirements.txt` vs actual imports used in code. (Completed)
 - [x] Remove unused heavyweight dependencies such as `transformers`, `torch`, and `scikit-learn` unless they are truly required. (Not present in codebase)
 - [ ] Verify package install and entry point `agi` works correctly.

### 1.3 Stabilize API and CLI bootstrapping
- [ ] Fix `src/api/app.py` component initialization and ensure Graph connection wiring is correct.
- [ ] Fix `src/cli/main.py` so CLI commands use graph-backed reasoning when Neo4j is available.
- [ ] Add a `status` command that reports live graph availability and node counts.

---

## Sprint 2: Make the Graph Model Real

### 2.1 Finalize schema and fact model
- [ ] Choose one canonical graph schema based on `docs/graph-schema.md`.
- [ ] Ensure node labels and relationship types are consistent across code and docs.
- [ ] Document schema expectations in `docs/graph-schema.md`.

### 2.2 Fix NLP fact conversion
- [ ] Update `src/nlp/nlp_pipeline.py` and `FactConverter` to output actual graph-ready facts.
- [ ] Add unit tests for fact conversion on sample release note text.

### 2.3 Harden graph population
- [ ] Refactor `src/storage/graph_populater.py` to insert the right node types and relationships.
- [ ] Make graph inserts idempotent and preserve provenance (`source_url`, `raw_text`, `confidence`).
- [ ] Add graph schema validation tests.

---

## Sprint 3: Improve ingestion and extraction

### 3.1 Strengthen scrapers
- [ ] Improve release notes scraping reliability with robust selectors and fallback logic.
- [ ] Improve EOS scraper so it extracts structured support announcements.
- [ ] Improve Hub scraper to scrape meaningful extension compatibility metadata, not just page text.

### 3.2 Improve NLP quality
- [ ] Expand compatibility extraction patterns to capture linked versions and components.
- [ ] Improve entity extraction for OS versions and extension identifiers.
- [ ] Add regression tests covering real-world sample content.

### 3.3 Connect ingestion end-to-end
- [ ] Ensure `/api/ingest` scrapes, extracts, converts, and persists facts in Neo4j.
- [ ] Provide meaningful ingestion output with item and fact counts.
- [ ] Add a safe graph reset endpoint and validate ingestion results.

---

## Sprint 4: Real compatibility reasoning

### 4.1 Graph-first reasoning
- [ ] Replace static heuristic checks with graph-backed compatibility lookups.
- [ ] Use Neo4j relationships as the primary source of truth for AG/Managed/OS/extension compatibility.
- [ ] Add explicit rule handling for deprecations and EOS based on extracted facts.

### 4.2 Citations and explainability
- [ ] Wire extracted provenance into compatibility result citations.
- [ ] Return citations in API results and display them in CLI/UI outputs.
- [ ] Add tests that verify citations are produced for issue/warning cases.

### 4.3 Natural language query improvements
- [ ] Improve `QueryProcessor.process_query()` to extract versions, OS, managed version, and extensions.
- [ ] Add query intent recognition for extension, OS, upgrade, and general compatibility.
- [ ] Add tests for query parsing and formatted results.

---

## Sprint 5: UI, tests, and polish

### 5.1 UI stabilization
- [ ] Decide whether the frontend stays as a static SPA or becomes a built React app.
- [ ] Ensure the UI can ingest data, query chat, and show graph data correctly.
- [ ] Add better error handling for API failures.

### 5.2 Testing and CI
- [ ] Convert current script-style tests into proper `pytest` tests.
- [ ] Add unit tests for ingestion, NLP, graph population, reasoning, and API endpoints.
- [ ] Add GitHub Actions or another CI workflow to run tests automatically.

### 5.3 Final validation
- [ ] Validate the system against real Dynatrace release and compatibility cases.
- [ ] Confirm the deployment workflow works as documented.
- [ ] Update README, deployment docs, and checklist.

---

## Sprint Execution Notes
- Each task should include a short description, expected result, and acceptance criteria.
- Prioritize work starting with architecture/deployment, then graph model, then ingestion, then reasoning, then UI/tests.
- Maintain the backlog as living documentation and update `SPRINT_BACKLOG.md` as tasks are completed.
