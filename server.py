"""
Node — Flask API Server
"""

from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory

from database import (
    get_available_dates,
    get_stories_for_date,
    get_unprocessed_articles,
)
from fetcher import fetch_all
from categorizer import categorize_articles

app = Flask(__name__, static_folder="static")


# ── API Routes ──────────────────────────────────────────────

@app.route("/api/dates")
def api_dates():
    """Get available dates with stories."""
    dates = get_available_dates(limit=30)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_dates = sorted(set(dates + [today]), reverse=True)
    return jsonify(all_dates)


@app.route("/api/stories")
def api_stories():
    """Get stories for a given date."""
    date_str = request.args.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    stories = get_stories_for_date(date_str)
    unprocessed = get_unprocessed_articles(date_str)
    return jsonify({
        "date": date_str,
        "stories": stories,
        "unprocessed_count": len(unprocessed),
    })


@app.route("/api/fetch", methods=["POST"])
def api_fetch():
    """Fetch new articles from all sources."""
    count = fetch_all()
    return jsonify({"new_articles": count})


@app.route("/api/categorize", methods=["POST"])
def api_categorize():
    """Categorize unprocessed articles for a date."""
    date_str = request.json.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    stories_count = categorize_articles(date_str)
    return jsonify({"stories_created": stories_count})


# ── Static file serving ─────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    Path("static").mkdir(exist_ok=True)
    app.run(debug=True, host="0.0.0.0", port=8080)
