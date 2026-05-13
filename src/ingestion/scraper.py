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
            # Find ALL links and filter for release note pages
            all_links = soup.find_all('a', href=True)
            
            release_candidates = []
            for link in all_links:
                href = link.get('href')
                text = link.get_text().strip()
                
                # Check if this looks like a release note link
                if self._is_release_note_link(href, text):
                    full_url = href if href.startswith('http') else f"https://docs.dynatrace.com{href}"
                    release_candidates.append({
                        'url': full_url,
                        'title': text or href.split('/')[-1].replace('-', ' ').title(),
                        'link_text': text,
                        'href': href
                    })
            
            logger.info(f"Found {len(release_candidates)} potential release note links")
            
            # Scrape the first 5 release pages
            for candidate in release_candidates[:5]:
                logger.info(f"Scraping: {candidate['title']} -> {candidate['url']}")
                
                release_content = self._scrape_release_page(candidate['url'])
                
                if release_content and len(release_content.strip()) > 200:  # Substantial content
                    releases.append({
                        "title": candidate['title'],
                        "url": candidate['url'],
                        "content": release_content,
                        "scraped_at": str(datetime.now())
                    })
                    logger.info(f"Successfully scraped release with {len(release_content)} chars")
                else:
                    logger.warning(f"No substantial content found for {candidate['url']}")
            
            logger.info(f"Total releases scraped: {len(releases)}")
            return releases
            
        except Exception as e:
            logger.error(f"Error scraping release notes: {e}")
            return []

    def _is_release_note_link(self, href: str, text: str) -> bool:
        """Determine if a link points to a release notes page."""
        if not href:
            return False
            
        href_lower = href.lower()
        text_lower = (text or '').lower()
        
        # Must contain some version-like pattern
        import re
        version_pattern = r'\b\d+\.\d+'  # Like 1.234
        
        # Check various indicators
        indicators = [
            'release-notes' in href_lower,
            'whats-new' in href_lower,
            'dynatrace-managed' in href_lower,
            re.search(version_pattern, href_lower),
            re.search(version_pattern, text_lower),
            'version' in text_lower,
            any(char.isdigit() for char in href.split('/')[-1])  # Numbers in URL segment
        ]
        
        return any(indicators)

    def _scrape_release_page(self, url: str) -> str:
        """
        Scrape content from an individual release page.
        """
        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, "lxml")
            
            # Remove script and style elements
            for script in soup(["script", "style", "nav", "header", "footer"]):
                script.extract()
            
            # Try multiple selectors for main content - Dynatrace docs use various structures
            content_selectors = [
                'div.content',
                'main',
                'article',
                'div.markdown-body',
                'div.article-content',
                '.documentation-content',
                'div.main-content',
                'div.content-wrapper',
                '[role="main"]',
                '.doc-content'
            ]
            
            content_div = None
            for selector in content_selectors:
                content_div = soup.select_one(selector)
                if content_div:
                    logger.info(f"Found content using selector: {selector}")
                    break
            
            # Fallback: look for divs with lots of text content
            if not content_div:
                all_divs = soup.find_all('div')
                content_div = max(all_divs, key=lambda d: len(d.get_text()), default=None)
                if content_div and len(content_div.get_text()) < 500:
                    content_div = None  # Too short, probably not main content
            
            if not content_div:
                # Last resort: use body
                content_div = soup.find('body')
                logger.warning(f"Using body content for {url}")
            
            if content_div:
                # Get text and clean it up
                text = content_div.get_text(separator='\n', strip=True)
                
                # Remove excessive whitespace and short lines
                lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 10]
                
                # Look for sections that mention compatibility, versions, etc.
                relevant_lines = []
                for line in lines:
                    line_lower = line.lower()
                    if any(keyword in line_lower for keyword in [
                        'activegate', 'version', 'compatible', 'requires', 'support', 
                        'managed', 'cluster', 'extension', 'os', 'linux', 'windows'
                    ]):
                        relevant_lines.append(line)
                
                # If we found relevant lines, use them; otherwise use all lines
                final_lines = relevant_lines if relevant_lines else lines[:50]  # Limit if no relevant content
                
                result = '\n'.join(final_lines)
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
