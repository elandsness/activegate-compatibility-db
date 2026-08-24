"""Shared helpers for the ActiveGate Compatibility API."""

import csv
import json
import logging
import os
import re
from io import StringIO
from typing import Any, Dict, List, Optional

from src.nlp.nlp_pipeline import FactConverter, NLPPipeline
from src.storage.connection_manager import get_manager

logger = logging.getLogger(__name__)


def make_graph_connection():
    """Return a session-scoped Neo4j connection (singleton under the hood)."""
    mgr = get_manager()
    if not mgr.is_connected:
        mgr.connect()
    return mgr


def process_documents_with_nlp(documents: List[Dict], graph_populator=None) -> Dict:
    """Process documents via NLP pipeline and persist extracted facts."""
    from src.storage.graph_populater import GraphPopulator

    nlp = NLPPipeline()
    facts_extracted = 0
    facts_stored = 0
    processed_docs = []

    pop = graph_populator or GraphPopulator()

    # Connect to Neo4j if not already connected
    if not pop.graph_conn or not pop.graph_conn.is_connected:
        if pop.graph_conn:
            pop.graph_conn.connect()
        else:
            # Create a new connection manager and connect
            from src.storage.connection_manager import get_manager
            mgr = get_manager()
            mgr.connect()
            pop.graph_conn = mgr

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

        # Persist facts to Neo4j
        if facts and pop and pop.graph_conn and pop.graph_conn.is_connected:
            stored = pop.populate_from_facts(facts)
            facts_stored += stored
            logger.info("Stored %d facts for document %s", stored, doc.get("title", "Unknown"))
        elif not pop:
            logger.warning("No graph_populator provided")
        elif not pop.graph_conn:
            logger.warning("graph_populator has no graph_conn")
        elif not pop.graph_conn.is_connected:
            logger.warning("graph_populator connected=%s", pop.graph_conn.is_connected)

        processed_docs.append({
            "title": doc.get("title", "Unknown"),
            "url": doc.get("url", ""),
            "content_length": len(content),
            "facts_extracted": doc_facts,
            "facts_stored": facts_stored,
            "compatibility_statements": len(result.compatibility_statements),
            "version_pairs": len(result.version_pairs),
        })

    return {"facts_extracted": facts_extracted, "facts_stored": facts_stored, "documents": processed_docs}


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
