import requests
from bs4 import BeautifulSoup
import logging
from typing import List, Dict
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EndOfSupportScraper:
    def __init__(self, base_url: str = 'https://docs.dynatrace.com/managed/whats-new/technology/end-of-support-news'):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def scrape_end_of_support(self) -> List[Dict]:
        try:
            response = self.session.get(self.base_url)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'lxml')
            
            announcements = []
            # Find sections or links related to end of support
            # Placeholder: look for headings or specific content
            content_div = soup.find('div', class_='content') or soup.find('main')
            if content_div:
                # Extract text or structured data
                text = content_div.get_text()
                announcements.append({
                    'title': 'End of Support Announcements',
                    'url': self.base_url,
                    'content': text,
                    'scraped_at': str(datetime.now())
                })
            
            logger.info(f'Scraped {len(announcements)} end of support entries')
            return announcements
            
        except Exception as e:
            logger.error(f'Error scraping end of support: {e}')
            return []

if __name__ == '__main__':
    scraper = EndOfSupportScraper()
    announcements = scraper.scrape_end_of_support()
    
    import json
    with open('scraped_eos.json', 'w') as f:
        json.dump(announcements, f, indent=2)
    
    print(f'Scraped {len(announcements)} announcements')
