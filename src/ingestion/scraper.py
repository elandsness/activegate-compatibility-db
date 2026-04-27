import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ReleaseNotesScraper:
    def __init__(self, base_url: str = "https://docs.dynatrace.com/managed/whats-new"):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })

    def scrape_release_notes(self) -> List[Dict]:
        """
        Scrape the main release notes page and extract individual release entries.
        Returns a list of dicts with title, date, url, and content.
        """
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, "lxml")
            
            releases = []
            # Assuming the page has a list of releases with links
            # This is a placeholder - actual parsing depends on page structure
            release_links = soup.find_all("a", href=True)
            
            for link in release_links:
                if "release" in link.get("href", "").lower():
                    release_url = link["href"] if link["href"].startswith("http") else f"https://docs.dynatrace.com{link['href']}"
                    title = link.get_text().strip()
                    
                    # Scrape individual release page
                    release_content = self._scrape_release_page(release_url)
                    
                    releases.append({
                        "title": title,
                        "url": release_url,
                        "content": release_content,
                        "scraped_at": str(datetime.now())
                    })
            
            logger.info(f"Scraped {len(releases)} release notes")
            return releases
            
        except Exception as e:
            logger.error(f"Error scraping release notes: {e}")
            return []

    def _scrape_release_page(self, url: str) -> str:
        """
        Scrape content from an individual release page.
        """
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, "lxml")
            # Extract main content - adjust selectors based on actual page structure
            content_div = soup.find("div", class_="content") or soup.find("main")
            return content_div.get_text() if content_div else soup.get_text()
            
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
