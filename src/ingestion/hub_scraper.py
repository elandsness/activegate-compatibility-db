import html
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HubExtensionsScraper:
    """Ingest Hub managed catalog and release feed metadata."""

    HUB_LISTING_URL = "https://www.dynatrace.com/hub/?managed=true"
    PUBLIC_HUB_API = "https://hub-manager.hub.central.dynatrace.com/api/v1/public-hub/"
    FEED_ROOT = (
        "https://hub-manager.hub.central.dynatrace.com/api/v1/public-hub/feed"
    )
    USER_AGENT = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    def __init__(self, base_url: str = HUB_LISTING_URL):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})

    def scrape_extensions(self) -> List[Dict]:
        """Backward-compatible wrapper used by tests and legacy callers."""
        items = self.scrape_managed_catalog(include_feeds=True)
        extensions = []
        for item in items:
            if item.get("extension_type") != "extension-2":
                continue
            latest_release = item.get("releases", [{}])[0]
            extensions.append(
                {
                    "name": item.get("title") or item.get("slug", "Unknown Extension"),
                    "url": item.get("details_url", ""),
                    "data": {
                        "extension_type": item.get("extension_type"),
                        "release_latest_version": item.get("release_latest_version"),
                        "latest_release": latest_release,
                    },
                    "scraped_at": item.get("scraped_at"),
                }
            )
        logger.info("Prepared %d extension-2 entries from managed catalog", len(extensions))
        return extensions

    def scrape_managed_catalog(self, include_feeds: bool = True) -> List[Dict]:
        """Fetch all managed technologies from Hub and enrich with release feeds."""
        payload = self._fetch_catalog()
        technologies = payload.get("technologies") or []
        now_iso = datetime.now(timezone.utc).isoformat()

        managed_items = []
        for raw in technologies:
            if raw.get("saas_only") is True:
                continue

            slug = raw.get("slug")
            if not slug:
                continue

            item = {
                "hub_id": raw.get("id") or slug,
                "slug": slug,
                "title": raw.get("title") or slug,
                "description": raw.get("description") or "",
                "extension_type": raw.get("extension_type") or "unknown",
                "managed": True,
                "supported_by_dt": bool(raw.get("supported_by_dt")),
                "details_url": f"https://www.dynatrace.com/hub/detail/{slug}/",
                "release_latest_version": (raw.get("details") or {}).get(
                    "release_latest_version"
                ),
                "scraped_at": now_iso,
                "raw": {
                    "author": raw.get("author"),
                    "documentation_link": raw.get("documentation_link"),
                    "link_to": raw.get("link_to"),
                    "providers": raw.get("providers"),
                    "tags": raw.get("tags"),
                },
                "releases": [],
                "feed_url": None,
                "feed_status": "not_requested",
            }

            if include_feeds:
                feed_data = self._fetch_release_feed(item)
                item["feed_url"] = feed_data.get("feed_url")
                item["feed_status"] = feed_data.get("status", "missing")
                item["releases"] = feed_data.get("releases", [])

            managed_items.append(item)

        logger.info("Loaded %d managed Hub items", len(managed_items))
        return managed_items

    def _fetch_catalog(self) -> Dict:
        response = self.session.get(self.PUBLIC_HUB_API, timeout=60)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "technologies" not in payload:
            raise ValueError("Unexpected Hub catalog payload shape")
        return payload

    def _fetch_release_feed(self, item: Dict) -> Dict:
        candidates = self._candidate_feed_paths(item)
        for path in candidates:
            feed_url = f"{self.FEED_ROOT}/{path}/"
            try:
                response = self.session.get(feed_url, timeout=45)
                if response.status_code == 404:
                    continue
                response.raise_for_status()
                releases = self._parse_feed_entries(response.text, item)
                return {"feed_url": feed_url, "releases": releases, "status": "ok"}
            except Exception as exc:
                logger.warning(
                    "Feed fetch failed for %s at %s: %s",
                    item.get("slug"),
                    feed_url,
                    exc,
                )

        return {"feed_url": None, "releases": [], "status": "missing"}

    def _candidate_feed_paths(self, item: Dict) -> List[str]:
        slug = item.get("slug")
        ext_type = (item.get("extension_type") or "").lower()

        if ext_type == "classic-app" or ext_type == "app":
            return [f"apps/{slug}", f"extensions/{slug}"]
        if ext_type == "extension-2":
            return [f"extensions/{slug}", f"apps/{slug}"]

        # Unknown/null type: extensions-first was empirically successful for many entries.
        return [f"extensions/{slug}", f"apps/{slug}"]

    def _parse_feed_entries(self, xml_text: str, item: Dict) -> List[Dict]:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as exc:
            logger.warning("Invalid feed XML for %s: %s", item.get("slug"), exc)
            return []

        channel = root.find("channel")
        if channel is None:
            return []

        releases = []
        for entry in channel.findall("item"):
            title = (entry.findtext("title") or "").strip()
            description_html = entry.findtext("description") or ""
            description_text = self._html_to_text(description_html)
            pub_date = (entry.findtext("pubDate") or "").strip()
            version = self._extract_release_version(title)
            published_at = self._parse_pub_date(pub_date)

            releases.append(
                {
                    "title": title,
                    "version": version,
                    "published_at": published_at.isoformat() if published_at else None,
                    "published_at_epoch": int(published_at.timestamp())
                    if published_at
                    else None,
                    "raw_description": description_text,
                    "source_url": item.get("details_url", ""),
                    "constraints": self._extract_constraints(
                        description_text, item.get("details_url", "")
                    ),
                }
            )

        releases.sort(key=lambda r: (r.get("published_at_epoch") or 0), reverse=True)
        return releases

    def _parse_pub_date(self, value: str) -> Optional[datetime]:
        if not value:
            return None
        patterns = [
            "%a, %d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S GMT",
        ]
        for pattern in patterns:
            try:
                parsed = datetime.strptime(value, pattern)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed
            except ValueError:
                continue
        return None

    def _extract_release_version(self, title: str) -> Optional[str]:
        match = re.search(r"(\d+\.\d+(?:\.\d+)*)", title)
        return match.group(1) if match else None

    def _extract_constraints(self, text: str, source_url: str) -> List[Dict]:
        constraints = []

        patterns = [
            (
                "activegate",
                r"minimum\s+(?:EEC|ActiveGate)\s+version[^\d]*(\d+\.\d+(?:\.\d+)*)",
                0.95,
            ),
            (
                "activegate",
                r"requires?[^\n\.]{0,80}ActiveGate[^\d]*(\d+\.\d+(?:\.\d+)*)",
                0.85,
            ),
            (
                "managed_cluster",
                r"minimum\s+Dynatrace\s+version[^\d]*(\d+\.\d+(?:\.\d+)*)",
                0.95,
            ),
            (
                "managed_cluster",
                r"requires?[^\n\.]{0,80}Dynatrace[^\d]*(\d+\.\d+(?:\.\d+)*)",
                0.85,
            ),
        ]

        for component, pattern, confidence in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                min_version = match.group(1)
                raw_line = self._slice_sentence(text, match.start(), match.end())
                constraints.append(
                    {
                        "component": component,
                        "operator": ">=",
                        "min_version": min_version,
                        "confidence": confidence,
                        "source_url": source_url,
                        "raw_text": raw_line,
                    }
                )

        # De-duplicate by component + version + operator.
        unique = {}
        for constraint in constraints:
            key = (
                constraint["component"],
                constraint["operator"],
                constraint["min_version"],
            )
            if key not in unique or unique[key]["confidence"] < constraint["confidence"]:
                unique[key] = constraint

        return list(unique.values())

    def _slice_sentence(self, text: str, start: int, end: int) -> str:
        left = text.rfind("\n", 0, start)
        right = text.find("\n", end)
        if left == -1:
            left = 0
        if right == -1:
            right = len(text)
        sentence = text[left:right].strip()
        if not sentence:
            sentence = text[max(0, start - 80) : min(len(text), end + 80)].strip()
        return sentence[:500]

    def _html_to_text(self, html_fragment: str) -> str:
        unescaped = html.unescape(html_fragment)
        soup = BeautifulSoup(unescaped, "lxml")
        text = soup.get_text("\n", strip=True)
        return "\n".join(line.strip() for line in text.splitlines() if line.strip())


if __name__ == "__main__":
    scraper = HubExtensionsScraper()
    managed_items = scraper.scrape_managed_catalog(include_feeds=True)

    import json

    with open("scraped_extensions.json", "w", encoding="utf-8") as f:
        json.dump(managed_items, f, indent=2)

    print(f"Scraped {len(managed_items)} managed hub items")
