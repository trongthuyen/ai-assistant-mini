import json
from shared.logger import logging
import os
import time
from typing import Optional
from models.sync_result import SyncResult
from dotenv import load_dotenv
from google import genai

load_dotenv()
logger = logging.getLogger("uploader")

# Get environment variables
STATE_FILE = os.environ.get("STATE_FILE", "assets/checklist.json")
FILE_SEARCH_STORE_NAME = os.environ.get("FILE_SEARCH_STORE_NAME", "optibot-file-search-store")

CHUNKING_CONFIG = {
    "white_space_config": {
        "max_tokens_per_chunk": 300,
        "max_overlap_tokens": 50,
    }
}

def load_state() -> dict:
    if not os.path.exists(STATE_FILE):
        return {"file_search_store_name": None, "articles": {}}
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def cache_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE) or ".", exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, sort_keys=True)

def get_or_create_file_search_store(client: genai.Client, state: dict) -> str:
    store_name = state.get("file_search_store_name") or os.environ.get("GEMINI_FILE_SEARCH_STORE_NAME")
    if store_name:
        try:
            client.file_search_stores.get(name=store_name)
            return store_name
        except Exception:
            logger.warning("Stored file_search_store_name %s no longer exists, creating a new one", store_name)

    store = client.file_search_stores.create(config={"display_name": FILE_SEARCH_STORE_NAME})
    logger.info("Created new vector store: %s", store.name)
    return store.name

def _wait_for_operation(client: genai.Client, operation, poll_seconds: float = 2.0):
    while not operation.done:
        time.sleep(poll_seconds)
        operation = client.operations.get(operation)
    return operation

def _upload_one(client: genai.Client, store_name: str, article: dict) -> str:
    display_name = article["slug"]

    file_path = article["path"]
    if file_path.endswith(".md") or file_path.endswith(".markdown"):
        mime_type = "text/markdown"
    elif file_path.endswith(".txt"):
        mime_type = "text/plain"
    elif file_path.endswith(".json"):
        mime_type = "application/json"
    else:
        mime_type = "text/plain"

    operation = client.file_search_stores.upload_to_file_search_store(
        file=article["path"],
        file_search_store_name=store_name,
        config={
            "display_name": display_name,
            "custom_metadata": [
                {"key": "article_id", "string_value": str(article["id"])},
                {"key": "article_url", "string_value": article["url"]},
            ],
            "chunking_config": CHUNKING_CONFIG,
            "mime_type": mime_type,
        },
    )
    _wait_for_operation(client, operation)

    for doc in client.file_search_stores.documents.list(parent=store_name):
        if doc.display_name == display_name:
            return doc.name

    raise RuntimeError(f"Uploaded '{display_name}' but could not locate its Document afterwards")

def _delete_one(client: genai.Client, document_name: Optional[str]) -> None:
    if not document_name:
        return
    try:
        client.file_search_stores.documents.delete(name=document_name, config={"force": True})
    except Exception as e:
        logger.warning("Could not delete document %s: %s", document_name, e)

def sync_articles(scraped_articles: list[dict]) -> SyncResult:
    client = genai.Client()
    state = load_state()
    store_name = get_or_create_file_search_store(client, state)
    state["file_search_store_name"] = store_name
    known = state.setdefault("articles", {})

    result = SyncResult()
    seen_ids = set()

    for article in scraped_articles:
        article_id = str(article["id"])
        seen_ids.add(article_id)
        prior = known.get(article_id)

        if prior is None:
            document_name = _upload_one(client, store_name, article)
            known[article_id] = {
                "hash": article["hash"],
                "document_name": document_name,
                "slug": article["slug"],
                "url": article["url"],
                "updated_at": article["updated_at"],
            }
            result.added += 1
            logger.info("ADDED   %s", article["slug"])

        elif prior["hash"] != article["hash"]:
            _delete_one(client, prior.get("document_name"))
            document_name = _upload_one(client, store_name, article)
            known[article_id] = {
                "hash": article["hash"],
                "document_name": document_name,
                "slug": article["slug"],
                "url": article["url"],
                "updated_at": article["updated_at"],
            }
            result.updated += 1
            logger.info("UPDATED %s", article["slug"])

        else:
            result.skipped += 1
            logger.debug("SKIPPED %s (unchanged)", article["slug"])

    # Articles that disappeared from the Help Center (unpublished/deleted)
    # get removed from the store too, so stale docs don't linger.
    removed_ids = set(known.keys()) - seen_ids
    for article_id in removed_ids:
        prior = known.pop(article_id)
        _delete_one(client, prior.get("document_name"))
        result.removed += 1
        logger.info("REMOVED %s (no longer published)", prior.get("slug", article_id))

    cache_state(state)

    # Report totals straight from the store so the log reflects ground
    # truth, not just this run's delta.
    result.files_embedded = sum(1 for _ in client.file_search_stores.documents.list(parent=store_name))

    return result

if __name__ == "__main__":
    import argparse
    from scraper import scrape_to_markdown

    parser = argparse.ArgumentParser()
    parser.add_argument("--min-articles", type=int, default=30)
    args = parser.parse_args()

    scraped = scrape_to_markdown(min_articles=args.min_articles)
    res = sync_articles(scraped)
    logger.info(
        f"added={res.added} updated={res.updated} skipped={res.skipped} "
        f"removed={res.removed} files_in_store={res.files_embedded}"
    )
