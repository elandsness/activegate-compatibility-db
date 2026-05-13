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
            # Look for release note links - adjust selectors based on actual page structure
            # Dynatrace release notes typically have links like "/managed/whats-new/release-notes/dynatrace-managed-1-XXX"
            release_links = soup.find_all('a', href=lambda x: x and '/whats-new/release-notes/' in x)
            
            for link in release_links[:5]:  # Limit to recent releases for testing
                href = link.get('href')
                if href.startswith('/'):
                    release_url = f"https://docs.dynatrace.com{href}"
                else:
                    release_url = href
                
                title = link.get_text().strip()
                if not title:
                    title = "Release Notes"
                
                # Scrape individual release page
                release_content = self._scrape_release_page(release_url)
                
                if release_content:  # Only include if we got content
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
            
            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.extract()
            
            # Try to find main content area - Dynatrace docs typically use specific classes
            content_selectors = [
                'div.content',
                'main',
                'article',
                'div.markdown-body',
                'div.article-content',
                '.documentation-content'
            ]
            
            content_div = None
            for selector in content_selectors:
                content_div = soup.select_one(selector)
                if content_div:
                    break
            
            if not content_div:
                # Fallback to body text
                content_div = soup.find('body')
            
            if content_div:
                # Get text and clean it up
                text = content_div.get_text(separator='\n', strip=True)
                # Remove excessive whitespace
                lines = [line.strip() for line in text.split('\n') if line.strip()]
                return '\n'.join(lines)
            
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
