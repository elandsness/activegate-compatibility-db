# ActiveGate Compatibility Intelligence

An internal tool for Dynatrace Managed environments to check ActiveGate upgrade compatibility based on release notes and extension data.

## Overview

This system ingests Dynatrace documentation, extracts compatibility facts using NLP, and provides go/no-go guidance for ActiveGate upgrades.

## Features

- Automated ingestion of release notes and extension metadata
- NLP-based compatibility extraction
- Graph-based storage for relationships
- CLI and web interfaces for queries
- Historical compatibility support

## Setup

1. Clone the repository
2. Create virtual environment: python -m venv venv
3. Activate: venv\Scripts\activate (Windows)
4. Install dependencies: pip install -r requirements.txt
5. Run the application

## Development

See development-checklist.md for step-by-step build guide.
