"""
AI News Digest — Generate static HTML digest page with typewriter design.

Usage:
    python generate.py              # fetch + categorize + generate
    python generate.py --no-fetch   # just generate from existing DB data
"""

import json
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
}


def generate_html(all_stories, today):
    stories_json = json.dumps(all_stories, default=str, ensure_ascii=False)
    categories_json = json.dumps(
        [{**c, "color": CAT_COLORS.get(c["id"], "#888")} for c in CATEGORIES],
        ensure_ascii=False,
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


def main():
    no_fetch = "--no-fetch" in sys.argv
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

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

    print(f"\nGenerating digest ({len(all_stories)} total stories)...")
    html = generate_html(all_stories, today)
    OUTPUT_PATH.write_text(html, encoding="utf-8")
    print(f"Written to {OUTPUT_PATH}")

    webbrowser.open(OUTPUT_PATH.as_uri())
    print("Opened in browser.")


if __name__ == "__main__":
    main()
