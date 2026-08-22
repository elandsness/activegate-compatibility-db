"""Shared helpers for the ActiveGate Compatibility API."""

import csv
import json
import logging
import os
import re
from io import StringIO
from typing import Any, Dict, List, Optional

from src.nlp.nlp_pipeline import FactConverter, NLPPipeline
from src.storage.graph_connection import GraphConnection

logger = logging.getLogger(__name__)


def make_graph_connection() -> GraphConnection:
    """Create a GraphConnection from environment variables."""
    return GraphConnection(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "password"),
        database=os.environ.get("NEO4J_DATABASE", "neo4j"),
    )


def process_documents_with_nlp(documents: List[Dict]) -> Dict:
    """Process documents via NLP pipeline and persist extracted facts."""
    nlp = NLPPipeline()
    facts_extracted = 0
    processed_docs = []

    for doc in documents:
        content = doc.get("content", "")
        logger.info(
            "Processing document '%s' with %d chars",
            doc.get("title", "Unknown"),
            len(content),
        )

        result = nlp.process_document(
            text=content,
            source_url=doc.get("url", ""),
            source_title=doc.get("title", "Document"),
        )

        facts = FactConverter.convert_to_facts(result)
        doc_facts = len(facts)
        facts_extracted += doc_facts

        # Persist via the GraphPopulator passed in by the caller
        # (we avoid importing it here to prevent circular deps)
        processed_docs.append({
            "title": doc.get("title", "Unknown"),
            "url": doc.get("url", ""),
            "content_length": len(content),
            "facts_extracted": doc_facts,
            "facts_stored": doc_facts,
            "compatibility_statements": len(result.compatibility_statements),
            "version_pairs": len(result.version_pairs),
        })

    return {"facts_extracted": facts_extracted, "documents": processed_docs}


def extract_release_version_from_url(url: str) -> str:
    """Extract ActiveGate version (1.xxx) from a sprint URL."""
    match = re.search(r"sprint-(\d+)", url, re.IGNORECASE)
    return f"1.{match.group(1)}" if match else ""


# ------------------------------------------------------------------ #
#  Graph-visualisation helpers (used by /api/data/graph route)      #
# ------------------------------------------------------------------ #

def normalize_graph_value(value: Any) -> Any:
    """Convert Neo4j values to JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def pick_node_key(labels: List[str], props: Dict[str, Any]) -> str:
    """Pick a stable display key for a node based on label and properties."""
    if "ActiveGateVersion" in labels:
        return str(
            props.get("version") or props.get("name") or props.get("id") or "unknown"
        )
    if "ManagedClusterVersion" in labels:
        return str(
            props.get("version") or props.get("name") or props.get("id") or "unknown"
        )
    if "OSVersion" in labels:
        os_name = props.get("os_name") or props.get("family") or "OS"
        version = props.get("version") or "unknown"
        return f"{os_name} {version}"
    if "Extension" in labels:
        return str(
            props.get("id") or props.get("slug") or props.get("name") or "extension"
        )
    if "HubItem" in labels:
        return str(
            props.get("slug") or props.get("id") or props.get("title") or "hub-item"
        )
    if "HubItemRelease" in labels:
        title = (
            props.get("title") or props.get("version") or props.get("id") or "release"
        )
        return str(title)
    if "Module" in labels:
        return str(props.get("name") or props.get("id") or "module")
    if "Setting" in labels:
        return str(props.get("name") or props.get("id") or "setting")

    return str(
        props.get("name")
        or props.get("version")
        or props.get("id")
        or props.get("slug")
        or "node"
    )


def relationship_status(rel_type: str) -> str:
    """Map relationship type to high-level graph status."""
    if rel_type in {
        "COMPATIBLE_WITH", "SUPPORTED_BY", "REQUIRES",
        "UPGRADEABLE_TO", "HAS_SETTING", "USES_MODULE",
    }:
        return "compatible"
    if rel_type in {"DEPRECATED_IN", "END_OF_SUPPORT", "REQUIRES_UPGRADE"}:
        return "questionable"
    if rel_type == "INCOMPATIBLE_WITH":
        return "incompatible"
    return "unknown"


def status_color(status: str) -> str:
    """Return a CSS hex colour for a graph status string."""
    return {
        "compatible": "#22c55e",
        "questionable": "#f59e0b",
        "incompatible": "#ef4444",
    }.get(status, "#94a3b8")


def serialize_issues(items) -> str:
    if not items:
        return ""
    return " | ".join(
        f"[{item.severity}] {item.category}: {item.message}" for item in items
    )


def serialize_recommendations(items: List[str]) -> str:
    if not items:
        return ""
    return " | ".join(items)
