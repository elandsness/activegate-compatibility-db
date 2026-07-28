"""
Flask API Backend for ActiveGate Compatibility Intelligence
Provides REST endpoints for chat, compatibility checks, and data management.
"""

import csv
import json
import logging
import os
import re
from io import StringIO
from typing import Any, Dict, List

from flask import Flask, Response, jsonify, request
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

BATCH_REQUIRED_HEADERS = [
    "current_activegate_version",
    "target_activegate_version",
    "managed_cluster_version",
    "os_family",
    "os_version",
    "extensions",
]

BATCH_OUTPUT_HEADERS = [
    "compatibility_status",
    "compatibility_confidence",
    "compatibility_issues",
    "compatibility_warnings",
    "compatibility_recommendations",
    "row_error",
]

MAX_BATCH_ROWS = 5000


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
                "batch_check": "/api/check/batch-csv (POST)",
                "check_template": "/api/check/template (GET)",
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


def _normalize_graph_value(value: Any) -> Any:
    """Convert Neo4j values to JSON-safe values."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _pick_node_key(labels: List[str], props: Dict[str, Any]) -> str:
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


def _relationship_status(relationship_type: str) -> str:
    """Map relationship type to high-level graph status."""
    if relationship_type in {
        "COMPATIBLE_WITH",
        "SUPPORTED_BY",
        "REQUIRES",
        "UPGRADEABLE_TO",
        "HAS_SETTING",
        "USES_MODULE",
    }:
        return "compatible"
    if relationship_type in {"DEPRECATED_IN", "END_OF_SUPPORT", "REQUIRES_UPGRADE"}:
        return "questionable"
    if relationship_type in {"INCOMPATIBLE_WITH"}:
        return "incompatible"
    return "unknown"


def _status_color(status: str) -> str:
    if status == "compatible":
        return "#22c55e"
    if status == "questionable":
        return "#f59e0b"
    if status == "incompatible":
        return "#ef4444"
    return "#94a3b8"


def _serialize_issues(items) -> str:
    if not items:
        return ""
    return " | ".join(
        f"[{item.severity}] {item.category}: {item.message}" for item in items
    )


def _serialize_recommendations(items: List[str]) -> str:
    if not items:
        return ""
    return " | ".join(items)


def _parse_extensions_cell(raw_extensions: str) -> List[Dict]:
    if not raw_extensions or not raw_extensions.strip():
        return []

    try:
        parsed = json.loads(raw_extensions)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid extensions JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise ValueError(
            'Extensions must be a JSON object map like {"ext-id": "1.2.3"}'
        )

    extensions = []
    for ext_id, ext_version in parsed.items():
        if not str(ext_id).strip():
            raise ValueError("Extensions map contains an empty extension id")

        extensions.append(
            {
                "id": str(ext_id).strip(),
                "version": "" if ext_version is None else str(ext_version).strip(),
            }
        )

    return extensions


def _build_row_findings(row: Dict[str, str]) -> Dict[str, str]:
    findings = {
        "compatibility_status": "",
        "compatibility_confidence": "",
        "compatibility_issues": "",
        "compatibility_warnings": "",
        "compatibility_recommendations": "",
        "row_error": "",
    }

    current = (row.get("current_activegate_version") or "").strip()
    target = (row.get("target_activegate_version") or "").strip()
    managed = (row.get("managed_cluster_version") or "").strip() or None
    os_family = (row.get("os_family") or "").strip() or None
    os_version = (row.get("os_version") or "").strip() or None
    raw_extensions = row.get("extensions") or ""

    if not current or not target:
        findings["row_error"] = (
            "Missing required values for current_activegate_version and/or target_activegate_version"
        )
        return findings

    try:
        extensions = _parse_extensions_cell(raw_extensions)
    except ValueError as exc:
        findings["row_error"] = str(exc)
        return findings

    result = reasoner.check_upgrade_compatibility(
        current_version=current,
        target_version=target,
        os_family=os_family,
        os_version=os_version,
        managed_cluster_version=managed,
        extensions=extensions,
        use_graph=reasoner.graph_query is not None,
    )

    findings["compatibility_status"] = result.status.value
    findings["compatibility_confidence"] = f"{result.confidence:.2f}"
    findings["compatibility_issues"] = _serialize_issues(result.issues)
    findings["compatibility_warnings"] = _serialize_issues(result.warnings)
    findings["compatibility_recommendations"] = _serialize_recommendations(
        result.recommendations
    )

    return findings


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
    data = request.get_json() or {}
    message = data.get("message", "")
    context = data.get("context", {})

    if not message:
        return jsonify({"error": "No message provided"}), 400

    # Process the query
    parsed = query_processor.process_query(message, context=context)
    collected_context = parsed.get("context", {})

    if not parsed.get("ready_for_decision", False):
        return jsonify(
            {
                "response": parsed.get("follow_up_prompt"),
                "citations": [],
                "status": "NEEDS_INFO",
                "missing_fields": parsed.get("missing_fields", []),
                "required_fields": query_processor.REQUIRED_CONTEXT_FIELDS,
                "collected_context": collected_context,
            }
        )

    current = collected_context.get("current_activegate_version")
    target = collected_context.get("target_activegate_version")
    os_family = collected_context.get("os_family")
    os_version = collected_context.get("os_version")
    managed_cluster_version = collected_context.get("managed_cluster_version")
    extensions = collected_context.get("extensions") or []

    # Run compatibility check, querying the graph when available
    result = reasoner.check_upgrade_compatibility(
        current_version=current,
        target_version=target,
        os_family=os_family,
        os_version=os_version,
        managed_cluster_version=managed_cluster_version,
        extensions=extensions,
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
            "collected_context": collected_context,
            "missing_fields": [],
        }
    )


@app.route("/api/check", methods=["POST"])
def check_compatibility():
    """
    Structured compatibility check endpoint.
    Accepts: {"current": "1.330", "target": "1.335", "os_family": "Red Hat Enterprise Linux", ...}
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


@app.route("/api/check/template", methods=["GET"])
def check_template_csv():
    """Download a CSV template for batch compatibility checks."""
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=BATCH_REQUIRED_HEADERS)
    writer.writeheader()
    writer.writerow(
        {
            "current_activegate_version": "1.330",
            "target_activegate_version": "1.335",
            "managed_cluster_version": "1.335",
            "os_family": "Red Hat Enterprise Linux",
            "os_version": "8",
            "extensions": '{"custom-ext":"2.0.0"}',
        }
    )

    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = (
        "attachment; filename=activegate-compatibility-template.csv"
    )
    return response


@app.route("/api/check/batch-csv", methods=["POST"])
def batch_check_csv():
    """Process a CSV file and append compatibility findings columns per row."""
    upload = request.files.get("file")
    if upload is None:
        return (
            jsonify(
                {"error": "No file uploaded. Use multipart/form-data with field 'file'"}
            ),
            400,
        )

    try:
        csv_content = upload.read().decode("utf-8")
    except UnicodeDecodeError:
        return jsonify({"error": "Unable to decode file as UTF-8 CSV"}), 400

    reader = csv.DictReader(StringIO(csv_content))
    if not reader.fieldnames:
        return jsonify({"error": "Uploaded CSV has no header row"}), 400

    missing_headers = [
        header for header in BATCH_REQUIRED_HEADERS if header not in reader.fieldnames
    ]
    if missing_headers:
        return (
            jsonify(
                {
                    "error": "Missing required CSV headers",
                    "missing_headers": missing_headers,
                    "required_headers": BATCH_REQUIRED_HEADERS,
                }
            ),
            400,
        )

    input_headers = list(reader.fieldnames)
    output_headers = input_headers + [
        h for h in BATCH_OUTPUT_HEADERS if h not in input_headers
    ]

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=output_headers)
    writer.writeheader()

    row_count = 0
    for row in reader:
        row_count += 1
        if row_count > MAX_BATCH_ROWS:
            return (
                jsonify(
                    {
                        "error": f"CSV exceeds max supported rows ({MAX_BATCH_ROWS})",
                        "max_rows": MAX_BATCH_ROWS,
                    }
                ),
                400,
            )

        findings = _build_row_findings(row)
        row_out = dict(row)
        row_out.update(findings)
        writer.writerow(row_out)

    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = (
        "attachment; filename=activegate-compatibility-with-findings.csv"
    )
    return response


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


@app.route("/api/data/graph", methods=["GET"])
def get_graph_data():
    """Return node/edge payload for interactive graph rendering."""
    graph_conn = _make_graph_connection()
    try:
        graph_conn.connect()

        activegate_version = request.args.get("activegate_version")
        raw_limit = request.args.get("limit", "500")
        try:
            limit = max(50, min(int(raw_limit), 1200))
        except ValueError:
            limit = 500

        activegate_limit = max(10, min(limit // 2, 250))

        query = """
        MATCH (ag:ActiveGateVersion)
        WHERE coalesce(ag.is_release, false) = true
          AND ($activegate_version IS NULL OR ag.version = $activegate_version)
        WITH ag
        ORDER BY ag.version DESC
        LIMIT $activegate_limit
        MATCH (ag)-[r]-(other)
        WHERE (
          other:ManagedClusterVersion OR
          other:OSVersion OR
          other:Extension OR
          other:HubItem OR
          other:HubItemRelease OR
          other:Module OR
          other:Setting OR
          other:ActiveGateVersion
        )
        WITH DISTINCT r, startNode(r) AS src, endNode(r) AS dst
        RETURN labels(src) AS source_labels,
               properties(src) AS source_props,
               labels(dst) AS target_labels,
               properties(dst) AS target_props,
               type(r) AS relationship_type,
               properties(r) AS relationship_props
        LIMIT $edge_limit
        """

        rows = graph_conn.execute(
            query,
            {
                "activegate_version": activegate_version,
                "activegate_limit": activegate_limit,
                "edge_limit": limit,
            },
        )

        nodes_by_id: Dict[str, Dict[str, Any]] = {}
        edges: List[Dict[str, Any]] = []

        for idx, row in enumerate(rows):
            source_labels = row.get("source_labels") or []
            target_labels = row.get("target_labels") or []
            source_props = row.get("source_props") or {}
            target_props = row.get("target_props") or {}

            source_type = source_labels[0] if source_labels else "Node"
            target_type = target_labels[0] if target_labels else "Node"

            source_key = _pick_node_key(source_labels, source_props)
            target_key = _pick_node_key(target_labels, target_props)

            source_id = f"{source_type}:{source_key}"
            target_id = f"{target_type}:{target_key}"

            if source_id not in nodes_by_id:
                nodes_by_id[source_id] = {
                    "id": source_id,
                    "label": source_key,
                    "type": source_type,
                    "properties": {
                        k: _normalize_graph_value(v) for k, v in source_props.items()
                    },
                }

            if target_id not in nodes_by_id:
                nodes_by_id[target_id] = {
                    "id": target_id,
                    "label": target_key,
                    "type": target_type,
                    "properties": {
                        k: _normalize_graph_value(v) for k, v in target_props.items()
                    },
                }

            rel_type = row.get("relationship_type") or "RELATED_TO"
            rel_props = row.get("relationship_props") or {}
            status = _relationship_status(rel_type)

            edges.append(
                {
                    "id": f"e{idx}",
                    "source": source_id,
                    "target": target_id,
                    "relationship": rel_type,
                    "status": status,
                    "color": _status_color(status),
                    "confidence": _normalize_graph_value(rel_props.get("confidence")),
                    "verified": _normalize_graph_value(rel_props.get("verified")),
                }
            )

        status_counts = {
            "compatible": 0,
            "questionable": 0,
            "incompatible": 0,
            "unknown": 0,
        }
        for edge in edges:
            status_counts[edge["status"]] = status_counts.get(edge["status"], 0) + 1

        return jsonify(
            {
                "nodes": list(nodes_by_id.values()),
                "edges": edges,
                "status_counts": status_counts,
                "filters": {
                    "activegate_version": activegate_version,
                    "limit": limit,
                },
            }
        )
    except Exception as e:
        return jsonify({"error": str(e), "nodes": [], "edges": []}), 500
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
