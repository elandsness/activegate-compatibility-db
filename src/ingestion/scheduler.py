import json
import logging
import os

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from src.ingestion.eos_scraper import EndOfSupportScraper
from src.ingestion.hub_scraper import HubExtensionsScraper
from src.ingestion.scraper import ReleaseNotesScraper

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_weekly_ingestion():
    logger.info("Starting weekly data ingestion")

    # Scrape release notes
    rn_scraper = ReleaseNotesScraper()
    releases = rn_scraper.scrape_release_notes()
    with open("data/releases.json", "w") as f:
        json.dump(releases, f, indent=2)

    # Scrape end of support
    eos_scraper = EndOfSupportScraper()
    eos = eos_scraper.scrape_end_of_support()
    with open("data/eos.json", "w") as f:
        json.dump(eos, f, indent=2)

    # Scrape hub extensions
    hub_scraper = HubExtensionsScraper()
    extensions = hub_scraper.scrape_extensions()
    with open("data/extensions.json", "w") as f:
        json.dump(extensions, f, indent=2)

    logger.info("Weekly ingestion completed")


if __name__ == "__main__":
    # Create data directory
    os.makedirs("data", exist_ok=True)

    scheduler = BlockingScheduler()
    # Run every Monday at 9 AM
    scheduler.add_job(run_weekly_ingestion, CronTrigger(day_of_week="mon", hour=9))

    logger.info("Scheduler started. Waiting for weekly runs...")
    scheduler.start()
