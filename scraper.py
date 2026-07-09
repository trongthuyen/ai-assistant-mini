from shared.logger import logging
import os
import time
from typing import Iterator
import requests
from models.article import Article
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("scraper")

# Get environment variables
ZENDESK_BASE_URL = os.environ.get("ZENDESK_BASE_URL", "https://support.optisigns.com")
ZENDESK_LOCALE = os.environ.get("ZENDESK_LOCALE", "en-us")
ARTICLES_DIR = os.environ.get("ARTICLES_DIR", "assets/articles")

BASE_URL = f"{ZENDESK_BASE_URL}/api/v2/help_center/{ZENDESK_LOCALE}"
PAGE_SIZE = 30
REQUEST_TIMEOUT = 30

def _get(session: requests.Session, url: str, params: dict) -> dict:
    # support retrying 3 times
    for attempt in range(3):
        res = session.get(url, params=params, timeout=REQUEST_TIMEOUT)
        if res.status_code in [429, 504]:
            wait = int(res.headers.get("Retry-After", 5))
            logger.warning("Rate limited by Zendesk, sleeping %ss", wait)
            time.sleep(wait)
            continue
        res.raise_for_status()
        return res.json()
    raise RuntimeError(f"Failed to fetch {url} after retries")

def fetch_articles() -> Iterator[Article]:
    """Yield every published Help Center article, paginating through the
    Zendesk API until there are no more pages."""
    session = requests.Session()
    url = f"{BASE_URL}/articles.json"
    params = {"page[size]": PAGE_SIZE, "sort_by": "updated_at", "sort_order": "desc"}

    while url:
        data = _get(session, url, params)
        for raw in data.get("articles", []):
            if raw.get("draft"):
                continue  # skip unpublished drafts
            yield Article(
                id=raw["id"],
                title=raw["title"],
                url=raw["html_url"],
                body_html=raw.get("body") or "",
                updated_at=raw["updated_at"],
                section_id=raw.get("section_id", 0),
            )
        url = data.get("next_page")
        params = {}  # next_page URL already carries query params

def scrape_to_markdown(min_articles: int = 30) -> list[dict]:
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    results = []

    for article in fetch_articles():
        markdown = article.to_markdown()
        file_hash = article.content_hash(markdown)
        path = os.path.join(ARTICLES_DIR, f"{article.slug}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(markdown)

        results.append(
            {
                "id": article.id,
                "slug": article.slug,
                "path": path,
                "url": article.url,
                "hash": file_hash,
                "updated_at": article.updated_at,
            }
        )

    if len(results) < min_articles:
        logger.warning(
            "The requested minimum of %d, but got only scraped %d articles",
            min_articles,
            len(results),
        )
    else:
        logger.info("Scraped %d articles from %s", len(results), ZENDESK_BASE_URL)

    return results

if __name__ == "__main__":
    # fetch & convert articles to markdown
    articles = scrape_to_markdown()
    logger.info(f"Wrote {len(articles)} markdown files to {ARTICLES_DIR}/")
