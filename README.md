# ActiveGate Compatibility Intelligence

A graph-backed compatibility intelligence system for Dynatrace ActiveGate upgrades.

[![License: Unlicense](https://img.shields.io/badge/license-Unlicense-blue.svg)](https://unlicense.org/)

## What It Does

ActiveGate Compatibility Intelligence (AGI) helps you determine if your ActiveGate upgrade path is compatible with your environment. It scrapes Dynatrace release documentation, extracts compatibility relationships using regex-based NLP, stores them in Neo4j, and serves results through a web interface.

**Key Capabilities:**
- **Release Note Ingestion** - Scrapes and processes ActiveGate sprint release notes from Dynatrace docs
- **Managed Cluster Compatibility** - Tracks Managed cluster version compatibility with ActiveGate releases
- **Extension Catalog** - Indexes Dynatrace Hub extensions and their compatibility constraints
- **EOS Tracking** - Monitors end-of-support announcements
- **Compatibility Reasoning Engine** - Evaluates upgrade paths considering OS, Managed clusters, and extensions
- **Batch CSV Processing** - Bulk-check compatibility for multiple environments

## Quick Start (Docker Compose)

### Prerequisites
- Docker and Docker Compose installed
- Internet access (for initial data ingestion)

### 1. Clone and Start

```bash
git clone https://github.com/elandsness/activegate-compatibility-db.git
cd activegate-compatibility-db

# Start all services
docker compose up -d --build
```

### 2. Verify Services

Services start in this order: Neo4j → API → Web UI (wait ~15 seconds total)

```bash
# Check status
docker compose ps

# View logs
docker compose logs -f
```

### 3. Access the Application

| Service | URL | Purpose |
|---------|-----|---------|
| Web UI | http://localhost:3000 | Main application interface |
| API (direct) | http://localhost:5000/api/health | Backend health check |
| Neo4j Browser | http://localhost:7474 | Graph database explorer |

**Default Neo4j credentials:** `neo4j` / `password`

### 4. Ingest Initial Data

1. Open http://localhost:3000
2. Go to the **📥 Ingest Data** tab
3. Click **"Start Ingestion"** under "Releases"
4. Wait for success message (typically 30-60 seconds)
5. Switch to other tabs to explore data

### 5. Stop Services

```bash
# Stop all services (keeps data)
docker compose down

# Remove volumes (deletes Neo4j data!)
docker compose down -v
```

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Web UI (Port 3000)                        │
│                  Nginx reverse proxy + React SPA                   │
└──────────────────────────────────┬──────────────────────────────────┘
                                 │ /api/* requests
┌────────────────────────────────▼──────────────────────────────────┐
│              Flask API (Port 5000)                                │
│  ┌─────────────────┐ ┌───────────────┐ ┌──────────────────────┐  │
│  │   Compatibility │ │   Ingestion   │ │     Data/Graph       │  │
│  │     Reasoner    │ │   Scrapers    │ │     Endpoints        │  │
│  └────────┬────────┘ └───────┬───────┘ └──────────────────────┘  │
└───────────────────────────┼───┴───────────────────────────────────┘
                            │ Neo4j Bolt protocol (7687)
┌───────────────────────────▼───────────────────────────────────────┐
│              Neo4j Graph Database (Ports 7474, 7687)             │
│  Stores: Versions, Extensions, Compatibility relationships       │
└───────────────────────────────────────────────────────────────────┘
```

### Component Details

| Component | Location | Purpose |
|-----------|----------|---------|
| **Frontend** | `frontend/index.html` | Single-page React app served by Nginx |
| **Backend API** | `src/api/app.py` | Flask REST endpoints |
| **Compatibility Engine** | `src/reasoning/` | GO/NO-GO decision logic |
| **NLP Pipeline** | `src/nlp/` | Regex-based fact extraction |
| **Scrapers** | `src/ingestion/` | Data collection from Dynatrace docs |
| **Storage Layer** | `src/storage/` | Neo4j integration and queries |

## Usage

### Web UI (Port 3000)

The web interface has five tabs:

#### 📥 Ingest Data
Scrape and load compatibility data from various sources:
- **Releases** - ActiveGate sprint release notes
- **Managed** - Managed cluster release notes  
- **Hub** - Dynatrace Hub extensions catalog
- **EOS** - End-of-support announcements
- **All** - Scrape all sources (releases, managed, hub, EOS)
- **Custom URL** - Any webpage to extract compatibility info

#### 💬 Chat
Ask natural language questions about upgrade compatibility:
```
Can I upgrade from ActiveGate 1.330 to 1.335 on RHEL 8 with Managed 1.335?

Extensions: custom-ext:2.0.0
```

The system uses an interview-first flow, collecting required context before returning GO/NO-GO.

#### 📄 Batch CSV Check
Bulk compatibility checks:
1. Click "Download Template" to get the CSV format
2. Fill in one environment per row with:
   - `current_activegate_version`
   - `target_activegate_version`
   - `managed_cluster_version` (optional)
   - `os_family` (optional)
   - `os_version` (optional)
   - `extensions` as JSON object: `{"ext-id":"1.0.0"}`
3. Upload CSV
4. Download processed CSV with appended columns:
   - `compatibility_status` (GO, GO_WITH_CAUTION, NO_GO, UNKNOWN)
   - `compatibility_confidence` (0.0-1.0)
   - `compatibility_issues`
   - `compatibility_warnings`
   - `compatibility_recommendations`
   - `row_error` (for validation issues)

#### 📊 Data
View indexed data:
- ActiveGate release versions count
- Managed cluster version count
- Total relationships in graph
- Hub coverage summary and health status
- **Clear Graph Data** - Destructive operation to reset the database

#### 🕸️ Graph
Interactive visualization of compatibility relationships:
- Filter by ActiveGate version
- Filter by relationship status (compatible, questionable, incompatible, unknown)
- Search nodes by label
- Click nodes to see properties and connections

### CLI Tool

Run compatibility checks from command line:

```bash
# Install (with Python 3.10+)
pip install -r requirements.txt
pip install -e .

# Check a specific upgrade path
agi check --current 1.330 --target 1.335 \
    --os-family "Red Hat Enterprise Linux" \
    --os-version 8 \
    --managed 1.335 \
    --extensions custom-ext:2.0

# Ask natural language questions
agi ask "Can I upgrade from 1.330 to 1.335?"

# View system status
agi status

# Visualize the graph as Mermaid diagram
agi visualize

# Generate a config template
agi init_config my-config.yaml
```

## API Endpoints

### Health & Info
- `GET /` - API documentation and endpoint list
- `GET /api/health` - Service health status

### Compatibility Queries
- `POST /api/chat` - Natural language query
  ```json
  { "message": "Can I upgrade from 1.330 to 1.335?", "context": {} }
  ```
- `POST /api/check` - Structured check
  ```json
  {
    "current": "1.330",
    "target": "1.335",
    "os_family": "Red Hat Enterprise Linux",
    "managed_cluster_version": "1.335"
  }
  ```
- `GET /api/check/template` - Download CSV template
- `POST /api/check/batch-csv` - Bulk compatibility checks (multipart/form-data)

### Ingestion
- `POST /api/ingest` - Scrape and ingest data
  ```json
  { "source": "all" }
  ```
  Valid sources: `releases`, `managed`, `hub`, `eos`, `all`, `url`

### Data Queries
- `GET /api/data/versions` - ActiveGate versions list
- `GET /api/data/managed-versions` - Managed cluster versions
- `GET /api/data/relationships` - Relationship statistics
- `GET /api/data/hub-summary` - Extension catalog coverage
- `GET /api/data/graph` - Graph visualization data
  - Query params: `activegate_version`, `limit`
- `POST /api/admin/clear-graph` - Clear all graph data (destructive!)

## Data Ingestion Workflow

### How It Works
1. **Scrape** - HTML pages from Dynatrace documentation are fetched
2. **Parse** - Content is extracted and cleaned
3. **Extract** - NLP pipeline identifies:
   - Version numbers (ActiveGate, Managed, OS)
   - Compatibility statements (compatible/incompatible/deprecated)
   - Extension constraints
4. **Store** - Facts are persisted to Neo4j as nodes and relationships

### Relationship Types
| Type | Meaning |
|------|---------|
| `COMPATIBLE_WITH` | Versions work together |
| `INCOMPATIBLE_WITH` | Known incompatibility |
| `UPGRADEABLE_TO` | Upgrade path available |
| `SUPPORTED_BY` | Version supports a feature |
| `DEPRECATED_IN` | Feature deprecated in this version |
| `END_OF_SUPPORT` | Support ended for this version |

## Configuration

Environment variables (configure in `docker-compose.yml`):

```yaml
environment:
  - NEO4J_URI=bolt://neo4j:7687
  - NEO4J_USER=neo4j
  - NEO4J_PASSWORD=password
  - NEO4J_DATABASE=neo4j
  - PORT=5000
```

## Development

### Local Python Environment

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate    # Windows

# Install dependencies
pip install -r requirements.txt

# Run the API directly (requires Neo4j running)
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USER=neo4j
export NEO4J_PASSWORD=password
python -m src.api.app
```

### Running Tests

```bash
pytest tests/ -v --cov=src/
```

### Modifying the Frontend

Edit `frontend/index.html` and reload your browser (Ctrl+F5). The file is served directly by Nginx without rebuilding containers.

## Troubleshooting

### Neo4j connection fails
```bash
docker compose logs neo4j
# Verify http://localhost:7474 works with neo4j/password
```

### Ingestion timeouts or errors
- Ensure internet access is available
- Check if Dynatrace docs are accessible
- Look for source page structure changes in scraper code

### API returns errors
```bash
docker compose logs api
curl http://localhost:5000/api/health
```

### Web UI not loading
```bash
docker compose logs web
curl http://localhost:3000
```

## Project Structure

```
activegate-compatibility-db/
├── src/
│   ├── api/          # Flask REST API endpoints
│   ├── ingestion/    # Data scrapers (releases, managed, hub, eos)
│   ├── nlp/          # Regex-based NLP for fact extraction
│   ├── reasoning/    # Compatibility decision engine
│   └── storage/      # Neo4j integration and queries
├── frontend/
│   ├── index.html    # React SPA (single file)
│   └── nginx.conf    # Nginx reverse proxy config
├── tests/            # Unit and integration tests
├── docker-compose.yml       # Consolidated stack (Neo4j + API + Web)
├── Dockerfile.simple        # Python runtime image for API
└── requirements.txt         # Python dependencies
```

## License

This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute this software, in source or compiled form, for any purpose, commercial or non-commercial, and by any means.

For more information, please refer to [https://unlicense.org](https://unlicense.org)