# ActiveGate Compatibility Intelligence

A system for checking ActiveGate upgrade compatibility for Dynatrace Managed environments. Ingests release notes, extracts compatibility facts using NLP, stores in Neo4j graph database, and provides go/no-go upgrade guidance with explainable citations.

## Features

- **NLP-Powered Analysis**: Uses lightweight regex-based extraction (no heavy ML libraries required) to understand release notes
- **Graph Database**: Neo4j for storing compatibility relationships
- **Automated Updates**: Weekly data refresh from Dynatrace documentation
- **Source Citations**: Links back to original documentation for explainability
- **Batch CSV Checks**: Upload a CSV of ActiveGate environments and receive a CSV with compatibility findings columns appended

## Quick Start

### Installation

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

Download the template CSV:

```bash
curl -L -o activegate-compatibility-template.csv \
  http://localhost:5000/api/check/template
```

Process a batch CSV and download results:

```bash
curl -L -X POST \
  -F "file=@activegate-compatibility-template.csv" \
  http://localhost:5000/api/check/batch-csv \
  -o activegate-compatibility-with-findings.csv
```

Input CSV requirements:

- UTF-8, comma-delimited CSV
- Required headers:
  - `current_activegate_version`
  - `target_activegate_version`
  - `managed_cluster_version`
  - `os_family`
  - `os_version`
  - `extensions`
- `extensions` cell format is a JSON object map, for example: `{"custom-ext":"2.0.0","another-ext":"1.5.2"}`

Output columns appended by `/api/check/batch-csv`:

- `compatibility_status`
- `compatibility_confidence`
- `compatibility_issues`
- `compatibility_warnings`
- `compatibility_recommendations`
- `row_error`

Notes:

- Missing `current_activegate_version` or `target_activegate_version` writes a row-level error and continues processing other rows.
- Blank `managed_cluster_version` and `extensions` values are accepted.

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

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_reasoning_engine.py -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html
```

### Project Structure

```
activegate-compatibility-db/
├── src/
│   ├── cli/           # CLI interface
│   ├── ingestion/    # Web scrapers
│   ├── nlp/           # NLP extraction
│   ├── reasoning/    # Compatibility reasoning
│   └── storage/      # Neo4j storage
├── tests/            # Test files
├── data/             # Data files
├── config/           # Configuration
├── Dockerfile        # Docker image
├── docker-compose.yml
└── requirements.txt
```

## License

This is free and unencumbered software released into the public domain.

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