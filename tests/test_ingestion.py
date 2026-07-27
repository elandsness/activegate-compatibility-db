#!/usr/bin/env python3
"""
Test script for ingestion components.
Tests that scrapers can be imported and initialized.
"""

from src.ingestion.eos_scraper import EndOfSupportScraper
from src.ingestion.hub_scraper import HubExtensionsScraper
from src.ingestion.managed_scraper import ManagedReleaseNotesScraper
from src.ingestion.scheduler import run_weekly_ingestion
from src.ingestion.scraper import ReleaseNotesScraper


def test_release_notes_scraper():
    """Test ReleaseNotesScraper can be initialized."""
    print("\n=== Testing ReleaseNotesScraper ===")

    scraper = ReleaseNotesScraper()
    assert scraper is not None
    assert scraper.base_url is not None

    print("✓ ReleaseNotesScraper initialized")


def test_eos_scraper():
    """Test EndOfSupportScraper can be initialized."""
    print("\n=== Testing EndOfSupportScraper ===")

    scraper = EndOfSupportScraper()
    assert scraper is not None

    print("✓ EndOfSupportScraper initialized")


def test_hub_scraper():
    """Test HubExtensionsScraper can be initialized."""
    print("\n=== Testing HubExtensionsScraper ===")

    scraper = HubExtensionsScraper()
    assert scraper is not None

    print("✓ HubExtensionsScraper initialized")


def test_managed_scraper():
    """Test ManagedReleaseNotesScraper can be initialized."""
    print("\n=== Testing ManagedReleaseNotesScraper ===")

    scraper = ManagedReleaseNotesScraper()
    assert scraper is not None

    print("✓ ManagedReleaseNotesScraper initialized")


def test_scheduler():
    """Test scheduler function exists."""
    print("\n=== Testing Scheduler ===")

    assert callable(run_weekly_ingestion)

    print("✓ Scheduler function available")


def test_integration():
    """Integration test for ingestion pipeline."""
    print("\n=== Testing Ingestion Integration ===")

    # Test full pipeline
    scraper = ReleaseNotesScraper()
    eos_scraper = EndOfSupportScraper()
    hub_scraper = HubExtensionsScraper()
    managed_scraper = ManagedReleaseNotesScraper()

    # Verify all scrapers can be initialized
    assert scraper is not None
    assert eos_scraper is not None
    assert hub_scraper is not None
    assert managed_scraper is not None

    # Test scheduler function exists
    assert callable(run_weekly_ingestion)

    print("✓ Ingestion integration passed")


if __name__ == "__main__":
    print("=" * 60)
    print("Running Ingestion Component Tests")
    print("=" * 60)

    tests = [
        test_release_notes_scraper,
        test_eos_scraper,
        test_hub_scraper,
        test_managed_scraper,
        test_scheduler,
        test_integration,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            failed += 1

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
