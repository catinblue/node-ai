"""
Scrape newsletter archives from The Neuron and AI Valley (Beehiiv).
Extracts post titles, dates, and content, then uses LLM to extract stories.
Run once to backfill historical data.
"""

import re
import sys
import time
from datetime import datetime, timezone

import requests
from dateutil import parser as dateparser

from database import insert_article
from fetcher import extract_stories_from_newsletter

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

SITES = [
    {"name": "The Neuron", "base": "https://www.theneurondaily.com"},
    {"name": "AI Valley", "base": "https://www.theaivalley.com"},
]


def get_post_slugs(base_url, max_pages=20):
    """Get all post slugs from paginated archive pages back to Jan 2026."""
    all_slugs = []
    seen = set()
    for page in range(1, max_pages + 1):
        url = f"{base_url}/archive" if page == 1 else f"{base_url}/archive?page={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception:
            break

        slugs = re.findall(r'/p/([a-z0-9][\w-]+)', resp.text)
        new_slugs = [s for s in slugs if s not in seen]
        for s in new_slugs:
            seen.add(s)
            all_slugs.append(s)

        if not new_slugs:
            break

        # Check if we've gone past Jan 2026
        dates = re.findall(r'((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{1,2},?\s+\d{4})', resp.text)
        if dates:
            last_date = dates[-1]
            if "2025" in last_date:
                print(f"    Reached 2025 at page {page}, stopping")
                break

        print(f"    Page {page}: {len(new_slugs)} new posts")
        time.sleep(1)

    return all_slugs


def scrape_post(base_url, slug):
    """Scrape a single post page and return title, date, text."""
    url = f"{base_url}/p/{slug}"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"    [FAIL] {slug}: {e}")
        return None

    html = resp.text

    # Extract title
    title_match = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.DOTALL)
    title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else slug

    # Extract date
    date_match = re.search(r'<time[^>]*datetime="([^"]+)"', html)
    if date_match:
        date_str = date_match.group(1)
    else:
        # Try og:article:published_time
        og_match = re.search(r'property="article:published_time"\s+content="([^"]+)"', html)
        if og_match:
            date_str = og_match.group(1)
        else:
            # Try finding a date pattern in the text
            date_pattern = re.search(r'((?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})', html)
            date_str = date_pattern.group(1) if date_pattern else ""

    try:
        pub_date = dateparser.parse(date_str).strftime("%Y-%m-%d %H:%M:%S") if date_str else ""
    except (ValueError, TypeError):
        pub_date = ""

    # Skip if before 2026
    if pub_date and pub_date < "2026-01-01":
        return None

    # Extract body text (strip HTML)
    # Find the main content area
    body_match = re.search(r'id="content-blocks"(.*?)(?:class="w\b|class="footer|$)', html, re.DOTALL)
    if not body_match:
        body_match = re.search(r'<article[^>]*>(.*?)</article>', html, re.DOTALL)
    if not body_match:
        # Fallback: get everything between first <p> and footer
        body_match = re.search(r'(<p\b.*?)(?:Update your email|Unsubscribe|Terms of Service)', html, re.DOTALL)

    if body_match:
        body_html = body_match.group(1)
    else:
        body_html = html

    # Strip HTML tags
    text = re.sub(r'<style[^>]*>.*?</style>', '', body_html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()

    return {"title": title, "date": pub_date, "text": text[:6000], "url": url, "slug": slug}


def is_url_in_db(url):
    """Check if a URL (or base URL) already exists in the DB."""
    from database import get_connection
    conn = get_connection()
    row = conn.execute("SELECT COUNT(*) FROM articles WHERE url LIKE ?", (url + "%",)).fetchone()
    conn.close()
    return row[0] > 0


def process_post(post, source_name, use_llm=True):
    """Extract stories from a post and insert into DB.

    Returns (count_inserted, rate_limited_flag). When rate_limited_flag is True
    the caller should stop using the LLM for subsequent posts in this run.
    """
    if not post or not post["text"] or len(post["text"]) < 100:
        return 0, False

    # Skip if already scraped
    if is_url_in_db(post["url"]):
        return 0, False

    if not use_llm:
        # Store as single article without LLM
        inserted = insert_article(
            title=post["title"],
            url=post["url"],
            source_name=source_name,
            published_at=post["date"],
            content_snippet=post["text"][:500],
            language="en",
        )
        return (1 if inserted else 0), False

    # Try LLM extraction
    try:
        stories = extract_stories_from_newsletter(post["text"], source_name)
    except Exception as e:
        msg = str(e).lower()
        if "429" in msg or "rate_limit" in msg or "rate-limit" in msg:
            print(f"    [RATE LIMIT] Switching to no-LLM mode for remaining posts")
            count, _ = process_post(post, source_name, use_llm=False)
            return count, True   # signal: caller must set rate_limited=True
        print(f"    [LLM FAIL] {post['slug']}: {e}")
        count, _ = process_post(post, source_name, use_llm=False)
        return count, False

    count = 0
    for i, story in enumerate(stories):
        s_title = story.get("title", "").strip()
        s_summary = story.get("summary", "").strip()
        if not s_title or len(s_title) < 5:
            continue
        inserted = insert_article(
            title=s_title,
            url=f"{post['url']}#story-{i}",
            source_name=source_name,
            published_at=post["date"],
            content_snippet=s_summary,
            language="en",
        )
        if inserted:
            count += 1
    return count, False


def main():
    use_llm = "--no-llm" not in sys.argv
    total = 0
    rate_limited = False

    for site in SITES:
        name = site["name"]
        base = site["base"]
        print(f"\n=== Scraping {name} archive ({base}) ===")

        slugs = get_post_slugs(base)
        print(f"  Found {len(slugs)} posts total")

        for i, slug in enumerate(slugs):
            post = scrape_post(base, slug)
            if not post:
                continue

            # Skip if already in DB
            if is_url_in_db(post["url"]):
                continue

            print(f"  [{i+1}/{len(slugs)}] {slug} ({post['date'][:10]})...")

            count, hit_rate_limit = process_post(post, name, use_llm=use_llm and not rate_limited)
            if hit_rate_limit and not rate_limited:
                rate_limited = True
                print("  [RATE LIMIT] All subsequent posts in this run will skip LLM.")
            total += count
            print(f"    -> {count} stories")

            if use_llm and not rate_limited:
                time.sleep(2)

    print(f"\n=== Done: {total} total stories added to DB ===")


if __name__ == "__main__":
    main()
