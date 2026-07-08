"""
Flask API Backend for ActiveGate Compatibility Intelligence
Provides REST endpoints for chat, compatibility checks, and data management.
"""

import logging
import os

from flask import Flask, jsonify, request
from flask_cors import CORS

from src.nlp.nlp_pipeline import FactConverter, NLPPipeline
from src.reasoning.citation_generator import QueryProcessor
from src.reasoning.compatibility_reasoner import CompatibilityReasoner
from src.storage.graph_connection import GraphConnection
from src.storage.graph_populater import GraphPopulator
from src.storage.graph_query import GraphQuery

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)


@app.route("/")
def index():
    """Root endpoint with API info."""
    return jsonify(
        {
            "service": "ActiveGate Compatibility API",
            "version": "1.0.0",
            "endpoints": {
                "health": "/api/health",
                "chat": "/api/chat (POST)",
                "check": "/api/check (POST)",
                "ingest": "/api/ingest (POST)",
                "versions": "/api/data/versions",
                "relationships": "/api/data/relationships",
                "visualize": "/api/visualize",
            },
            "web_ui": "Port 3000",
        }
    )


def _make_graph_connection() -> GraphConnection:
    """Create a GraphConnection from environment variables."""
    return GraphConnection(
        uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        user=os.environ.get("NEO4J_USER", "neo4j"),
        password=os.environ.get("NEO4J_PASSWORD", "password"),
        database=os.environ.get("NEO4J_DATABASE", "neo4j"),
    )


def _init_components():
    """Initialise shared components, wiring the graph into the reasoner when available."""
    graph_conn = _make_graph_connection()
    connected = graph_conn.connect()

    if connected:
        graph_query = GraphQuery(graph_conn)
        graph_pop = GraphPopulator(graph_conn)
        reasoner = CompatibilityReasoner(graph_query=graph_query)
        logger.info("Components initialised with live Neo4j connection.")
    else:
        logger.warning("Neo4j unavailable at startup — running in offline mode.")
        graph_query = None
        reasoner = CompatibilityReasoner(graph_query=None)
        graph_pop = GraphPopulator(graph_conn)

    return reasoner, graph_pop


# Module-level singletons
reasoner, graph_populator = _init_components()
query_processor = QueryProcessor(reasoner)
nlp_pipeline = NLPPipeline()


@app.route("/api/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"status": "healthy", "service": "ActiveGate Compatibility API"})


@app.route("/api/chat", methods=["POST"])
def chat():
    """
    Chat endpoint for natural language queries.
    Accepts: {"message": "Can I upgrade from 1.330 to 1.335?"}
    Returns: {"response": "...", "citations": [...], "status": "GO|NO_GO"}
    """
    data = request.get_json()
    message = data.get("message", "")

    if not message:
        return jsonify({"error": "No message provided"}), 400

    # Process the query
    parsed = query_processor.process_query(message)
    versions = parsed.get("versions_found", [])

    if len(versions) >= 2:
        current = versions[0]
        target = versions[1]
    elif len(versions) == 1:
        current = "1.330"  # Default
        target = versions[0]
    else:
        return jsonify(
            {
                "response": 'Could not detect version in query. Please use format: "Can I upgrade from X to Y?"',
                "citations": [],
                "status": "UNKNOWN",
            }
        )

    # Run compatibility check, querying the graph when available
    result = reasoner.check_upgrade_compatibility(
        current_version=current,
        target_version=target,
        use_graph=reasoner.graph_query is not None,
    )

    # Format response
    response_text = query_processor.format_result_for_display(result)

    return jsonify(
        {
            "response": response_text,
            "versions_detected": {"current": current, "target": target},
            "citations": result.citations,
            "status": result.status.value if hasattr(result, "status") else "UNKNOWN",
            "confidence": result.confidence,
        }
    )


@app.route("/api/check", methods=["POST"])
def check_compatibility():
    """
    Structured compatibility check endpoint.
    Accepts: {"current": "1.330", "target": "1.335", "os_family": "linux", ...}
    Returns: Compatibility result with issues and recommendations.
    """
    data = request.get_json()

    current = data.get("current")
    target = data.get("target")
    os_family = data.get("os_family")
    os_version = data.get("os_version")
    managed = data.get("managed_cluster_version")
    extensions = data.get("extensions", [])

    if not current or not target:
        return jsonify({"error": "Current and target versions required"}), 400

    result = reasoner.check_upgrade_compatibility(
        current_version=current,
        target_version=target,
        os_family=os_family,
        os_version=os_version,
        managed_cluster_version=managed,
        extensions=extensions,
        use_graph=reasoner.graph_query is not None,
    )

    return jsonify(result.to_dict())


@app.route("/api/ingest", methods=["POST"])
def ingest_data():
    """
    Ingest data from various sources.
    Accepts: {"source": "releases|hub|eos|url", "url": "..."}
    Returns: {"status": "success", "source": "...", "items_scraped": N, "facts_extracted": N}
    """
    data = request.get_json(force=True, silent=True) or {}
    source = data.get("source", "releases")

    items_scraped = 0
    facts_extracted = 0

    try:
        documents = []

        if source == "releases":
            import re

            from src.ingestion.scraper import ReleaseNotesScraper

            def _extract_version_from_url(url: str) -> str:
                match = re.search(r"sprint-(\d+)", url, re.IGNORECASE)
                return f"1.{match.group(1)}" if match else ""

            scraper = ReleaseNotesScraper()
            releases = scraper.scrape_release_notes()
            items_scraped = len(releases)
            documents = releases
            logger.info(f"Release scraper found {len(releases)} documents")

            # Ensure every scraped release exists as a graph node before NLP extraction.
            for release in releases:
                version = release.get("version") or _extract_version_from_url(
                    release.get("url", "")
                )
                title = release.get("title") or f"ActiveGate {version}"
                if version:
                    graph_populator.ensure_activegate_release_node(
                        version, title, release.get("url", "")
                    )

        elif source == "hub":
            from src.ingestion.hub_scraper import HubExtensionsScraper

            scraper = HubExtensionsScraper()
            extensions = scraper.scrape_extensions()
            items_scraped = len(extensions)
            documents = [
                {
                    "title": ext.get("name", "Extension"),
                    "url": ext.get("url", ""),
                    "content": str(ext.get("data", {})),
                }
                for ext in extensions
            ]
            logger.info(f"Hub scraper found {len(extensions)} extensions")

        elif source == "eos":
            from src.ingestion.eos_scraper import EndOfSupportScraper

            scraper = EndOfSupportScraper()
            announcements = scraper.scrape_end_of_support()
            items_scraped = len(announcements)
            documents = announcements
            logger.info(f"EOS scraper found {len(announcements)} announcements")

        elif source == "url":
            url = data.get("url")
            if not url:
                return jsonify({"error": "URL required for url source"}), 400

            import requests

            response = requests.get(url, timeout=30)
            response.raise_for_status()
            documents = [
                {"title": data.get("title", url), "url": url, "content": response.text}
            ]
            items_scraped = 1
            logger.info(f"URL scraper processed {url}")

        else:
            return (
                jsonify(
                    {"error": f"Unknown source: {source}. Use: releases, hub, eos, url"}
                ),
                400,
            )

        facts_extracted = 0
        processed_docs = []

        for doc in documents:
            content = doc.get("content", "")
            logger.info(
                f"Processing document '{doc.get('title', 'Unknown')}' with {len(content)} chars"
            )

            result = nlp_pipeline.process_document(
                text=content,
                source_url=doc.get("url", ""),
                source_title=doc.get("title", "Document"),
            )

            # Convert to facts and store in graph
            facts = FactConverter.convert_to_facts(result)
            doc_facts = len(facts)
            facts_extracted += doc_facts
            logger.info(
                f"Extracted {len(result.compatibility_statements)} compatibility statements and generated {doc_facts} graph facts"
            )
            graph_populator.populate_from_facts(facts)
            logger.info(f"Stored {len(facts)} facts in graph")

            processed_docs.append(
                {
                    "title": doc.get("title", "Unknown"),
                    "url": doc.get("url", ""),
                    "content_length": len(content),
                    "facts_extracted": doc_facts,
                    "facts_stored": len(facts),
                    "compatibility_statements": len(result.compatibility_statements),
                    "version_pairs": len(result.version_pairs),
                }
            )

        return jsonify(
            {
                "status": "success",
                "source": source,
                "items_scraped": items_scraped,
                "facts_extracted": facts_extracted,
                "documents": processed_docs,
            }
        )

    except Exception as e:
        logger.error(f"Ingest error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/api/data/versions", methods=["GET"])
def get_versions():
    """Get all ActiveGate versions in the database."""
    graph_conn = _make_graph_connection()
    try:
        graph_conn.connect()
        query = "MATCH (ag:ActiveGateVersion) RETURN ag.version as version ORDER BY ag.version"
        result = graph_conn.execute(query)
        versions = [record["version"] for record in result]
        return jsonify({"versions": versions})
    except Exception as e:
        return jsonify({"error": str(e), "versions": []}), 500
    finally:
        graph_conn.disconnect()


@app.route("/api/data/relationships", methods=["GET"])
def get_relationships():
    """Get relationship statistics."""
    graph_conn = _make_graph_connection()
    try:
        graph_conn.connect()
        query = """
        MATCH (a)-[r]->(b)
        RETURN type(r) as relationship, count(*) as count
        """
        result = graph_conn.execute(query)
        relationships = [
            {"type": r["relationship"], "count": r["count"]} for r in result
        ]
        return jsonify({"relationships": relationships})
    except Exception as e:
        return jsonify({"error": str(e), "relationships": []}), 500
    finally:
        graph_conn.disconnect()


@app.route("/api/admin/clear-graph", methods=["POST"])
def clear_graph():
    """Clear all Neo4j graph data. Use for resetting ingestion state."""
    graph_conn = _make_graph_connection()
    try:
        graph_conn.connect()
        graph_conn.clear_database()
        return jsonify({"status": "success", "message": "Neo4j graph cleared"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        graph_conn.disconnect()


@app.route("/api/visualize", methods=["GET"])
def visualize():
    """Get graph visualization data."""
    from src.storage.graph_visualizer import GraphVisualizer

    try:
        visualizer = GraphVisualizer()
        data = visualizer.get_graph_data(limit=20)
        text_output = visualizer.to_text_diagram(data)
        return jsonify({"visualization": text_output})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)
