import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ManagedReleaseNotesScraper:
    """Scrape Dynatrace Managed release notes and sprint pages."""

    def __init__(
        self, base_url: str = "https://docs.dynatrace.com/managed/whats-new/managed"
    ):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
                )
            }
        )

    def scrape_release_notes(self) -> List[Dict]:
        """Scrape Managed sprint pages and return release-note documents."""
        try:
            response = self.session.get(self.base_url, timeout=30)
            response.raise_for_status()
            html_text = response.text

            sprint_urls = self._extract_sprint_urls(html_text)
            logger.info("Found %d Managed sprint links", len(sprint_urls))

            releases = []
            for url in sprint_urls:
                try:
                    content, metadata = self._scrape_release_page(url)
                    version = self._extract_release_version(url, content)
                    title = f"Managed {version}" if version else "Managed Release"

                    if not content or len(content.strip()) < 200:
                        logger.warning("Skipping %s due to short content", url)
                        continue

                    releases.append(
                        {
                            "title": title,
                            "version": version,
                            "url": url,
                            "content": content,
                            "rollout_start": metadata.get("rollout_start"),
                            "updated_on": metadata.get("updated_on"),
                            "scraped_at": str(datetime.now()),
                        }
                    )
                except Exception as exc:
                    logger.warning("Failed scraping managed sprint %s: %s", url, exc)

            logger.info("Total Managed releases scraped: %d", len(releases))
            return releases
        except Exception as e:
            logger.error("Error scraping Managed releases: %s", e)
            return []

    def _extract_sprint_urls(self, html_text: str) -> List[str]:
        patterns = [
            r'"(\/managed\/whats-new\/managed\/sprint-\d+)"',
            r'"(\/whats-new\/managed\/sprint-\d+)"',
            r'(\/managed\/whats-new\/managed\/sprint-\d+)',
            r'(\/whats-new\/managed\/sprint-\d+)',
        ]

        found = set()
        for pattern in patterns:
            for match in re.findall(pattern, html_text):
                href = match.replace("\\/", "/")
                href = href.strip()
                if not href:
                    continue
                if href.startswith("http"):
                    full_url = href
                elif href.startswith("/whats-new/managed/"):
                    full_url = f"https://docs.dynatrace.com/managed{href}"
                else:
                    full_url = f"https://docs.dynatrace.com{href}"
                full_url = full_url.rstrip("/")
                found.add(full_url)

        # Keep only numeric sprint URLs and sort newest first.
        def sprint_key(url: str) -> int:
            m = re.search(r"sprint-(\d+)", url)
            return int(m.group(1)) if m else 0

        urls = [u for u in found if re.search(r"/sprint-\d+$", u)]
        urls.sort(key=sprint_key, reverse=True)
        return urls

    def _extract_release_version(self, url: str, content_text: str = "") -> str:
        url_match = re.search(r"sprint-(\d+)", url, re.IGNORECASE)
        if url_match:
            return f"1.{url_match.group(1)}"

        title_match = re.search(
            r"Dynatrace\s+Managed\s+(\d+\.\d+)", content_text, re.IGNORECASE
        )
        if title_match:
            return title_match.group(1)

        return ""

    def _scrape_release_page(self, url: str) -> (str, Dict[str, Optional[str]]):
        response = self.session.get(url, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, "lxml")

        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.extract()

        content_selectors = [
            "div.content",
            "main",
            "article",
            "div.markdown-body",
            "div.article-content",
            ".documentation-content",
            "div.main-content",
            "div.content-wrapper",
            '[role="main"]',
            ".doc-content",
        ]

        content_div = None
        for selector in content_selectors:
            content_div = soup.select_one(selector)
            if content_div:
                break

        if not content_div:
            content_div = soup.find("body")

        text = content_div.get_text(separator="\n", strip=True) if content_div else ""
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        relevant_lines = []
        for line in lines:
            lower = line.lower()
            if any(
                keyword in lower
                for keyword in [
                    "managed",
                    "activegate",
                    "version",
                    "release notes",
                    "rollout start",
                    "updated on",
                    "compatible",
                    "requires",
                    "support",
                    "cluster",
                    "operating systems support",
                ]
            ):
                relevant_lines.append(line)

        final_lines = relevant_lines if relevant_lines else lines[:120]
        content = "\n".join(final_lines)

        metadata = {
            "rollout_start": self._extract_metadata_date(
                text, r"Rollout\s+start\s+on\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})"
            ),
            "updated_on": self._extract_metadata_date(
                text, r"Updated\s+on\s+([A-Za-z]{3}\s+\d{1,2},\s+\d{4})"
            ),
        }
        return content, metadata

    def _extract_metadata_date(self, text: str, pattern: str) -> Optional[str]:
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1) if match else None


if __name__ == "__main__":
    scraper = ManagedReleaseNotesScraper()
    releases = scraper.scrape_release_notes()

    import json

    with open("scraped_managed_releases.json", "w") as f:
        json.dump(releases, f, indent=2)

    print(f"Scraped {len(releases)} managed releases")
