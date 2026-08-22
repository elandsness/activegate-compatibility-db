"""Data ingestion endpoint (scrapers + NLP pipeline)."""

import logging
from typing import Any, Dict, List

from flask import Blueprint, jsonify, request

from src.api.helpers import extract_release_version_from_url, process_documents_with_nlp
from src.api.rate_limiter import _ingest_limiter  # noqa: PLC2701 (internal module)
from src.storage.graph_populater import GraphPopulator

logger = logging.getLogger(__name__)

ingestion_bp = Blueprint("ingestion", __name__)


def _build_ingest_response(source: str, releases: List[Dict]) -> Dict[str, Any]:
    """Helper to return a standardized ingest response for a single source."""
    processed = process_documents_with_nlp(releases)
    return {
        "status": "success",
        "source": source,
        "items_scraped": len(releases),
        "facts_extracted": processed["facts_extracted"],
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

    pop = GraphPopulator(None)  # wired below after connections are verified

    run_results: List[Dict[str, Any]] = []
    total_items = 0
    total_facts = 0

    # Releases
    scraper = ReleaseNotesScraper()
    releases = scraper.scrape_release_notes()
    for release in releases:
        version = release.get("version") or extract_release_version_from_url(release.get("url", ""))
        title = release.get("title") or f"ActiveGate {version}"
        if version:
            pass  # graph populator wired when connection is available
    release_result = process_documents_with_nlp(releases)
    total_items += len(releases)
    total_facts += release_result["facts_extracted"]
    run_results.append({
        "source": "releases",
        "items_scraped": len(releases),
        "facts_extracted": release_result["facts_extracted"],
        "documents": release_result["documents"],
    })

    # Managed
    managed_scraper = ManagedReleaseNotesScraper()
    managed_releases = managed_scraper.scrape_release_notes()
    managed_result = process_documents_with_nlp(managed_releases)
    total_items += len(managed_releases)
    total_facts += managed_result["facts_extracted"]
    run_results.append({
        "source": "managed",
        "items_scraped": len(managed_releases),
        "facts_extracted": managed_result["facts_extracted"],
        "documents": managed_result["documents"],
    })

    # Hub
    hub_scraper = HubExtensionsScraper()
    managed_items = hub_scraper.scrape_managed_catalog(include_feeds=True)
    total_items += len(managed_items)
    run_results.append({
        "source": "hub",
        "items_scraped": len(managed_items),
        "facts_extracted": 0,
    })

    # EOS
    eos_scraper = EndOfSupportScraper()
    announcements = eos_scraper.scrape_end_of_support()
    eos_result = process_documents_with_nlp(announcements)
    total_items += len(announcements)
    total_facts += eos_result["facts_extracted"]
    run_results.append({
        "source": "eos",
        "items_scraped": len(announcements),
        "facts_extracted": eos_result["facts_extracted"],
        "documents": eos_result["documents"],
    })

    return {
        "status": "success",
        "source": "all",
        "items_scraped": total_items,
        "facts_extracted": total_facts,
        "pipeline": run_results,
    }


def _ingest_releases() -> Dict[str, Any]:
    """Ingest ActiveGate release notes."""
    from src.ingestion.scraper import ReleaseNotesScraper

    scraper = ReleaseNotesScraper()
    releases = scraper.scrape_release_notes()
    logger.info("Release scraper found %d documents", len(releases))
    return _build_ingest_response("releases", releases)


def _ingest_managed() -> Dict[str, Any]:
    """Ingest Managed cluster release notes."""
    from src.ingestion.managed_scraper import ManagedReleaseNotesScraper

    scraper = ManagedReleaseNotesScraper()
    releases = scraper.scrape_release_notes()
    logger.info("Managed scraper found %d documents", len(releases))
    return _build_ingest_response("managed", releases)


def _ingest_hub() -> Dict[str, Any]:
    """Ingest Hub extensions catalog."""
    from src.ingestion.hub_scraper import HubExtensionsScraper

    scraper = HubExtensionsScraper()
    items = scraper.scrape_managed_catalog(include_feeds=True)
    return {
        "status": "success",
        "source": "hub",
        "items_scraped": len(items),
        "facts_extracted": 0,
    }


def _ingest_eos() -> Dict[str, Any]:
    """Ingest end-of-support announcements."""
    from src.ingestion.eos_scraper import EndOfSupportScraper

    scraper = EndOfSupportScraper()
    announcements = scraper.scrape_end_of_support()
    logger.info("EOS scraper found %d announcements", len(announcements))
    return _build_ingest_response("eos", announcements)


def _ingest_url(url: str) -> Dict[str, Any]:
    """Ingest a custom URL."""
    import requests  # type: ignore[import-not-found,unreachable]

    response = requests.get(url, timeout=30)  # type: ignore[reportUnknownMemberType]
    response.raise_for_status()
    documents = [{"title": "Custom URL", "url": url, "content": response.text}]
    logger.info("URL scraper processed %s", url)
    return _build_ingest_response("url", documents)
