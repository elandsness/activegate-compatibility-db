import logging
import re
from datetime import datetime
from typing import Dict, List

import requests
from bs4 import BeautifulSoup

from src.ingestion.retry import retry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ReleaseNotesScraper:
    def __init__(
        self, base_url: str = "https://docs.dynatrace.com/managed/whats-new/activegate"
    ):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        )

    @retry(max_retries=3, base_delay=1.0)
    def scrape_release_notes(self) -> List[Dict]:
        """
        Scrape the ActiveGate release notes section and extract individual sprint releases.
        Returns a list of dicts with title, version, url, and content.
        """
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "lxml")

            content_area = soup.select_one("div.content") or soup.body
            all_links = content_area.find_all("a", href=True)

            release_candidates = []
            for link in all_links:
                href = link.get("href")
                text = link.get_text().strip()

                if self._is_activegate_release_link(href, text):
                    if href.startswith("http"):
                        full_url = href
                    elif href.startswith("/whats-new/activegate/"):
                        full_url = f"https://docs.dynatrace.com/managed{href}"
                    else:
                        full_url = f"https://docs.dynatrace.com{href}"
                    release_candidates.append(
                        {"url": full_url, "title": text, "href": href}
                    )

            # Fallback for client-rendered Next.js pages where links are embedded in escaped JSON payloads
            if not release_candidates:
                raw_text = response.text
                plain_pattern = re.compile(
                    r'"href"\s*:\s*"(\/managed\/whats-new\/activegate\/sprint-\d+|\/whats-new\/activegate\/sprint-\d+)"'
                )
                escaped_pattern = re.compile(
                    r'\\"href\\"\s*:\s*\\"(\/managed\/whats-new\/activegate\/sprint-\d+|\/whats-new\/activegate\/sprint-\d+)\\"'
                )
                matches = plain_pattern.findall(raw_text) or escaped_pattern.findall(
                    raw_text
                )
                for href in matches:
                    if href.startswith("http"):
                        full_url = href
                    elif href.startswith("/whats-new/activegate/"):
                        full_url = f"https://docs.dynatrace.com/managed{href}"
                    else:
                        full_url = f"https://docs.dynatrace.com{href}"
                    if full_url not in [
                        candidate["url"] for candidate in release_candidates
                    ]:
                        release_candidates.append(
                            {"url": full_url, "title": "", "href": href}
                        )

            logger.info(
                f"Found {len(release_candidates)} ActiveGate sprint release links"
            )

            releases = []
            for candidate in release_candidates:
                logger.info(f"Scraping ActiveGate release page: {candidate['url']}")
                release_content = self._scrape_release_page(candidate["url"])
                release_version = self._extract_release_version(
                    candidate["url"], release_content
                )
                title = candidate["title"] or (
                    f"ActiveGate {release_version}"
                    if release_version
                    else "ActiveGate Release"
                )

                if release_content and len(release_content.strip()) > 200:
                    releases.append(
                        {
                            "title": title,
                            "version": release_version,
                            "url": candidate["url"],
                            "content": release_content,
                            "scraped_at": str(datetime.now()),
                        }
                    )
                    logger.info(
                        f"Successfully scraped release {release_version or 'unknown'} with {len(release_content)} chars"
                    )
                else:
                    logger.warning(
                        f"No substantial content found for {candidate['url']}"
                    )

            logger.info(f"Total ActiveGate releases scraped: {len(releases)}")
            return releases

        except Exception as e:
            logger.error(f"Error scraping release notes: {e}")
            return []

    def _is_activegate_release_link(self, href: str, text: str) -> bool:
        """Determine if a link points to an ActiveGate sprint release page."""
        if not href:
            return False

        href_lower = href.lower().strip()

        if (
            href_lower.startswith("#")
            or href_lower.startswith("javascript:")
            or href_lower.startswith("mailto:")
        ):
            return False
        if "#fn-" in href_lower or "#toc" in href_lower or "footnote" in href_lower:
            return False

        if (
            "/whats-new/activegate/" not in href_lower
            and "/managed/whats-new/activegate/" not in href_lower
        ):
            return False
        if "/sprint-" not in href_lower:
            return False

        return True

    def _extract_release_version(self, url: str, content_text: str = "") -> str:
        """Extract the ActiveGate release version from a page URL or page content."""
        import re

        # Prefer sprint version from URL because page content can mention historical
        # versions and cause incorrect labels (for example sprint-303 -> 1.299).
        url_match = re.search(r"sprint-(\d+)", url, re.IGNORECASE)
        if url_match:
            return f"1.{url_match.group(1)}"

        title_match = re.search(r"ActiveGate\s+(\d+\.\d+)", content_text, re.IGNORECASE)
        if title_match:
            return title_match.group(1)

        return ""

    @retry(max_retries=3, base_delay=1.5)
    def _scrape_release_page(self, url: str) -> str:
        """Scrape content from an individual release page."""
        try:
            response = self.session.get(url, timeout=(10, 30))
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "lxml")

            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer"]):
                script.extract()

            # Try multiple selectors for main content - Dynatrace docs use various structures
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
                    logger.info(f"Found content using selector: {selector}")
                    break

            # Fallback: look for divs with lots of text content
            if not content_div:
                all_divs = soup.find_all("div")
                content_div = max(
                    all_divs, key=lambda d: len(d.get_text()), default=None
                )
                if content_div and len(content_div.get_text()) < 500:
                    content_div = None  # Too short, probably not main content

            if not content_div:
                # Last resort: use body
                content_div = soup.find("body")
                logger.warning(f"Using body content for {url}")

            if content_div:
                # Get text and clean it up
                text = content_div.get_text(separator="\n", strip=True)

                # Remove excessive whitespace and short lines
                lines = [
                    line.strip()
                    for line in text.split("\n")
                    if line.strip() and len(line.strip()) > 10
                ]

                # Look for sections that mention compatibility, versions, etc.
                relevant_lines = []
                for line in lines:
                    line_lower = line.lower()
                    if any(
                        keyword in line_lower
                        for keyword in [
                            "activegate",
                            "version",
                            "compatible",
                            "requires",
                            "support",
                            "managed",
                            "cluster",
                            "extension",
                            "os",
                            "linux",
                            "windows",
                        ]
                    ):
                        relevant_lines.append(line)

                # If we found relevant lines, use them; otherwise use all lines
                final_lines = (
                    relevant_lines if relevant_lines else lines[:50]
                )  # Limit if no relevant content

                result = "\n".join(final_lines)
                logger.info(f"Extracted {len(result)} characters from {url}")
                return result

            logger.warning(f"No content found for {url}")
            return ""

        except Exception as e:
            logger.error(f"Error scraping release page {url}: {e}")
            return ""


if __name__ == "__main__":
    scraper = ReleaseNotesScraper()
    releases = scraper.scrape_release_notes()

    # Save to file for testing
    import json

    with open("scraped_releases.json", "w") as f:
        json.dump(releases, f, indent=2)

    print(f"Scraped {len(releases)} releases")
