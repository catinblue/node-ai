"""
AI News Digest — Streamlit UI
"""

import streamlit as st
from datetime import datetime, timezone

from database import get_stories_for_date, get_available_dates, get_unprocessed_articles
from sources import CATEGORIES
from fetcher import fetch_all
from categorizer import categorize_articles

# Category lookup
CAT_MAP = {c["id"]: c for c in CATEGORIES}

st.set_page_config(page_title="AI News Digest", page_icon="📡", layout="wide")

# ── Sidebar ──────────────────────────────────────────────

with st.sidebar:
    st.title("📡 AI News Digest")

    # Date picker
    available = get_available_dates(limit=30)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    if available:
        dates = sorted(set(available + [today]), reverse=True)
    else:
        dates = [today]

    selected_date = st.selectbox("Date", dates, index=0)

    st.divider()

    # Actions
    st.subheader("Actions")

    if st.button("🔄 Fetch new articles", use_container_width=True):
        with st.spinner("Fetching sources..."):
            count = fetch_all()
        st.success(f"{count} new articles fetched.")

    if st.button("🧠 Categorize articles", use_container_width=True):
        unprocessed = get_unprocessed_articles(selected_date)
        if not unprocessed:
            st.info("No unprocessed articles for this date.")
        else:
            with st.spinner(f"Categorizing {len(unprocessed)} articles..."):
                n = categorize_articles(selected_date)
            st.success(f"{n} stories created.")
            st.rerun()

    st.divider()
    unprocessed = get_unprocessed_articles(selected_date)
    if unprocessed:
        st.caption(f"⚠️ {len(unprocessed)} articles not yet categorized")

# ── Main content ─────────────────────────────────────────

stories = get_stories_for_date(selected_date)

if not stories:
    st.header(f"No stories for {selected_date}")
    st.info("Use the sidebar to fetch articles, then categorize them.")
    st.stop()

st.header(f"📰 {selected_date}")
st.caption(f"{len(stories)} stories from {sum(len(s['articles']) for s in stories)} articles")

# Group stories by category (preserve CATEGORIES order)
by_cat = {}
for s in stories:
    by_cat.setdefault(s["category"], []).append(s)

for cat in CATEGORIES:
    cat_stories = by_cat.get(cat["id"], [])
    if not cat_stories:
        continue

    st.subheader(f"{cat['emoji']} {cat['name_en']}")

    for story in cat_stories:
        with st.expander(f"**{story['headline']}** ({len(story['articles'])} sources)"):
            st.write(story["summary"])
            st.divider()
            for article in story["articles"]:
                source = article["source_name"]
                title = article["title"]
                url = article["url"]
                st.markdown(f"- [{title}]({url}) — *{source}*")
