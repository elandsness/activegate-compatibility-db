import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HubExtensionsScraper:
    def __init__(self, base_url: str = 'https://www.dynatrace.com/hub/?filter=all&managed=true'):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def scrape_extensions(self) -> List[Dict]:
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            extensions = []
            # Find extension cards or links
            # Placeholder: look for links to extension pages
            ext_links = soup.find_all('a', href=lambda x: x and '/hub/detail/' in x)
            
            for link in ext_links[:10]:  # Limit for testing
                ext_url = link['href'] if link['href'].startswith('http') else f'https://www.dynatrace.com{link[\"href\"]}'
                name = link.get_text().strip()
                
                # Scrape extension page for compatibility and release notes
                ext_data = self._scrape_extension_page(ext_url)
                
                extensions.append({
                    'name': name,
                    'url': ext_url,
                    'data': ext_data,
                    'scraped_at': str(datetime.now())
                })
            
            logger.info(f'Scraped {len(extensions)} extensions')
            return extensions
            
        except Exception as e:
            logger.error(f'Error scraping hub extensions: {e}')
            return []

    def _scrape_extension_page(self, url: str) -> Dict:
        try:
            response = self.session.get(url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            # Extract deployment options, versions, release notes
            # Placeholder
            return {
                'deployment_options': 'ActiveGate' if 'ActiveGate' in soup.get_text() else 'Other',
                'release_notes': 'Placeholder content'
            }
            
        except Exception as e:
            logger.error(f'Error scraping extension page {url}: {e}')
            return {}

if __name__ == '__main__':
    scraper = HubExtensionsScraper()
    extensions = scraper.scrape_extensions()
    
    import json
    with open('scraped_extensions.json', 'w') as f:
        json.dump(extensions, f, indent=2)
    
    print(f'Scraped {len(extensions)} extensions')
