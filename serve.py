"""
Node — Local server.
Usage: python serve.py
"""

import json
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

from database import get_all_stories, get_unprocessed_articles
from fetcher import fetch_all
from categorizer import categorize_articles
from sources import CATEGORIES

PORT = 8080

CAT_STYLES = {
    "model_releases":      {"color": "#a78bfa", "glow": "129,140,248", "grad": "135deg, #312e81, #1e1b4b"},
    "products_tools":      {"color": "#fbbf24", "glow": "251,191,36",  "grad": "135deg, #451a03, #78350f"},
    "industry_business":   {"color": "#60a5fa", "glow": "96,165,250",  "grad": "135deg, #172554, #1e3a5f"},
    "funding_acquisitions":{"color": "#fb7185", "glow": "251,113,133", "grad": "135deg, #4c0519, #881337"},
    "research":            {"color": "#34d399", "glow": "52,211,153",  "grad": "135deg, #022c22, #064e3b"},
    "open_source":         {"color": "#c084fc", "glow": "192,132,252", "grad": "135deg, #2e1065, #3b0764"},
    "editorial":           {"color": "#fb923c", "glow": "251,146,60",  "grad": "135deg, #431407, #7c2d12"},
    "sci_tech_trends":     {"color": "#06b6d4", "glow": "6,182,212",   "grad": "135deg, #083344, #164e63"},
}

app = Flask(__name__, static_folder="static")
_fetch_lock = threading.Lock()


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/stories")
def api_stories():
    stories = get_all_stories(limit=300)
    cats = [{**c, **CAT_STYLES.get(c["id"], {})} for c in CATEGORIES]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return jsonify({"stories": stories, "categories": cats, "today": today})


@app.route("/api/fetch")
def api_fetch():
    with _fetch_lock:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            count = fetch_all()
            stories_count = 0
            unprocessed = get_unprocessed_articles(today)
            if unprocessed:
                stories_count = categorize_articles(today)
            scrape_error = None
            try:
                from scrape_ktn_stories import run_pipeline as scrape_ktn
                scrape_ktn(verbose=False)
            except Exception as e:
                scrape_error = str(e)
            result = {"status": "ok", "new_articles": count, "stories_created": stories_count}
            if scrape_error:
                result["scrape_warning"] = scrape_error
            return jsonify(result)
        except Exception as e:
            # Surface the failure as HTTP 500 so clients checking status codes
            # don't misread a pipeline crash as success.
            return jsonify({"status": "error", "message": str(e)}), 500


# Serve PWA assets + digest.html from repo root.
# Flask's built-in /static handles static/index.html at /; this catch-all
# covers manifest.json, sw.js, icon.svg, and digest.html which live at the
# repo root (not inside static/). /favicon.ico has its own dedicated route
# below because no favicon.ico file exists — we redirect it to icon.svg.
ROOT_FILES = {"manifest.json", "sw.js", "icon.svg", "digest.html"}


@app.route("/favicon.ico")
def favicon():
    # Browsers auto-probe /favicon.ico even when <link rel="icon"> is set.
    # Serve icon.svg with the SVG mime type so the request resolves cleanly
    # instead of 404-ing on every page load.
    return send_from_directory(".", "icon.svg", mimetype="image/svg+xml")


@app.route("/<path:filename>")
def root_file(filename):
    if filename in ROOT_FILES:
        return send_from_directory(".", filename)
    abort(404)


def startup_fetch():
    """Auto-fetch new articles on server startup (full pipeline).
    Takes the same _fetch_lock as /api/fetch so a user click during startup
    can't kick off a concurrent second pipeline run."""
    with _fetch_lock:
        try:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            print("Auto-fetching articles...")
            count = fetch_all()
            print(f"  {count} new articles fetched.")
            unprocessed = get_unprocessed_articles(today)
            if unprocessed:
                print(f"  Categorizing {len(unprocessed)} articles...")
                n = categorize_articles(today)
                print(f"  {n} stories created.")
            # Scrape original newsletter prose for KTN articles
            try:
                from scrape_ktn_stories import run_pipeline as scrape_ktn
                scrape_ktn(verbose=False)
                print("  KTN full_text scraping complete.")
            except Exception as e:
                print(f"  KTN scraping error: {e}")
        except Exception as e:
            print(f"  Startup fetch error: {e}")


if __name__ == "__main__":
    Path("static").mkdir(exist_ok=True)
    # Auto-fetch in background so server starts immediately
    threading.Thread(target=startup_fetch, daemon=True).start()
    print(f"Node: http://localhost:{PORT}")
    webbrowser.open(f"http://localhost:{PORT}")
    app.run(host="0.0.0.0", port=PORT, debug=False)
