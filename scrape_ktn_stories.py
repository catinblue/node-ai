"""
Slice B — KTN HTML Section Extraction.

For each unique Kill-the-Newsletter entry that backs one or more articles in the
DB, fetch the HTML once, parse it into paragraph blocks, then keyword-match each
DB article's title to the best-fitting block and store it as full_text.

This recovers the original newsletter prose (human-written) for featured stories,
which is strictly richer than the LLM-reduced content_snippet.

Usage:
    python scrape_ktn_stories.py                # scrape all pending KTN newsletters
    python scrape_ktn_stories.py --dry-run      # show mapping without writing
    python scrape_ktn_stories.py --limit 3      # only process first N newsletters
"""

import argparse
import re
import sys
import time
from collections import defaultdict
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from database import get_connection, update_article_full_text


FETCH_SLEEP = 1.0
USER_AGENT = "AI-News-Aggregator/1.0 (personal project)"
MIN_BLOCK_LEN = 40          # ignore boilerplate paragraphs shorter than this
MIN_IMPROVE_FACTOR = 1.3    # only overwrite content_snippet if new text is ≥30% longer


# Email boilerplate patterns — these paragraphs are header/footer junk
BOILERPLATE_PATTERNS = [
    r"unsubscribe",
    r"view in (your )?browser",
    r"sign up",
    r"forwarded this email",
    r"all rights reserved",
    r"privacy policy",
    r"manage (your )?preferences",
    r"sent to you by",
    r"©\s*\d{4}",
    r"^welcome,?\s*humans",
    r"^today'?s\s",
    r"(^|\b)together with\b",   # sponsor block headers
]
BOILERPLATE_RE = re.compile("|".join(BOILERPLATE_PATTERNS), re.IGNORECASE)


def get_ktn_articles_by_newsletter():
    """
    Group DB articles by their newsletter base URL (stripping #story-N).
    Returns { base_url: [article_dict, ...] }, only for articles without full_text.
    """
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.id, a.url, a.title, a.source_name, a.content_snippet
           FROM articles a
           INNER JOIN story_articles sa ON a.id = sa.article_id
           WHERE a.url LIKE 'https://kill-the-newsletter.com%'
             AND (a.full_text IS NULL OR a.full_text = '')
           ORDER BY a.id"""
    ).fetchall()
    conn.close()

    groups = defaultdict(list)
    for r in rows:
        r = dict(r)
        base = r["url"].split("#", 1)[0]
        groups[base].append(r)
    return groups


def extract_anchor_keywords(title):
    """
    Pull 2-5 distinctive tokens from an article title for block matching.
    Prefers: capitalized proper nouns, product names, numbers, then long common words.
    """
    if not title:
        return []
    # Capitalized words & compound product names (Codex, ChatGPT, GPT-4, Gemini, $100, etc.)
    caps = re.findall(r"\b[A-Z][\w\-']*[\w']\b", title)
    # Numbers and dollar amounts
    nums = re.findall(r"\$?\d[\w.,-]*", title)
    # Remove fillers
    fillers = {"The", "A", "An", "Is", "Are", "In", "On", "To", "For", "With", "And", "Of", "By", "At"}
    keywords = [w for w in caps if w not in fillers]
    keywords.extend(n for n in nums if n not in keywords)
    # If we ended up with nothing, fall back to long lowercase words
    if len(keywords) < 2:
        keywords.extend(w for w in title.split() if len(w) > 5 and w.lower() not in keywords)
    # Deduplicate while preserving order
    seen = set()
    out = []
    for k in keywords:
        if k.lower() not in seen:
            seen.add(k.lower())
            out.append(k)
    return out[:5]


def parse_newsletter_blocks(html):
    """
    Return an ordered list of paragraph blocks from a KTN email newsletter.
    Each block is already cleaned and de-boilerplated.
    """
    soup = BeautifulSoup(html, "html.parser")
    # Drop everything non-content
    for tag in soup(["style", "script", "head", "meta", "link", "noscript", "svg"]):
        tag.decompose()

    blocks = []
    for el in soup.find_all(["p", "li"]):
        text = el.get_text(" ", strip=True)
        # Strip blockquote markers BS4 leaves when flattening <blockquote> elements
        text = re.sub(r"^\s*>\s*", "", text)
        text = re.sub(r"\s+>\s+", " - ", text)
        text = re.sub(r"\s+", " ", text)
        if len(text) < MIN_BLOCK_LEN:
            continue
        if BOILERPLATE_RE.search(text):
            continue
        blocks.append(text)
    return blocks


def extract_single_block(blocks, anchor_idx):
    """
    Return ONLY the matched block — no adjacent merging.
    Adjacent merging caused cross-story contamination (grabbing the next
    story's opening paragraph). A single matched block is safer: if it's
    too short, the frontend falls back to content_snippet.
    """
    if anchor_idx < 0 or anchor_idx >= len(blocks):
        return ""
    return blocks[anchor_idx][:1200]


def match_article_to_block(article_title, blocks):
    """
    Find the block that best matches an article title via keyword overlap.
    Requires at least 2 keyword matches to avoid false positives.
    Gives bonus weight to the first keyword (usually the company/product name).
    Returns (block_index, score) or (None, 0).
    """
    keywords = extract_anchor_keywords(article_title)
    if not keywords:
        return None, 0

    primary = keywords[0] if keywords else None
    best_idx = None
    best_score = 0
    for i, block in enumerate(blocks):
        matches = [k for k in keywords if k in block]
        score = len(matches)
        if score < 2:
            continue
        if primary and primary in matches:
            score += 2
        if len(block) > 200:
            score += 1
        if score > best_score:
            best_score = score
            best_idx = i
    return best_idx, best_score


def process_newsletter(base_url, articles, dry_run=False):
    """Fetch one newsletter and map its articles to blocks. Returns stats."""
    try:
        r = requests.get(base_url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if r.status_code == 404:
            # KTN purges older entries — expected, not an error
            return {"expired": True, "matched": 0, "skipped": 0, "total": len(articles)}
        r.raise_for_status()
        r.encoding = "utf-8"
    except requests.RequestException as e:
        return {"error": f"fetch failed: {e}", "matched": 0, "skipped": 0, "total": len(articles)}

    blocks = parse_newsletter_blocks(r.text)
    if not blocks:
        return {"error": "no content blocks", "matched": 0, "skipped": 0, "total": len(articles)}

    stats = {"matched": 0, "skipped": 0, "total": len(articles), "blocks": len(blocks)}

    # Score ALL (article, block) candidates first, then assign by highest score.
    # Each block can only be assigned to ONE article (exclusive matching).
    candidates = []
    for art in articles:
        idx, score = match_article_to_block(art["title"], blocks)
        if idx is not None and score > 0:
            candidates.append((score, art, idx))

    # Sort by score descending — best matches get first pick
    candidates.sort(key=lambda x: -x[0])
    used_blocks = set()

    for score, art, idx in candidates:
        if idx in used_blocks:
            stats["skipped"] += 1
            continue

        body = extract_single_block(blocks, idx)
        current = art.get("content_snippet") or ""
        if len(body) < len(current) * MIN_IMPROVE_FACTOR:
            stats["skipped"] += 1
            continue

        used_blocks.add(idx)

        if dry_run:
            safe_title = art["title"][:55].encode("ascii", "replace").decode()
            safe_body = body[:100].encode("ascii", "replace").decode()
            print(f"    MATCH [{score}] {safe_title}")
            print(f"       -> {safe_body}...")
        else:
            update_article_full_text(art["id"], body)
        stats["matched"] += 1

    return stats


def run_pipeline(dry_run=False, limit=None, verbose=True):
    """
    Programmatic entry point — safe to call from generate.py without argparse.
    Returns a totals dict. Idempotent: articles already having full_text are skipped.
    """
    groups = get_ktn_articles_by_newsletter()
    if not groups:
        if verbose:
            print("  No KTN articles pending full_text.")
        return {"matched": 0, "skipped": 0, "errors": 0, "expired": 0}

    newsletters = list(groups.items())
    if limit:
        newsletters = newsletters[:limit]

    if verbose:
        print(f"  Processing {len(newsletters)} unique KTN newsletters "
              f"covering {sum(len(a) for _, a in newsletters)} articles.")

    totals = {"matched": 0, "skipped": 0, "errors": 0, "expired": 0}

    for i, (base_url, articles) in enumerate(newsletters, 1):
        stats = process_newsletter(base_url, articles, dry_run=dry_run)
        if stats.get("expired"):
            if verbose:
                print(f"    [{i}/{len(newsletters)}] expired ({len(articles)} articles)")
            totals["expired"] += len(articles)
        elif "error" in stats:
            if verbose:
                print(f"    [{i}/{len(newsletters)}] ERROR: {stats['error']}")
            totals["errors"] += 1
        else:
            if verbose:
                print(f"    [{i}/{len(newsletters)}] matched {stats['matched']}/{stats['total']}")
            totals["matched"] += stats["matched"]
            totals["skipped"] += stats["skipped"]

        if i < len(newsletters):
            time.sleep(FETCH_SLEEP)

    if verbose:
        print(f"  Summary: matched {totals['matched']}, skipped {totals['skipped']}, "
              f"expired {totals['expired']}, errors {totals['errors']}")
    return totals


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="Max newsletters to process")
    args = parser.parse_args()

    totals = run_pipeline(dry_run=args.dry_run, limit=args.limit, verbose=True)
    return 0 if totals["matched"] > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
