import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class HubExtensionsScraper:
    def __init__(self, base_url: str = 'https://www.dynatrace.com/hub/?filter=all&type=extension&managed=true'):
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
            extension_links = soup.select('a[href*="/hub/detail/"]')
            for link in extension_links[:10]:
                href = link.get('href')
                ext_url = href if href.startswith('http') else f'https://www.dynatrace.com{href}'
                name = link.get_text().strip() or link.get('title', '').strip() or 'Unknown Extension'
                
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
            
            # Remove scripts and styles
            for script in soup(["script", "style"]):
                script.extract()
            
            # Extract deployment options, versions, release notes
            data = {
                'deployment_options': [],
                'supported_versions': [],
                'release_notes': '',
                'compatibility_info': ''
            }
            
            # Look for deployment options
            deployment_section = soup.find(string=lambda x: x and 'deployment' in x.lower())
            if deployment_section:
                parent = deployment_section.parent
                if parent:
                    deployment_text = parent.get_text()
                    if 'ActiveGate' in deployment_text:
                        data['deployment_options'].append('ActiveGate')
                    if 'OneAgent' in deployment_text:
                        data['deployment_options'].append('OneAgent')
            
            # Look for version information
            version_selectors = ['.version', '.compatibility', '[data-version]']
            for selector in version_selectors:
                version_elements = soup.select(selector)
                for elem in version_elements:
                    version_text = elem.get_text().strip()
                    if version_text and any(char.isdigit() for char in version_text):
                        data['supported_versions'].append(version_text)
            
            # Extract main content for release notes
            content_selectors = ['.content', 'main', 'article', '.extension-details']
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    text = content_elem.get_text(separator='\n', strip=True)
                    lines = [line.strip() for line in text.split('\n') if line.strip()]
                    data['release_notes'] = '\n'.join(lines[:500])  # Limit size
                    break
            
            # Look for compatibility information
            compat_keywords = ['compatible', 'requires', 'supports', 'minimum']
            for keyword in compat_keywords:
                elements = soup.find_all(string=lambda x: x and keyword in x.lower())
                for elem in elements:
                    parent = elem.parent if elem.parent else elem
                    data['compatibility_info'] += parent.get_text() + '\n'
            
            return data
            
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
