# OptiBot Mini

A support-doc assistant that scrapes OptiSigns' Zendesk Help Center, converts articles to Markdown, indexes them in a **Google Gemini File Search Store**, and answers questions with citations via a Gemini model ("OptiBot"). A daily job re-scrapes and uploads only changed articles (delta sync).

## Architecture

```
scraper.py                       Zendesk Help Center API -> clean Markdown files
models/article.py                Article dataclass (HTML->MD, hashing, slug)
uploader.py                      Diffs against assets/checklist.json, syncs delta to Gemini File Search Store
optibot_mini_assistant_setup.py  System prompt, sanity-check Q&A against the store
main.py                          Orchestrates scrape -> delta upload -> logs (Docker entrypoint)
shared/logger.py                        Shared logging config
models/sync_result.py            SyncResult dataclass (added/updated/skipped/removed)
assets/checklist.json            Per-article content hash + document name (delta-detection cache)
assets/articles/                 Scraped Markdown files (gitignored)
images/                          Screenshots (sanity check Q&A, articles & checklist)
Dockerfile                       Containerizes main.py
.github/workflows/daily.yml      Daily scheduled run (GitHub Actions) + manual trigger
```

## Setup

1. `git clone` this repo and `cd` into it.
2. `cp .env.sample .env` and fill in `GEMINI_API_KEY`.
3. `pip install -r requirements.txt` (Python 3.11+).

## Run locally

```bash
# Scrape + upload delta, in one shot
python main.py

# Run a sanity-check Q&A against the store
python optibot_mini_assistant_setup.py --sanity-check
```

Subsequent runs only upload articles whose content hash changed since the last run.

## Run via Docker

```bash
docker build -t optibot-sync .
docker run --rm -e GEMINI_API_KEY=sk-... optibot-sync
```

Exits `0` on success, `1` on failure.

## Delta detection

Each article is hashed (SHA-256 of its Markdown body) and stored in `assets/checklist.json` keyed by Zendesk article id, along with the resulting Gemini Document name. On each run:

| Condition                                      | Action                                                    |
| ---------------------------------------------- | --------------------------------------------------------- |
| Article id not seen before                     | Upload, count as **added**                                |
| Article id seen, hash changed                  | Delete old document, upload new one, count as **updated** |
| Article id seen, hash unchanged                | Skip, count as **skipped**                                |
| Article id seen but missing from latest scrape | Delete from store, count as **removed**                   |

The job logs a one-line summary each run:

```
DONE in 42.3s | added=3 updated=1 skipped=28 removed=0 | files_in_store=32
```

## Chunking strategy

Files are uploaded with Gemini's whitespace-based chunking: `max_tokens_per_chunk=300`, `max_overlap_tokens=50`. Support articles are short, so most fit in a single chunk while keeping retrieval precise.

## Daily job logs

The job runs daily at 06:00 UTC via GitHub Actions. The workflow caches `assets/checklist.json` between runs so delta detection works across executions.

## Assistant system prompt

```
You are OptiBot, the customer-support bot for OptiSigns.com.
• Tone: helpful, factual, concise.
• Only answer using the uploaded docs.
• Max 5 bullet points; else link to the doc.
• Cite up to 3 "Article URL:" lines per reply.
```

## Notes

- `assets/checklist.json` is not committed if it contains environment-specific store names; the GitHub Actions workflow caches it via `actions/cache`.
- Zendesk pagination is followed automatically via `next_page`; no page-count assumptions.
- Unpublished/removed articles are also removed from the File Search Store.
- Uses `gemini-2.5-flash` by default (configurable via `GEMINI_MODEL`).
