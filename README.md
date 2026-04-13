# ◧ Node — AI Intelligence Terminal

A personal AI news intelligence terminal that aggregates 5 newsletters, extracts stories via LLM, and presents them through a physics-driven swipe interface with full-text search, knowledge graph visualization, timeline drill-down, and personalized ranking.

## Quick Start

```bash
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env: set KTN_FEED_ID and MISTRAL_API_KEY

# Full pipeline: fetch → categorize → scrape original prose → generate HTML
python generate.py

# Regenerate from existing data (no API calls, no tokens consumed)
python generate.py --no-fetch

# Open digest.html in browser — everything runs client-side from there
```

## Features

### Content Engine
- **Multi-source aggregation** — AlphaSignal, AI Valley, The Neuron, Every, AI Tinkerers via Kill the Newsletter RSS proxy
- **LLM story extraction** — Mistral AI (Mistral Small Latest) extracts individual stories from newsletter HTML
- **Cross-newsletter deduplication** — Stories covered by multiple sources merge into single entries ranked by coverage count
- **Original prose scraping** — `scrape_ktn_stories.py` recovers human-written newsletter text via BeautifulSoup section matching
- **Content priority chain** — `full_text` (scraped) > `content_snippet` (LLM per-article) > `summary` (LLM aggregate)
- **8 categories** — Model Releases, Products & Tools, Industry & Business, Funding & Acquisitions, Research, Open Source, Editorial, Sci-Tech Trends

### Intelligence Engine
- **Full-text search** — Weighted scoring: headline ×10, full_text ×5, summary ×3, snippet ×2, with freshness and coverage bonuses
- **Story Echoes** — Proper-noun keyword collision algorithm finds thematically related stories across the corpus
- **Breadcrumb navigation** — A→B→C exploration chain with depth badge and Escape key pop-back
- **Keyword Pills** — Clickable `#topic` chips jump from detail view to full-text search
- **Timeline sparkline** — 30-day Canvas bar chart showing story distribution over time
- **Timeline drill-down** — Click any bar to slice results to a single day
- **Knowledge Graph** — Force-directed Canvas visualization of keyword co-occurrence (Coulomb repulsion + Hooke attraction)
- **Personalization** — Zero-ML affinity matrix: bookmarks (+1/keyword) and searches (+0.5) reorder the feed

### Interaction
- **Tinder-style swipe** — Horizontal card swiping with Quintic Out easing and edge glow offset
- **Ripple lighting** — Energy-sensing elliptical Canvas blooms on swipe, screen-blended onto cards
- **5-layer card deck** — Background cards with proportional stagger for physical depth
- **Scrubbable slider** — Draggable progress bar with amber glowing thumb
- **Bookmark micro-interaction** — Spring pop + glow pulse animation (in-place DOM update)
- **Zen Reading Mode** — 3 font scales (16/18/20px) via Aa toggle, persisted in localStorage
- **Export to Markdown** — One-click briefing download with tags, sources, and excerpts

### Views
- **Feed** — Swipeable card stack with content-hugging layout
- **Search** — Full-text results with keyword highlighting and timeline
- **Graph** — Force-directed knowledge map (35 entities, drag + hover + click-to-search)
- **Saved** — Bento-lite bookmark list with Export .MD button

## Architecture

```
Kill the Newsletter feed (Atom XML)
        │
        ▼
   fetcher.py ────── LLM extraction (Mistral AI)
        │
        ▼
   database.py ───── SQLite: articles, stories, story_articles
        │
        ▼
  categorizer.py ─── Deduplication + categorization via LLM
        │
        ▼
  scrape_ktn_stories.py ── Newsletter prose extraction (BeautifulSoup)
        │
        ▼
   generate.py ───── Builds static digest.html with embedded JSON data
        │
        ▼
   digest.html ───── Single-file SPA: CSS + JS + data (opens in any browser)
```

### File Overview

| File | Purpose |
|------|---------|
| `generate.py` | Pipeline orchestrator: fetch → categorize → scrape → generate |
| `fetcher.py` | RSS ingestion, KTN newsletter LLM extraction, API fetchers |
| `categorizer.py` | Cross-newsletter dedup + categorization via Mistral AI |
| `database.py` | SQLite schema, CRUD, migrations (`full_text` column) |
| `sources.py` | Feed URLs + 8 category definitions (data-driven) |
| `scrape_ktn_stories.py` | KTN section extraction via BeautifulSoup keyword matching |
| `clean_ai_valley.py` | Archive boilerplate cleanup (regex decontamination) |
| `static/index.html` | Frontend template: all CSS + JS (~2200 lines, zero dependencies) |
| `scheduler.py` | Optional APScheduler cron: fetch → categorize → scrape → generate on schedule |

### Models and APIs

| Service | Model | Purpose | Cost |
|---------|-------|---------|------|
| Mistral AI | Mistral Small Latest | Story extraction + categorization | Free tier available |

### Performance (Telemetry)

| Metric | Value |
|--------|-------|
| Pipeline (fetch → generate) | ~30-60s end-to-end |
| Input latency (JS event) | 0.1ms/event |
| Long tasks during transitions | 0 (never >50ms) |
| DOM leakage (3 navigation cycles) | 0 nodes |
| Output file size | Single HTML, <500KB |
| External JS/CSS dependencies | 0 |

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `KTN_FEED_ID` | Yes | Kill the Newsletter feed identifier |
| `MISTRAL_API_KEY` | Yes | Mistral AI API key for LLM inference |

### Adding Newsletter Sources

1. Subscribe to a newsletter using the Kill the Newsletter email address
2. Newsletter appears automatically in the Atom feed
3. Add sender detection pattern in `fetcher.py` (author email / Beehiiv bounce ID matching)

### Automated Scheduling

```bash
# Optional: run pipeline on a cron schedule
python scheduler.py  # Configured for 7:30 AM and 6:30 PM
```

### Tech Stack

- **Backend**: Python 3.13, SQLite3, BeautifulSoup4, trafilatura
- **Frontend**: Vanilla JS, CSS3, Canvas 2D (zero frameworks, zero build tools)
- **Fonts**: Outfit (body), Fraunces (display/drop caps)
- **Physics**: Custom Verlet integration (ripple engine), Coulomb+Hooke force simulation (knowledge graph)

