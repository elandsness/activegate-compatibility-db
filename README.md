# ActiveGate Compatibility Intelligence

Graph-backed compatibility intelligence for Dynatrace ActiveGate upgrades.

The system ingests release and ecosystem data, extracts compatibility facts, stores them in Neo4j, and serves results through a web UI and REST API.

8 | - **NLP-Powered Analysis**: Uses lightweight regex-based extraction (no heavy ML libraries required) to understand release notes
9 | - **Graph Database**: Neo4j for storing compatibility relationships
10 | - **Automated Updates**: Weekly data refresh from Dynatrace documentation
11 | - **Source Citations**: Links back to original documentation for explainability
12 | - **Batch CSV Checks**: Upload a CSV of ActiveGate environments and receive a CSV with compatibility findings columns appended

14 | ## What Is Current
15 | The web UI is the primary interface (port 3000).
16 | The Flask API handles ingestion, checks, chat, batch CSV, and graph data (port 5000).
17 | Neo4j stores versions, entities, and compatibility relationships (ports 7474 and 7687).
18 | Ingestion sources: releases, managed releases, Hub catalog, EOS notices, custom URL.
19 | Batch CSV check workflow is available in the UI and API.
20 | Interactive graph exploration is available in the UI.

- Web UI is the primary interface (port 3000)
- Flask API handles ingestion, checks, chat, batch CSV, and graph data (port 5000)
- Neo4j stores versions, entities, and compatibility relationships (ports 7474 and 7687)
- Ingestion sources: releases, managed releases, Hub catalog, EOS notices, custom URL
- Batch CSV check workflow is available in the UI and API
- Interactive graph exploration is available in the UI

## Quick Start (Docker Compose)

Use the consolidated stack in docker-compose.yml.

### 1. Start services

<<<<<<< HEAD
1. **Clone the repository**

    ```bash
    git clone https://github.com/elandsness/activegate-compatibility-db.git
    cd activegate-compatibility-db
    ```

2. **Set up Docker and Docker Compose**

    Ensure you have Docker and Docker Compose installed on your system. You can follow the official documentation to install them if they are not already present.

3. **Build and run the Docker container**

    ```bash
    docker-compose up -d
    ```

4. **Verify installation**

    After starting the Docker containers, you can verify that everything is set up correctly by accessing the API or UI components.

## Batch CSV API Usage
=======
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
>>>>>>> origin/main

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

<<<<<<< HEAD
## Configuration

### Environment Variables

Ensure that the following environment variables are set correctly. These can be configured in your Docker Compose file or as part of your deployment environment.

| Variable         | Description                               | Default                 |
| ---------------- | ----------------------------------------- | ----------------------- |
| `NEO4J_URI`      | URI of the Neo4j database               | `bolt://localhost:7687` |
| `NEO4J_USER`     | Username for accessing the Neo4j database | `neo4j`                 |
| `NEO4J_PASSWORD` | Password for accessing the Neo4j database | `password`              |
| `LOG_LEVEL`      | Logging level (DEBUG, INFO, WARNING, ERROR) | `INFO`                  |

## Troubleshooting

### Common Issues

#### Neo4j Connection Failed

```bash
# Check Neo4j is running
docker ps | grep neo4j

# Check connection settings
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=your_password
```

#### No Compatibility Data Found

If you do not see compatibility data, ensure that the data ingestion process has been run correctly.

1. **Run data ingestion**

    ```bash
    docker-compose run cli agi check-file config.yaml
    ```

2. **Check data directory**

    ```bash
    ls -la data/
    ```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interface (CLI)                    │
│                         agi check/ask                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                    Reasoning Engine                          │
│         compatibility_reasoner + citation_generator          │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                      Storage Layer                           │
│                    Neo4j Graph Database                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   NLP Extraction Engine                      │
│              Regex-based entity extraction (spaCy optional)  │
└─────────────────────────┬───────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────┐
│                   Data Ingestion Pipeline                   │
│        scraper + eos_scraper + hub_scraper + scheduler      │
└─────────────────────────────────────────────────────────────┘
```

## Development

### Running Tests
=======
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
>>>>>>> origin/main

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

<<<<<<< HEAD
=======
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

>>>>>>> origin/main
## License

This is free and unencumbered software released into the public domain.

<<<<<<< HEAD
Anyone is free to copy, modify, publish, use, compile, sell, or
distribute this software, either in source code form or as a compiled
binary, for any purpose, commercial or non-commercial, and by any
means.

In jurisdictions that recognize copyright laws, the author or authors
of this software dedicate any and all copyright interest in the
software to the public domain. We make this dedication for the benefit
of the public at large and to the detriment of our heirs and
successors. We intend this dedication to be an overt act of
relinquishment in perpetuity of all present and future rights to this
software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
IN NO EVENT SHALL THE AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR
OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org/>

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request
=======
Anyone is free to copy, modify, publish, use, compile, sell, or distribute this software, in source or compiled form, for any purpose, commercial or non-commercial, and by any means.
>>>>>>> origin/main
