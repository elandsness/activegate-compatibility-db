"""
Flask API Backend for ActiveGate Compatibility Intelligence
Provides REST endpoints for chat, compatibility checks, and data management.
"""

import logging
import os
import re
from typing import Dict, List

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


def _process_documents_with_nlp(documents: List[Dict]) -> Dict:
    """Process documents via NLP pipeline and persist extracted facts."""
    facts_extracted = 0
    processed_docs = []

    for doc in documents:
        content = doc.get("content", "")
        logger.info(
            "Processing document '%s' with %d chars",
            doc.get("title", "Unknown"),
            len(content),
        )

        result = nlp_pipeline.process_document(
            text=content,
            source_url=doc.get("url", ""),
            source_title=doc.get("title", "Document"),
        )

        facts = FactConverter.convert_to_facts(result)
        doc_facts = len(facts)
        facts_extracted += doc_facts
        graph_populator.populate_from_facts(facts)

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

    return {"facts_extracted": facts_extracted, "documents": processed_docs}


def _extract_release_version_from_url(url: str) -> str:
    match = re.search(r"sprint-(\d+)", url, re.IGNORECASE)
    return f"1.{match.group(1)}" if match else ""


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
    Accepts: {"source": "all|releases|managed|hub|eos|url", "url": "..."}
    Returns: {"status": "success", "source": "...", "items_scraped": N, "facts_extracted": N}
    """
    data = request.get_json(force=True, silent=True) or {}
    source = data.get("source", "releases")

    try:
        if source == "all":
            from src.ingestion.eos_scraper import EndOfSupportScraper
            from src.ingestion.hub_scraper import HubExtensionsScraper
            from src.ingestion.managed_scraper import ManagedReleaseNotesScraper
            from src.ingestion.scraper import ReleaseNotesScraper

            run_results = []
            total_items = 0
            total_facts = 0

            # Releases
            scraper = ReleaseNotesScraper()
            releases = scraper.scrape_release_notes()
            for release in releases:
                version = release.get("version") or _extract_release_version_from_url(
                    release.get("url", "")
                )
                title = release.get("title") or f"ActiveGate {version}"
                if version:
                    graph_populator.ensure_activegate_release_node(
                        version, title, release.get("url", "")
                    )
            release_result = _process_documents_with_nlp(releases)
            total_items += len(releases)
            total_facts += release_result["facts_extracted"]
            run_results.append(
                {
                    "source": "releases",
                    "items_scraped": len(releases),
                    "facts_extracted": release_result["facts_extracted"],
                    "documents": release_result["documents"],
                }
            )

            # Managed release notes
            managed_scraper = ManagedReleaseNotesScraper()
            managed_releases = managed_scraper.scrape_release_notes()
            for release in managed_releases:
                version = release.get("version") or _extract_release_version_from_url(
                    release.get("url", "")
                )
                title = release.get("title") or f"Managed {version}"
                if version:
                    graph_populator.ensure_managed_release_node(
                        version=version,
                        title=title,
                        source_url=release.get("url", ""),
                        rollout_start=release.get("rollout_start"),
                        updated_on=release.get("updated_on"),
                    )

            managed_result = _process_documents_with_nlp(managed_releases)
            total_items += len(managed_releases)
            total_facts += managed_result["facts_extracted"]
            run_results.append(
                {
                    "source": "managed",
                    "items_scraped": len(managed_releases),
                    "facts_extracted": managed_result["facts_extracted"],
                    "documents": managed_result["documents"],
                }
            )

            # Hub (structured path)
            hub_scraper = HubExtensionsScraper()
            managed_items = hub_scraper.scrape_managed_catalog(include_feeds=True)
            hub_summary = graph_populator.ingest_hub_catalog(managed_items)
            total_items += len(managed_items)
            total_facts += hub_summary.get("constraints_upserted", 0)
            run_results.append(
                {
                    "source": "hub",
                    "items_scraped": len(managed_items),
                    "facts_extracted": hub_summary.get("constraints_upserted", 0),
                    "hub_summary": hub_summary,
                }
            )

            # EOS
            eos_scraper = EndOfSupportScraper()
            announcements = eos_scraper.scrape_end_of_support()
            eos_result = _process_documents_with_nlp(announcements)
            total_items += len(announcements)
            total_facts += eos_result["facts_extracted"]
            run_results.append(
                {
                    "source": "eos",
                    "items_scraped": len(announcements),
                    "facts_extracted": eos_result["facts_extracted"],
                    "documents": eos_result["documents"],
                }
            )

            return jsonify(
                {
                    "status": "success",
                    "source": "all",
                    "items_scraped": total_items,
                    "facts_extracted": total_facts,
                    "pipeline": run_results,
                }
            )

        if source == "releases":
            from src.ingestion.scraper import ReleaseNotesScraper

            scraper = ReleaseNotesScraper()
            releases = scraper.scrape_release_notes()
            logger.info("Release scraper found %d documents", len(releases))

            for release in releases:
                version = release.get("version") or _extract_release_version_from_url(
                    release.get("url", "")
                )
                title = release.get("title") or f"ActiveGate {version}"
                if version:
                    graph_populator.ensure_activegate_release_node(
                        version, title, release.get("url", "")
                    )
            processed = _process_documents_with_nlp(releases)
            return jsonify(
                {
                    "status": "success",
                    "source": source,
                    "items_scraped": len(releases),
                    "facts_extracted": processed["facts_extracted"],
                    "documents": processed["documents"],
                }
            )

        elif source == "managed":
            from src.ingestion.managed_scraper import ManagedReleaseNotesScraper

            scraper = ManagedReleaseNotesScraper()
            managed_releases = scraper.scrape_release_notes()
            logger.info("Managed scraper found %d documents", len(managed_releases))

            for release in managed_releases:
                version = release.get("version") or _extract_release_version_from_url(
                    release.get("url", "")
                )
                title = release.get("title") or f"Managed {version}"
                if version:
                    graph_populator.ensure_managed_release_node(
                        version=version,
                        title=title,
                        source_url=release.get("url", ""),
                        rollout_start=release.get("rollout_start"),
                        updated_on=release.get("updated_on"),
                    )

            processed = _process_documents_with_nlp(managed_releases)
            return jsonify(
                {
                    "status": "success",
                    "source": source,
                    "items_scraped": len(managed_releases),
                    "facts_extracted": processed["facts_extracted"],
                    "documents": processed["documents"],
                }
            )

        elif source == "hub":
            from src.ingestion.hub_scraper import HubExtensionsScraper

            scraper = HubExtensionsScraper()
            managed_items = scraper.scrape_managed_catalog(include_feeds=True)
            hub_summary = graph_populator.ingest_hub_catalog(managed_items)
            logger.info("Hub ingest summary: %s", hub_summary)
            return jsonify(
                {
                    "status": "success",
                    "source": source,
                    "items_scraped": len(managed_items),
                    "facts_extracted": hub_summary.get("constraints_upserted", 0),
                    "hub_summary": hub_summary,
                }
            )

        elif source == "eos":
            from src.ingestion.eos_scraper import EndOfSupportScraper

            scraper = EndOfSupportScraper()
            announcements = scraper.scrape_end_of_support()
            logger.info("EOS scraper found %d announcements", len(announcements))
            processed = _process_documents_with_nlp(announcements)
            return jsonify(
                {
                    "status": "success",
                    "source": source,
                    "items_scraped": len(announcements),
                    "facts_extracted": processed["facts_extracted"],
                    "documents": processed["documents"],
                }
            )

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
            logger.info(f"URL scraper processed {url}")
            processed = _process_documents_with_nlp(documents)
            return jsonify(
                {
                    "status": "success",
                    "source": source,
                    "items_scraped": 1,
                    "facts_extracted": processed["facts_extracted"],
                    "documents": processed["documents"],
                }
            )

        else:
            return (
                jsonify(
                    {
                        "error": f"Unknown source: {source}. Use: all, releases, managed, hub, eos, url"
                    }
                ),
                400,
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
        query = """
        MATCH (ag:ActiveGateVersion)
        WHERE coalesce(ag.is_release, false) = true
        RETURN ag.version as version
        ORDER BY ag.version
        """
        result = graph_conn.execute(query)
        versions = [record["version"] for record in result]
        return jsonify({"versions": versions})
    except Exception as e:
        return jsonify({"error": str(e), "versions": []}), 500
    finally:
        graph_conn.disconnect()


@app.route("/api/data/managed-versions", methods=["GET"])
def get_managed_versions():
    """Get all Managed cluster versions in the database."""
    graph_conn = _make_graph_connection()
    try:
        graph_conn.connect()
        query = """
        MATCH (mc:ManagedClusterVersion)
        WHERE coalesce(mc.is_release, false) = true
        RETURN mc.version as version
        ORDER BY mc.version
        """
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


@app.route("/api/data/hub-summary", methods=["GET"])
def get_hub_summary():
    """Get managed Hub ingestion coverage and health summary."""
    graph_conn = _make_graph_connection()
    try:
        graph_conn.connect()
        summary = GraphPopulator(graph_conn).get_hub_coverage_summary()
        return jsonify(summary)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
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
