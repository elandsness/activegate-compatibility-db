# Deployment Guide - ActiveGate Compatibility Intelligence

## Quick Start

### 1. Start Services

```bash
cd "c:\Users\erik.landsness\OneDrive - Dynatrace\Documents\Code\activegate-compatibility-db"
docker-compose -f docker-compose.web.yml up -d
```

### 2. Monitor Startup

```bash
docker-compose -f docker-compose.web.yml logs -f
```

Wait for the `web` service to report `ready` (typically 10-15 seconds after `neo4j` and `api` are healthy).

### 3. Access the UI

Open browser: **http://localhost:3000**

You should see the ActiveGate Compatibility Intelligence interface with three tabs:

- **📥 Ingest Data** (primary) - Scrape and ingest data sources
- **💬 Chat** - Ask natural language questions
- **📊 Data** - View indexed versions and relationships

## Data Ingestion Workflow

### Source Options

1. **📄 Releases** - Dynatrace official release notes
   - Scrapes: https://docs.dynatrace.com/ (release documentation)
   - Contains: Version compatibility, features, breaking changes
   - Click: "Start Ingestion" to fetch and process

2. **🔌 Hub** - Dynatrace Hub extensions
   - Scrapes: https://dynatrace.com/hub (extension catalog)
   - Contains: Extension names, compatibility matrices, supported versions
   - Click: "Start Ingestion" to fetch extension data

3. **⏰ EOS** - End-of-support announcements
   - Scrapes: https://dynatrace.com (EOS pages)
   - Contains: Support end dates, migration guidance
   - Click: "Start Ingestion" to fetch EOS info

4. **🌐 Custom URL** - Any webpage
   - Enter: Full URL (must be accessible)
   - Contains: Whatever text is on that page
   - Click: "Start Ingestion" to extract compatibility info

### Typical Workflow

1. Select "Releases" source
2. Click "Start Ingestion"
3. Wait for success message (shows items scraped, facts extracted)
4. Switch to "Data" tab to see new versions/relationships
5. Use "Chat" tab to query the ingested data

## Architecture

### Services (Docker Compose)

| Service | Port        | Purpose                                   |
| ------- | ----------- | ----------------------------------------- |
| `neo4j` | 7687 (Bolt) | Graph database storing compatibility data |
| `api`   | 5000        | Flask REST API (internal only)            |
| `web`   | 3000        | Nginx reverse proxy + static SPA frontend |

### Frontend (React)

- **Location**: `frontend/index.html`
- **Served by**: Nginx (port 3000)
- **Framework**: React 18 (via CDN + Babel transpilation)
- **API**: All requests go through Nginx proxy to `/api/*` (proxied to `api:5000`)

### Backend (Flask)

- **Location**: `src/api/app.py`
- **Database**: Neo4j at `bolt://neo4j:7687`
- **Scrapers**: `src/ingestion/` directory
- **NLP Pipeline**: `src/nlp/` (extracts compatibility facts)

## API Endpoints

### Health & Info

- `GET /` - API documentation and endpoint list
- `GET /api/health` - Service health status

### Compatibility Queries

- `POST /api/chat` - Natural language queries
  ```json
  { "message": "Can I upgrade from 1.330 to 1.335?" }
  ```
- `POST /api/check` - Structured compatibility check
  ```json
  { "from_version": "1.330", "to_version": "1.335", "managed": true }
  ```

### Data Ingestion

- `POST /api/ingest` - Scrape and ingest data
  ```json
  {"source": "releases"}
  {"source": "hub"}
  {"source": "eos"}
  {"source": "url", "url": "https://example.com"}
  ```

### Data Queries

- `GET /api/data/versions` - List all versions in graph
- `GET /api/data/relationships` - Relationship type statistics
- `GET /api/visualize` - Graph visualization data

## Troubleshooting

### Services Not Starting

```bash
# Check Docker daemon
docker ps

# Check compose logs
docker-compose -f docker-compose.web.yml logs

# Rebuild if needed
docker-compose -f docker-compose.web.yml build --no-cache
```

### Neo4j Connection Issues

```bash
# Check Neo4j logs
docker-compose -f docker-compose.web.yml logs neo4j

# Connect to Neo4j browser at http://localhost:7474
# Default credentials: neo4j / password
```

### Frontend Not Responding

```bash
# Check Nginx/web service
docker-compose -f docker-compose.web.yml logs web

# Verify port 3000 is accessible
curl http://localhost:3000
```

### API Returns Errors

```bash
# Check Flask app logs
docker-compose -f docker-compose.web.yml logs api

# Test API directly
curl http://localhost:5000/api/health
```

### Scrapers Failing

- **Releases scraper**: Requires internet access to https://docs.dynatrace.com/
- **Hub scraper**: Requires internet access to https://dynatrace.com/hub
- **EOS scraper**: Requires internet access to https://dynatrace.com/
- **URL scraper**: Requires access to specified URL

Check firewall/proxy settings if scrapers hang or timeout.

## Development Notes

### Modifying Frontend

1. Edit `frontend/index.html`
2. Reload browser (Ctrl+F5 for hard refresh)
3. Changes take effect immediately (no container rebuild needed)

### Modifying Backend API

1. Edit files in `src/`
2. Restart API service: `docker-compose -f docker-compose.web.yml restart api`
3. Or rebuild: `docker-compose -f docker-compose.web.yml up -d --build api`

### Inspecting Graph Database

1. Open Neo4j Browser: http://localhost:7474
2. Login: neo4j / password
3. Run queries like:
   ```cypher
   MATCH (v:Version) RETURN v LIMIT 10
   MATCH (a)-[r]->(b) RETURN a, r, b LIMIT 20
   ```

## Performance

### Initial Load

- First ingest typically takes 30-60 seconds per source
- Subsequent queries are instant (cached in Neo4j)

### Scalability

- Current setup handles ~10,000 compatibility facts
- Neo4j optimization needed for 100k+ facts
- Scraper parallelization possible in future

## Security Considerations

### Current Setup (Development)

- ⚠️ No authentication on API endpoints
- ⚠️ CORS enabled for all origins
- ⚠️ Neo4j default credentials (neo4j/password)
- ⚠️ No HTTPS (HTTP only on port 3000)

### Production Recommendations

1. Add authentication (API keys or OAuth)
2. Restrict CORS to known domains
3. Change Neo4j credentials
4. Enable HTTPS with reverse proxy
5. Add rate limiting
6. Implement audit logging

## Stopping Services

```bash
# Stop all services (keeps data)
docker-compose -f docker-compose.web.yml stop

# Stop and remove containers (keeps data volumes)
docker-compose -f docker-compose.web.yml down

# Stop and remove everything (deletes Neo4j data!)
docker-compose -f docker-compose.web.yml down -v
```

## Next Steps

1. **Ingest Data**: Use Ingest tab to populate graph with compatibility data
2. **Query Data**: Use Chat tab to ask natural language questions
3. **Explore Graph**: Use Data tab to see versions and relationships
4. **Monitor Performance**: Watch logs for any errors or timeouts
5. **Customize**: Modify scrapers/NLP pipeline for specific needs

## Support

For issues with:

- **Web UI**: Check `frontend/index.html` and browser console (F12)
- **API**: Check logs with `docker-compose logs api`
- **Database**: Check logs with `docker-compose logs neo4j`
- **Scrapers**: Check NLP pipeline output in API logs
