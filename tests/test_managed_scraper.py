from src.ingestion.managed_scraper import ManagedReleaseNotesScraper


def test_extract_release_version_from_url():
    scraper = ManagedReleaseNotesScraper()

    version = scraper._extract_release_version(
        "https://docs.dynatrace.com/managed/whats-new/managed/sprint-342", ""
    )

    assert version == "1.342"


def test_extract_sprint_urls_deduplicates_and_sorts():
    scraper = ManagedReleaseNotesScraper()
    html_blob = """
    <a href=\"/managed/whats-new/managed/sprint-340\">340</a>
    <a href=\"/managed/whats-new/managed/sprint-342\">342</a>
    <a href=\"/managed/whats-new/managed/sprint-340\">340b</a>
    """

    urls = scraper._extract_sprint_urls(html_blob)

    assert urls[0].endswith("sprint-342")
    assert urls[1].endswith("sprint-340")
    assert len(urls) == 2
