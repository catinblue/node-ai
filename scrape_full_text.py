"""
Slice C — The Content Engine.

Scrapes full article text for every article in the digest that doesn't yet have
it, using trafilatura for robust news-body extraction. Zero LLM tokens.

Usage:
    python scrape_full_text.py                  # scrape all pending articles
    python scrape_full_text.py --limit 20       # cap this run
    python scrape_full_text.py --days 30        # widen the recency window
"""

import argparse
import sys
import time
from urllib.parse import urlparse

import trafilatura

from database import get_articles_needing_full_text, update_article_full_text


FETCH_SLEEP = 1.0          # pacing between requests — polite to news sites
MIN_BODY_LENGTH = 200      # reject extractions shorter than this (probably paywall / junk)


def process_article(article):
    """
    Download and extract the main body for one article.
    Returns (status, length_or_message).

    status ∈ {'ok', 'no_download', 'no_extract', 'too_short', 'error'}
    """
    url = article["url"]
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception as e:
        return "error", f"fetch raised: {e.__class__.__name__}: {e}"

    if not downloaded:
        return "no_download", "empty response"

    try:
        content = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            favor_precision=True,
        )
    except Exception as e:
        return "error", f"extract raised: {e.__class__.__name__}: {e}"

    if not content:
        return "no_extract", "trafilatura returned None"

    if len(content) < MIN_BODY_LENGTH:
        return "too_short", f"{len(content)} chars"

    update_article_full_text(article["id"], content)
    return "ok", len(content)


def main():
    parser = argparse.ArgumentParser(description="Scrape full article text via trafilatura.")
    parser.add_argument("--limit", type=int, default=None, help="Max articles to scrape this run.")
    parser.add_argument("--days", type=int, default=14, help="Only scrape articles published in the last N days.")
    parser.add_argument("--dry-run", action="store_true", help="List what would be scraped without fetching.")
    args = parser.parse_args()

    pending = get_articles_needing_full_text(limit=args.limit, since_days=args.days)
    if not pending:
        print("No articles need full_text. Done.")
        return 0

    print(f"Found {len(pending)} articles needing full_text (last {args.days} days).")

    if args.dry_run:
        for a in pending[:30]:
            host = urlparse(a["url"]).hostname or "?"
            print(f"  [{a['id']:>5}] {host:30} {a['title'][:60]}")
        if len(pending) > 30:
            print(f"  ... and {len(pending) - 30} more")
        return 0

    stats = {"ok": 0, "no_download": 0, "no_extract": 0, "too_short": 0, "error": 0}

    for i, a in enumerate(pending, 1):
        host = (urlparse(a["url"]).hostname or "?").replace("www.", "")
        status, detail = process_article(a)
        stats[status] += 1

        marker = {
            "ok": "+",
            "no_download": ".",
            "no_extract": "?",
            "too_short": "-",
            "error": "x",
        }[status]
        print(f"  {marker} [{i:>3}/{len(pending)}] {host:<28} {str(detail)[:50]}")

        # Pacing — don't hammer origin servers
        if i < len(pending):
            time.sleep(FETCH_SLEEP)

    print()
    print("Summary:")
    for k, v in stats.items():
        print(f"  {k:<13} {v}")
    return 0 if stats["ok"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
