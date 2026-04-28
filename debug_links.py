import requests
from bs4 import BeautifulSoup

response = requests.get("https://docs.dynatrace.com/managed/whats-new", headers={"User-Agent": "Mozilla/5.0"})
soup = BeautifulSoup(response.content, "lxml")
links = soup.find_all("a", href=True)
sprint_links = [link for link in links if "sprint" in link.get("href", "")]
print(f"Found {len(sprint_links)} sprint links")
for link in sprint_links[:5]:
    print(f"Text: {link.get_text().strip()[:50]}... Href: {link['href']}")
