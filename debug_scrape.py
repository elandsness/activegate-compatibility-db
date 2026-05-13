from src.ingestion.scraper import ReleaseNotesScraper

scraper = ReleaseNotesScraper()
url = 'https://docs.dynatrace.com/managed/whats-new/activegate/sprint-337'
content = scraper._scrape_release_page(url)
print('content len', len(content))
print(content[:1200])
