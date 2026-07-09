from shared.logger import logging
import os
import sys
import time
from scraper import scrape_to_markdown
from uploader import sync_articles
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("main")

def run() -> int:
    started = time.time()

    if not os.environ.get("GEMINI_API_KEY"):
        logger.error("GEMINI_API_KEY is not configured.")
        return 1

    try:
        logger.info("START scraping...")
        articles = scrape_to_markdown(min_articles=30)
        logger.info("Scraped %d articles", len(articles))

        logger.info("Syncing delta to vector store...")
        result = sync_articles(articles)

        elapsed = round(time.time() - started, 1)
        logger.info(
            "DONE in %ss | added=%d updated=%d skipped=%d removed=%d | "
            "files_in_store=%d",
            elapsed,
            result.added,
            result.updated,
            result.skipped,
            result.removed,
            result.files_embedded,
        )
        return 0

    except Exception:
        logger.exception("Daily job failed")
        return 1

if __name__ == "__main__":
    sys.exit(run())
