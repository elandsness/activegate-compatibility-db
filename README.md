# ActiveGate Compatibility Intelligence

Graph-backed compatibility intelligence for Dynatrace ActiveGate upgrades.

The system ingests release and ecosystem data, extracts compatibility facts, stores them in Neo4j, and serves results through a web UI and REST API.

## What Is Current

- Web UI is the primary interface (port 3000)
- Flask API handles ingestion, checks, chat, batch CSV, and graph data (port 5000)
- Neo4j stores versions, entities, and compatibility relationships (ports 7474 and 7687)
- Ingestion sources: releases, managed releases, Hub catalog, EOS notices, custom URL
- Batch CSV check workflow is available in the UI and API
- Interactive graph exploration is available in the UI

## Quick Start (Docker Compose)

Use the consolidated stack in docker-compose.yml.

### 1. Start services

```bash
docker compose up -d --build
```

Services started:

- neo4j
- api
- web

### 2. Monitor startup

```bash
docker compose ps
docker compose logs -f
```

Wait until Neo4j is healthy before relying on ingestion or compatibility checks.

### 3. Open the app

- Web UI: http://localhost:3000
- API health: http://localhost:5000/api/health
- Neo4j Browser: http://localhost:7474

Default Neo4j credentials in compose:

- Username: neo4j
- Password: password

### 4. Stop services

```bash
docker compose down
```

To remove data volumes too:

```bash
docker compose down -v
```

## Compose File Notes

- docker-compose.yml: recommended default stack
- docker-compose.web.yml: web deployment variant
- docker-compose.simple.yml: reduced setup variant

## Web UI Workflow

The UI has five tabs.

### 1. Ingest Data

Purpose: scrape and load facts into Neo4j.

Available sources:

- Releases
- Managed
- Hub
- EOS
- All
- Custom URL

Typical flow:

1. Open the Ingest Data tab.
2. Choose Releases, Managed, Hub, EOS, All, or Custom URL.
3. Start ingestion.
4. Wait for success output with items_scraped and facts_extracted.

Notes:

- Requests go through /api/ingest via Nginx proxy.
- External sources require internet access.
- Data views refresh after successful ingestion.

### 2. Chat

Purpose: interactive upgrade guidance.

The chat endpoint uses an interview-first flow and collects required context before GO or NO_GO:

- current ActiveGate version
- target ActiveGate version
- Managed cluster version
- OS family
- OS version
- extensions with versions

Example prompt:

Can I upgrade from ActiveGate 1.330 to 1.335 on RHEL 8 with Managed 1.335 and extensions: custom-ext:2.0.0?

### 3. Batch CSV Check

Purpose: evaluate multiple environments in one run.

Flow:

1. Download template.
2. Fill one environment per row.
3. Upload CSV.
4. Download processed CSV with findings columns appended.

Required headers:

- current_activegate_version
- target_activegate_version
- managed_cluster_version
- os_family
- os_version
- extensions

Extensions field format (JSON object as cell text):

{"custom-ext":"2.0.0","another-ext":"1.5.2"}

Appended output columns:

- compatibility_status
- compatibility_confidence
- compatibility_issues
- compatibility_warnings
- compatibility_recommendations
- row_error

Behavior:

- UTF-8 CSV required
- maximum 5000 rows
- missing version fields are marked per row in row_error
- blank managed_cluster_version and extensions are accepted

### 4. Data

Purpose: inspect what is currently loaded.

Displays:

- ActiveGate release versions
- Managed release versions
- relationship counts by type
- Hub coverage summary

Includes Clear Graph Data, which is destructive.

### 5. Graph

Purpose: inspect compatibility relationships visually.

Features:

- load graph payload from /api/data/graph
- filter by ActiveGate version
- filter by relationship status (compatible, questionable, incompatible, unknown)
- search nodes by label
- inspect node properties and connected links
- fit and rebalance graph layout

## API Surface

### Health and service info

- GET /
- GET /api/health

### Compatibility

- POST /api/chat
- POST /api/check
- GET /api/check/template
- POST /api/check/batch-csv

### Ingestion

- POST /api/ingest

Supported source values:

- releases
- managed
- hub
- eos
- all
- url

### Data and graph

- GET /api/data/versions
- GET /api/data/managed-versions
- GET /api/data/relationships
- GET /api/data/hub-summary
- GET /api/data/graph
- POST /api/admin/clear-graph

## Local Development

### Python environment

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

### Run API directly

Neo4j must be reachable.

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
python -m src.api.app
```

### Run tests

```bash
pytest tests/ -v
```

## Project Layout

```text
src/
  api/          Flask API
  ingestion/    release, managed, hub, eos scrapers
  nlp/          compatibility fact extraction
  reasoning/    compatibility reasoning and citations
  storage/      Neo4j connection, population, and graph queries
frontend/
  index.html    web UI served by nginx
tests/
docker-compose.yml
Dockerfile.simple
```

## Troubleshooting

### UI is not reachable

```bash
docker compose logs web
curl http://localhost:3000
```

### API errors

```bash
docker compose logs api
curl http://localhost:5000/api/health
```

### Neo4j unavailable

```bash
docker compose logs neo4j
```

Then verify http://localhost:7474 is reachable and credentials match compose settings.

### Ingestion fails

Common causes:

- outbound network not available
- source page structure changed
- external request timeout or blocking

### Data tabs are empty

Run ingestion first. The stack can start with an empty graph.

## License

This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this software, in source or compiled form, for any purpose, commercial or non-commercial, and by any means.
