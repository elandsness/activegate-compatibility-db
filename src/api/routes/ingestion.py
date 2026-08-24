"""Data ingestion endpoint (scrapers + NLP pipeline)."""

import logging
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from src.api.helpers import extract_release_version_from_url, process_documents_with_nlp
from src.api.rate_limiter import _ingest_limiter  # noqa: PLC2701 (internal module)
from src.storage.graph_populater import GraphPopulator

logger = logging.getLogger(__name__)

ingestion_bp = Blueprint("ingestion", __name__)


def _build_ingest_response(source: str, releases: List[Dict], graph_populator=None) -> Dict[str, Any]:
    """Helper to return a standardized ingest response for a single source."""
    processed = process_documents_with_nlp(releases, graph_populator=graph_populator)
    return {
        "status": "success",
        "source": source,
        "items_scraped": len(releases),
        "facts_extracted": processed["facts_extracted"],
        "facts_stored": processed.get("facts_stored", 0),
        "documents": processed["documents"],
    }


@ingestion_bp.route("/ingest", methods=["POST"])
def ingest_data():
    """Ingest data from various sources.

    Accepts:: {"source": "all|releases|managed|hub|eos|url", "url": "..."}
    Returns:: {status, source, items_scraped, facts_extracted}
    """
    data = request.get_json(force=True, silent=True) or {}
    source = data.get("source", "releases")

    # Rate-limit to prevent abuse of the scraping pipeline
    if not _ingest_limiter.allow():
        return jsonify({
            "error": "Ingest is currently in progress or was recently run. "
                     "Please wait 30 seconds between ingest calls.",
        }), 429

    _ingest_limiter.start()
    try:
        if source == "all":
            return _ingest_all()

        if source == "releases":
            return _ingest_releases()

        if source == "managed":
            return _ingest_managed()

        if source == "hub":
            return _ingest_hub()

        if source == "eos":
            return _ingest_eos()

        if source == "url":
            url = data.get("url")
            if not url:
                return jsonify({"error": "URL required for url source"}), 400
            return _ingest_url(url)

        return jsonify({
            "error": f"Unknown source: {source}. Use: all, releases, managed, hub, eos, url",
        }), 400

    except Exception as exc:
        logger.error("Ingest error: %s", exc, exc_info=True)
        return jsonify({"error": str(exc)}), 500
    finally:
        _ingest_limiter.finish()


# ------------------------------------------------------------------ #
#  Per-source handlers extracted from the old monolithic if/elif chain #
# ------------------------------------------------------------------ #

def _ingest_all() -> Dict[str, Any]:
    """Ingest all data sources."""
    from src.ingestion.eos_scraper import EndOfSupportScraper
    from src.ingestion.hub_scraper import HubExtensionsScraper
    from src.ingestion.managed_scraper import ManagedReleaseNotesScraper
    from src.ingestion.scraper import ReleaseNotesScraper
    from src.storage.connection_manager import get_manager

    # Get the shared connected manager
    mgr = get_manager()
    logger.info("Ingest all: manager connected=%s, driver=%s", mgr.is_connected, bool(mgr.driver))
    if mgr.is_connected:
        pop = GraphPopulator(mgr)
        logger.info("Ingest all: GraphPopulator created with connected manager")
    else:
        pop = None
        logger.warning("Neo4j not connected — ingestion will not persist data")

    run_results: List[Dict[str, Any]] = []
    total_items = 0
    total_facts = 0
    total_stored = 0

    # Releases
    scraper = ReleaseNotesScraper()
    releases = scraper.scrape_release_notes()
    release_result = process_documents_with_nlp(releases, graph_populator=pop)
    total_items += len(releases)
    total_facts += release_result["facts_extracted"]
    total_stored += release_result.get("facts_stored", 0)
    run_results.append({
        "source": "releases",
        "items_scraped": len(releases),
        "facts_extracted": release_result["facts_extracted"],
        "facts_stored": release_result.get("facts_stored", 0),
        "documents": release_result["documents"],
    })

    # Managed
    managed_scraper = ManagedReleaseNotesScraper()
    managed_releases = managed_scraper.scrape_release_notes()
    managed_result = process_documents_with_nlp(managed_releases, graph_populator=pop)
    total_items += len(managed_releases)
    total_facts += managed_result["facts_extracted"]
    total_stored += managed_result.get("facts_stored", 0)
    run_results.append({
        "source": "managed",
        "items_scraped": len(managed_releases),
        "facts_extracted": managed_result["facts_extracted"],
        "facts_stored": managed_result.get("facts_stored", 0),
        "documents": managed_result["documents"],
    })

    # Hub
    hub_scraper = HubExtensionsScraper()
    managed_items = hub_scraper.scrape_managed_catalog(include_feeds=True)
    if pop:
        pop.ingest_hub_catalog(managed_items)
    total_items += len(managed_items)
    run_results.append({
        "source": "hub",
        "items_scraped": len(managed_items),
        "facts_extracted": 0,
        "facts_stored": 0,
    })

    # EOS
    eos_scraper = EndOfSupportScraper()
    announcements = eos_scraper.scrape_end_of_support()
    eos_result = process_documents_with_nlp(announcements, graph_populator=pop)
    total_items += len(announcements)
    total_facts += eos_result["facts_extracted"]
    total_stored += eos_result.get("facts_stored", 0)
    run_results.append({
        "source": "eos",
        "items_scraped": len(announcements),
        "facts_extracted": eos_result["facts_extracted"],
        "facts_stored": eos_result.get("facts_stored", 0),
        "documents": eos_result["documents"],
    })

    return {
        "status": "success",
        "source": "all",
        "items_scraped": total_items,
        "facts_extracted": total_facts,
        "facts_stored": total_stored,
        "pipeline": run_results,
    }


def _ingest_releases() -> Dict[str, Any]:
    """Ingest ActiveGate release notes."""
    from src.ingestion.scraper import ReleaseNotesScraper
    from src.storage.graph_populater import GraphPopulator

    scraper = ReleaseNotesScraper()
    releases = scraper.scrape_release_notes()
    logger.info("Release scraper found %d documents", len(releases))

    # Use the shared connection manager for persistence
    from src.storage.connection_manager import get_manager
    mgr = get_manager()
    if mgr.is_connected:
        pop = GraphPopulator(mgr)
    else:
        pop = None

    return _build_ingest_response("releases", releases, graph_populator=pop)


def _ingest_managed() -> Dict[str, Any]:
    """Ingest Managed cluster release notes."""
    from src.ingestion.managed_scraper import ManagedReleaseNotesScraper
    from src.storage.graph_populater import GraphPopulator

    scraper = ManagedReleaseNotesScraper()
    releases = scraper.scrape_release_notes()
    logger.info("Managed scraper found %d documents", len(releases))

    from src.storage.connection_manager import get_manager
    mgr = get_manager()
    pop = GraphPopulator(mgr) if mgr.is_connected else None

    return _build_ingest_response("managed", releases, graph_populator=pop)


def _ingest_hub() -> Dict[str, Any]:
    """Ingest Hub extensions catalog."""
    from src.ingestion.hub_scraper import HubExtensionsScraper
    from src.storage.connection_manager import get_manager
    from src.storage.graph_populater import GraphPopulator

    scraper = HubExtensionsScraper()
    items = scraper.scrape_managed_catalog(include_feeds=True)

    # Hub ingestion uses a different path
    if get_manager().is_connected:
        pop = GraphPopulator(get_manager())
        pop.ingest_hub_catalog(items)

    return {
        "status": "success",
        "source": "hub",
        "items_scraped": len(items),
        "facts_extracted": 0,
    }


def _ingest_eos() -> Dict[str, Any]:
    """Ingest end-of-support announcements."""
    from src.ingestion.eos_scraper import EndOfSupportScraper
    from src.storage.graph_populater import GraphPopulator

    scraper = EndOfSupportScraper()
    announcements = scraper.scrape_end_of_support()
    logger.info("EOS scraper found %d announcements", len(announcements))

    from src.storage.connection_manager import get_manager
    mgr = get_manager()
    pop = GraphPopulator(mgr) if mgr.is_connected else None

    return _build_ingest_response("eos", announcements, graph_populator=pop)


def _ingest_url(url: str) -> Dict[str, Any]:
    """Ingest a custom URL."""
    import requests  # type: ignore[import-not-found,unreachable]

    response = requests.get(url, timeout=30)  # type: ignore[reportUnknownMemberType]
    response.raise_for_status()
    documents = [{"title": "Custom URL", "url": url, "content": response.text}]
    logger.info("URL scraper processed %s", url)
    return _build_ingest_response("url", documents)
