# ActiveGate Compatibility Intelligence

A system for checking ActiveGate upgrade compatibility for Dynatrace Managed environments. Ingests release notes, extracts compatibility facts using NLP, stores in Neo4j graph database, and provides go/no-go upgrade guidance with explainable citations.

## Features

- **NLP-Powered Analysis**: Uses spaCy and regex-based extraction to understand release notes
- **Graph Database**: Neo4j for storing compatibility relationships
- **CLI Interface**: Check compatibility via command line or config files
- **Automated Updates**: Weekly data refresh from Dynatrace documentation
- **Source Citations**: Links back to original documentation for explainability

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/elandsness/activegate-compatibility-db.git
cd activegate-compatibility-db

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt

# Install the package
pip install -e .
```

### Basic Usage

```bash
# Check compatibility (structured)
agi check -c 1.330 -t 1.335

# Ask a natural language question
agi ask "Can I upgrade from 1.330 to 1.335?"

# Check using a config file
agi check-file config.yaml

# Get system status
agi status
```

### Docker Usage

```bash
# Build the Docker image
docker build -t dynatrace/activegate-compatibility .

# Run with Docker Compose
docker-compose up -d

# Run CLI commands
docker-compose run cli agi check -c 1.330 -t 1.335
```

## Configuration

### Environment Variables

| Variable         | Description          | Default                 |
| ---------------- | -------------------- | ----------------------- |
| `NEO4J_URI`      | Neo4j connection URI | `bolt://localhost:7687` |
| `NEO4J_USER`     | Neo4j username       | `neo4j`                 |
| `NEO4J_PASSWORD` | Neo4j password       | `password`              |
| `LOG_LEVEL`      | Logging level        | `INFO`                  |

### Config File Format

```yaml
# config.yaml
current_activegate_version: '1.330'
target_activegate_version: '1.335'
os_family: 'linux'
os_version: '8'
managed_cluster_version: '1.335'
extensions:
  - id: 'custom-logging'
    version: '2.0'
  - id: 'custom-metrics'
    version: '1.5'
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
│              spaCy + regex entity extraction                │
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

```bash
# Run data ingestion
python -m src.ingestion.scheduler

# Check data directory
ls -la data/
```

#### Import Errors

```bash
# Ensure virtual environment is activated
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Logging

```bash
# Set debug logging
export LOG_LEVEL=DEBUG
agi check -c 1.330 -t 1.335
```

### Getting Help

```bash
# Show CLI help
agi --help

# Show version
agi version

# Show status
agi status
```

## License

Copyright (c) 2026 Dynatrace. All rights reserved.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request
