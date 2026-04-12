"""
News Fetcher — collects articles from RSS feeds and API sources.
"""

import time
import feedparser
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser

from sources import RSS_SOURCES, API_SOURCES
from database import insert_article


# Some feeds block default user-agents
HEADERS = {
    "User-Agent": "AI-News-Aggregator/1.0 (personal project)"
}

# Request timeout in seconds
FETCH_TIMEOUT = 15

# Ignore articles older than this many days
MAX_ARTICLE_AGE_DAYS = 7


def parse_published_date(entry):
    """Extract and normalize the published date from a feed entry."""
    for field in ("published", "updated", "created"):
        raw = entry.get(field)
        if raw:
            try:
                return dateparser.parse(raw).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, TypeError):
                continue
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def extract_snippet(entry, max_len=500):
    """Get a text snippet from the entry summary or content."""
    import re
    text = entry.get("summary", "")
    if not text and "content" in entry:
        text = entry["content"][0].get("value", "")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\s+", " ", text)
    return text[:max_len].strip()


# Skip newsletter entries that are not actual news (welcome, confirm, etc.)
SKIP_TITLES = [
    "welcome", "confirm", "verify", "waitlist", "let's confirm",
    "signup", "subscribe", "unsubscribe",
]


def is_newsletter_noise(title):
    """Check if a newsletter entry is a welcome/confirmation email, not real content."""
    lower = title.lower()
    # Don't filter "Welcome to Every" type articles that are real content
    if "every" in lower and ("welcome to" in lower or "learn the new" in lower):
        return False
    return any(skip in lower for skip in SKIP_TITLES)


def get_newsletter_text(entry):
    """Extract plain text from a newsletter HTML entry."""
    import re
    html = ""
    if "content" in entry:
        html = entry["content"][0].get("value", "")
    elif entry.get("summary"):
        html = entry["summary"]

    # Unescape HTML entities
    for old, new in [("&lt;", "<"), ("&gt;", ">"), ("&amp;", "&"),
                     ("&quot;", '"'), ("&apos;", "'"), ("&#x27;", "'"),
                     ("&#39;", "'"), ("&#160;", " "), ("&#8204;", "")]:
        html = html.replace(old, new)

    # Strip all HTML tags
    text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_stories_from_newsletter(text, source_label):
    """Use LLM to extract individual news stories from newsletter text."""
    import json
    import os
    from dotenv import load_dotenv

    load_dotenv()
    api_key = os.getenv("MSITRAL_API_KEY")

    # Truncate to fit in context window
    text = text[:6000]

    prompt = f"""Extract every individual NEWS STORY from this newsletter email.

Newsletter text:
{text}

Return ONLY valid JSON — an array:
[
  {{"title": "Specific headline with company name and what happened", "summary": "1-2 sentence summary of what happened and why it matters"}}
]

Rules:
- Extract ALL news stories mentioned, even briefly (e.g. "signals" or "around the horn" sections)
- title MUST be specific: "Anthropic blocks OpenClaw on free Claude plans" NOT just "Anthropic"
- title MUST include the company/product name AND what happened
- summary should explain why this matters
- Skip: ads, sponsors, welcome text, feedback buttons, unsubscribe links, author bios
- If the newsletter is a deep-dive on ONE topic, return 1 item with a detailed title
- Return ONLY the JSON array, no markdown fences"""

    try:
        resp = requests.post("https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": "mistral-small-latest", "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1, "max_tokens": 2000},
            timeout=60,
        )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]
        stories = json.loads(raw)
        return stories
    except Exception as e:
        print(f"    [WARN] LLM extraction failed for {source_label}: {e}")
        return []


def fetch_one_source(source):
    """Fetch articles from a single RSS source. Returns count of new articles."""
    name = source["name"]
    url = source["url"]
    language = source.get("language", "en")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [FAIL] {name}: network error - {e}")
        return 0

    feed = feedparser.parse(resp.text)
    if feed.bozo and not feed.entries:
        print(f"  [FAIL] {name}: parse error - {feed.bozo_exception}")
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_ARTICLE_AGE_DAYS)
    max_entries = source.get("max_entries")
    entries = feed.entries[:max_entries] if max_entries else feed.entries
    new_count = 0
    skipped_old = 0
    for entry in entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            continue

        # Skip welcome/confirmation emails from newsletter feeds
        if is_newsletter_noise(title):
            continue

        published = parse_published_date(entry)

        # Skip articles older than the cutoff
        try:
            pub_dt = dateparser.parse(published)
            if pub_dt.tzinfo is None:
                pub_dt = pub_dt.replace(tzinfo=timezone.utc)
            if pub_dt < cutoff:
                skipped_old += 1
                continue
        except (ValueError, TypeError):
            pass  # If we can't parse, keep the article

        # Newsletter feeds: use LLM to extract individual stories
        is_newsletter = "kill-the-newsletter" in url
        if is_newsletter:
            # Detect which newsletter sent this
            author_email = ""
            if hasattr(entry, "get"):
                ad = entry.get("author_detail", {})
                if isinstance(ad, dict):
                    author_email = ad.get("email", "")
                author_str = entry.get("author", "")
                if not author_email:
                    author_email = author_str

            a_lower = author_email.lower()
            t_lower = title.lower()
            if "alphasignal" in a_lower:
                source_label = "AlphaSignal"
            elif "31209141" in a_lower or "neuron" in a_lower:
                source_label = "The Neuron"
            elif "30569924" in a_lower or "aivalley" in a_lower or "ai valley" in t_lower:
                source_label = "AI Valley"
            elif "33609922" in a_lower or "every" in t_lower or "bbb082" in a_lower:
                source_label = "Every"
            elif "aitinkerers" in a_lower or "tinkerers" in t_lower:
                source_label = "AI Tinkerers"
            else:
                source_label = "AI Valley"

            text = get_newsletter_text(entry)
            if len(text) > 200:  # Skip if too short (probably noise)
                print(f"    Extracting stories from {source_label}...")
                stories = extract_stories_from_newsletter(text, source_label)
                for si, story in enumerate(stories):
                    s_title = story.get("title", "").strip()
                    s_summary = story.get("summary", "").strip()
                    if not s_title or len(s_title) < 5:
                        continue
                    # Each story needs a unique URL (DB has UNIQUE on url)
                    unique_url = f"{link}#story-{si}"
                    inserted = insert_article(
                        title=s_title,
                        url=unique_url,
                        source_name=source_label,
                        published_at=published,
                        content_snippet=s_summary,
                        language=language,
                    )
                    if inserted:
                        new_count += 1
            continue  # Don't store the raw newsletter email

        snippet = extract_snippet(entry)

        inserted = insert_article(
            title=title,
            url=link,
            source_name=name,
            published_at=published,
            content_snippet=snippet,
            language=language,
        )
        if inserted:
            new_count += 1

    old_msg = f", {skipped_old} skipped (old)" if skipped_old else ""
    print(f"  [OK] {name}: {new_count} new / {len(feed.entries)} total{old_msg}")
    return new_count


def fetch_all_rss():
    """Fetch all RSS sources in parallel. Returns total new articles count."""
    print(f"Fetching {len(RSS_SOURCES)} RSS sources...")
    total = 0
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_one_source, src): src for src in RSS_SOURCES}
        for future in as_completed(futures):
            total += future.result()
    print(f"RSS done - {total} new articles.")
    return total


# ── API Fetchers ──────────────────────────────────────────────


def fetch_hn(source):
    """Fetch AI stories from Hacker News via Algolia API."""
    name = source["name"]
    cutoff_ts = int(time.time()) - MAX_ARTICLE_AGE_DAYS * 86400
    # Use /search (by relevance) with date filter — /search_by_date can return empty
    params = {**source["params"], "numericFilters": f"created_at_i>{cutoff_ts}"}

    try:
        resp = requests.get(source["url"], params=params,
                            headers=HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [FAIL] {name}: {e}")
        return 0

    hits = resp.json().get("hits", [])
    new_count = 0
    for hit in hits:
        title = hit.get("title", "").strip()
        url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit['objectID']}"
        if not title:
            continue

        published = hit.get("created_at", "")
        try:
            pub_str = dateparser.parse(published).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pub_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        points = hit.get("points", 0)
        num_comments = hit.get("num_comments", 0)
        snippet = f"[{points} points, {num_comments} comments on HN]"

        inserted = insert_article(
            title=title,
            url=url,
            source_name=name,
            published_at=pub_str,
            content_snippet=snippet,
            language=source.get("language", "en"),
        )
        if inserted:
            new_count += 1

    print(f"  [OK] {name}: {new_count} new / {len(hits)} total")
    return new_count


def fetch_reddit(source):
    """Fetch top AI posts from a subreddit via JSON API."""
    name = source["name"]
    # Reddit requires a descriptive User-Agent, blocks generic ones
    headers = {"User-Agent": "AI-News-Digest/1.0 (by /u/ainewsdigest)"}
    params = source.get("params", {})

    try:
        resp = requests.get(source["url"], params=params,
                            headers=headers, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [FAIL] {name}: {e}")
        return 0

    posts = resp.json().get("data", {}).get("children", [])
    new_count = 0
    for post in posts:
        data = post.get("data", {})
        title = (data.get("title") or "").strip()
        url = data.get("url") or f"https://reddit.com{data.get('permalink', '')}"
        if not title:
            continue

        # Skip self-posts with no external link (discussion threads)
        is_self = data.get("is_self", False)
        permalink = f"https://reddit.com{data.get('permalink', '')}"
        if is_self:
            url = permalink

        created_utc = data.get("created_utc", 0)
        pub_str = datetime.fromtimestamp(created_utc, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        # Skip old posts
        cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_ARTICLE_AGE_DAYS)
        if datetime.fromtimestamp(created_utc, tz=timezone.utc) < cutoff:
            continue

        score = data.get("score", 0)
        num_comments = data.get("num_comments", 0)
        snippet = f"[{score} upvotes, {num_comments} comments on {name}]"

        inserted = insert_article(
            title=title,
            url=url,
            source_name=name,
            published_at=pub_str,
            content_snippet=snippet,
            language=source.get("language", "en"),
        )
        if inserted:
            new_count += 1

    print(f"  [OK] {name}: {new_count} new / {len(posts)} total")
    return new_count


def fetch_hf_papers(source):
    """Fetch trending papers from HuggingFace Daily Papers API."""
    name = source["name"]

    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"  [FAIL] {name}: {e}")
        return 0

    papers = resp.json()
    if not isinstance(papers, list):
        print(f"  [FAIL] {name}: unexpected response format")
        return 0

    # API returns nested structure: each item has "paper" and top-level metadata
    # Flatten and sort by upvotes, take top 15
    flattened = []
    for item in papers:
        inner = item.get("paper", item)
        inner["_upvotes"] = item.get("upvotes", inner.get("upvotes", 0))
        inner["_numComments"] = item.get("numComments", inner.get("numComments", 0))
        flattened.append(inner)

    flattened.sort(key=lambda p: p.get("_upvotes", 0), reverse=True)
    flattened = flattened[:15]

    new_count = 0
    for paper in flattened:
        title = (paper.get("title") or "").strip()
        paper_id = paper.get("id", "")
        if not title or not paper_id:
            continue

        url = f"https://huggingface.co/papers/{paper_id}"
        upvotes = paper.get("_upvotes", 0)
        num_comments = paper.get("_numComments", 0)

        published = paper.get("publishedAt", "")
        try:
            pub_str = dateparser.parse(published).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            pub_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        snippet = (paper.get("summary") or "")[:500]
        snippet = f"[{upvotes} upvotes, {num_comments} comments on HF] {snippet[:400]}"

        inserted = insert_article(
            title=title,
            url=url,
            source_name=name,
            published_at=pub_str,
            content_snippet=snippet,
            language=source.get("language", "en"),
        )
        if inserted:
            new_count += 1

    print(f"  [OK] {name}: {new_count} new / {len(papers)} total")
    return new_count


API_FETCHERS = {
    "hn": fetch_hn,
    "reddit": fetch_reddit,
    "hf_papers": fetch_hf_papers,
}


def fetch_all_api():
    """Fetch all API sources. Returns total new articles count."""
    print(f"Fetching {len(API_SOURCES)} API sources...")
    total = 0
    for source in API_SOURCES:
        fetcher = API_FETCHERS.get(source["type"])
        if fetcher:
            total += fetcher(source)
        else:
            print(f"  [SKIP] {source['name']}: unknown type '{source['type']}'")
    print(f"API done - {total} new articles.")
    return total


def fetch_all():
    """Fetch from all sources (RSS + API)."""
    rss = fetch_all_rss()
    api = fetch_all_api()
    total = rss + api
    print(f"\nTotal: {total} new articles added.")
    return total


if __name__ == "__main__":
    fetch_all()
