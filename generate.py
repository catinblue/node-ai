"""
Node — Generate static HTML digest page with typewriter design.

Usage:
    python generate.py              # fetch + categorize + generate
    python generate.py --no-fetch   # just generate from existing DB data
"""

import hashlib
import json
import re
import sys
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from database import get_all_stories, get_available_dates, get_unprocessed_articles
from fetcher import fetch_all
from categorizer import categorize_articles
from sources import CATEGORIES
from scrape_ktn_stories import run_pipeline as scrape_ktn_full_text

OUTPUT_PATH = Path(__file__).parent / "digest.html"

CAT_COLORS = {
    "model_releases": "#6366f1",
    "products_tools": "#d97706",
    "industry_business": "#2c3e6a",
    "funding_acquisitions": "#9b2c2c",
    "research": "#059669",
    "open_source": "#7c3aed",
    "editorial": "#d97706",
    "sci_tech_trends": "#0891b2",
}


def _safe_json(obj):
    """Serialize `obj` to JSON and neutralize any "</" sequence so a hostile
    string like "</script>" inside story data cannot break out of the
    <script> tag that embeds it in digest.html. Standard defensive pattern
    for inline JSON in HTML."""
    return json.dumps(obj, default=str, ensure_ascii=False).replace("</", "<\\/")


# Privacy hardening — strip credentials-bearing URLs before writing them to a
# publicly-readable artifact. KTN feed/entry URLs contain the user's private
# inbox feed ID; anyone with the URL can read the proxied newsletter content.
# Other newsletter sources (Beehiiv archives, HN, HF Papers) are public and
# left untouched. See ~/.claude/memory/feedback_privacy_audit_spec.md §3.4.
_KTN_URL_PATTERN = re.compile(r'https?://kill-the-newsletter\.com/[^\s"\'<>\\]*')


def _opaque_hash(url):
    """Stable 16-hex SHA-256 prefix — same input always maps to same output
    so client-side dedup/keys keep working without leaking the source URL."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def _sanitize_url_for_public(url):
    if not url:
        return url
    if _KTN_URL_PATTERN.match(url):
        return f"#kts-{_opaque_hash(url)}"
    return url


def _scrub_text(text):
    """Replace any embedded KTN URL inside free-text fields (snippets,
    summaries, full_text) with the same opaque hash format used for url
    fields. Catches LLM-extracted text that may have echoed the URL."""
    if not text:
        return text
    return _KTN_URL_PATTERN.sub(lambda m: f"#kts-{_opaque_hash(m.group(0))}", text)


def _sanitize_stories_for_public(stories):
    """Walk every story + nested article, strip credentials from url and
    text fields. Returns a deep-copied list — does not mutate input."""
    out = []
    for s in stories:
        articles = s.get("articles") or []
        clean_articles = []
        for a in articles:
            clean_articles.append({
                **a,
                "url": _sanitize_url_for_public(a.get("url") or ""),
                "content_snippet": _scrub_text(a.get("content_snippet") or ""),
                "full_text": _scrub_text(a.get("full_text") or ""),
                "summary": _scrub_text(a.get("summary") or ""),
            })
        out.append({
            **s,
            "summary": _scrub_text(s.get("summary") or ""),
            "articles": clean_articles,
        })
    return out


def generate_html(all_stories, today):
    all_stories = _sanitize_stories_for_public(all_stories)
    stories_json = _safe_json(all_stories)
    # Defensive guard — if any sanitizer branch missed a path, fail loudly
    # instead of silently shipping a leaky digest.
    if "kill-the-newsletter.com" in stories_json:
        raise RuntimeError(
            "Sanitization failed: KTN URL still present in serialized output. "
            "Check _sanitize_stories_for_public coverage."
        )
    categories_json = _safe_json(
        [{**c, "color": CAT_COLORS.get(c["id"], "#888")} for c in CATEGORIES]
    )

    # Read the static/index.html template and inject data
    # Instead of template, we embed data directly into the typewriter HTML
    template_path = Path(__file__).parent / "static" / "index.html"
    html = template_path.read_text(encoding="utf-8")

    # Replace the API-based loading with embedded data
    embedded = f"""
// Embedded data (no server needed)
ALL = {stories_json};
CATS = {categories_json};
TODAY = "{today}";
CAT_MAP = {{}};
CATS.forEach(c => CAT_MAP[c.id] = c);
const tc = ALL.filter(s => s.date === TODAY).length;
const wc = ALL.filter(s => isW(s.date)).length;
filter.period = tc > 0 ? 'day' : wc > 0 ? 'week' : 'month';
render();
document.getElementById('loading').classList.add('hide');
setTimeout(() => document.getElementById('loading').style.display = 'none', 300);
// Slider — attach once after DOM is ready
document.getElementById('stack-slider').addEventListener('input', function(e) {{
  stackIdx = parseInt(e.target.value);
  renderStack();
}});
"""
    html = html.replace("loadData();", embedded)

    return html


MIN_STORIES = 5  # refuse to publish a near-empty digest


def main():
    no_fetch = "--no-fetch" in sys.argv
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if no_fetch and get_all_stories(limit=1) == []:
        print("ERROR: --no-fetch but database has no stories. Run without --no-fetch first.")
        sys.exit(1)

    if not no_fetch:
        print("Fetching articles...")
        count = fetch_all()
        print(f"\n{count} new articles fetched.")

        unprocessed = get_unprocessed_articles(today)
        if unprocessed:
            print(f"\nCategorizing {len(unprocessed)} articles...")
            n = categorize_articles(today)
            print(f"{n} stories created.")
        else:
            print("No unprocessed articles to categorize.")

        # Slice B: recover human-written newsletter prose for new KTN stories.
        # Idempotent — skips articles that already have full_text.
        print("\nScraping KTN full_text (Slice B)...")
        try:
            scrape_ktn_full_text()
        except Exception as e:
            print(f"  [WARN] KTN scraping failed: {e}")

    all_stories = get_all_stories(limit=300)

    if len(all_stories) < MIN_STORIES:
        print(f"ERROR: only {len(all_stories)} stories in database (minimum {MIN_STORIES}). Aborting to avoid publishing an empty digest.")
        sys.exit(1)

    print(f"\nGenerating digest ({len(all_stories)} total stories)...")
    html = generate_html(all_stories, today)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Written to {OUTPUT_PATH}")

    webbrowser.open(OUTPUT_PATH.as_uri())
    print("Opened in browser.")


if __name__ == "__main__":
    main()
