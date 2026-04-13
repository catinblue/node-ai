# Node — AI Intelligence Terminal

[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Mistral AI](https://img.shields.io/badge/LLM-Mistral_AI-orange.svg)](https://mistral.ai/)
[![No Build Tools](https://img.shields.io/badge/Frontend-No_Build_Tools-green.svg)](#tech-stack)

A personal news intelligence terminal that aggregates 5 AI newsletters, extracts and deduplicates stories via LLM, and renders them as a physics-driven single-page app — with full-text search, knowledge graph, timeline drill-down, and zero-ML personalization.

## How It Works

```
  Newsletters (email)              Pipeline (Python)                Browser (digest.html)
 ┌──────────────────┐         ┌──────────────────────┐          ┌──────────────────────┐
 │  AlphaSignal     │         │                      │          │  Swipeable card feed  │
 │  The Neuron      │  KTN    │  fetcher.py           │  embed   │  Full-text search     │
 │  AI Valley       │──RSS──▶ │  categorizer.py      │──JSON──▶ │  Knowledge graph      │
 │  Every           │  feed   │  scrape_ktn_stories.py│  into    │  Timeline drill-down  │
 │  AI Tinkerers    │         │  generate.py          │  HTML    │  Bookmarks + export   │
 └──────────────────┘         └──────────────────────┘          └──────────────────────┘
                                       │
                                       ▼
                                 SQLite (news.db)
                              articles ←M:N→ stories
```

## Quick Start

```bash
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env: set KTN_FEED_ID and MISTRAL_API_KEY

# Run the full pipeline
python generate.py

# Open digest.html — everything runs client-side from here
```

Regenerate HTML from an existing local database (no API calls, no tokens consumed):

```bash
python generate.py --no-fetch
```

> Requires a local `news.db` from a previous run. A fresh clone has no database — run the full pipeline first.

---

## Pipeline

Four stages. `--no-fetch` skips the first three (fetch + categorize + scrape) and regenerates HTML from existing data only:

| Stage | File | What It Does |
|-------|------|--------------|
| **Fetch** | `fetcher.py` | Polls KTN Atom feed, sends newsletter HTML to Mistral AI, extracts individual stories |
| **Categorize** | `categorizer.py` | Merges same-topic stories across newsletters, assigns 1 of 8 categories, ranks by cross-coverage |
| **Scrape** | `scrape_ktn_stories.py` | Recovers original newsletter prose via BeautifulSoup keyword matching |
| **Generate** | `generate.py` | Embeds story JSON into `static/index.html`, outputs self-contained `digest.html` |

### Content Priority Chain

```
full_text (scraped original prose)
    └─ fallback ─▶ content_snippet (LLM per-article extract)
                        └─ fallback ─▶ summary (LLM aggregate)
```

### Categories

| Category | Scope |
|----------|-------|
| Model Releases | New model launches, benchmarks, capabilities |
| Products & Tools | AI products, features, updates |
| Industry & Business | Trends, policy, regulation, adoption |
| Funding & Acquisitions | Startup funding, M&A, valuations |
| Research | Papers, breakthroughs, new techniques |
| Open Source | Models, datasets, frameworks |
| Editorial | Long-form deep dives (Every) |
| Sci-Tech Trends | Cross-disciplinary science beyond pure AI |

---

## Frontend

Single-file SPA. ~2200 lines of vanilla JS + CSS + Canvas 2D. Zero frameworks, zero build tools. Loads Google Fonts, Vercel Analytics/Speed Insights (via esm.sh), and Google favicon API at runtime.

### Views

| View | Features |
|------|----------|
| **Feed** | Tinder-style swipeable card stack, 5-layer depth stagger, ripple lighting via Canvas, scrubbable slider |
| **Search** | Weighted full-text scoring, keyword highlighting, 30-day timeline sparkline, click-to-drill-down by day |
| **Graph** | Force-directed keyword co-occurrence map (Coulomb repulsion + Hooke attraction), drag + hover + click-to-search |
| **Saved** | Bento-lite bookmark grid, one-click export to Markdown with tags, sources, and excerpts |

### Intelligence Features

| Feature | How It Works |
|---------|--------------|
| **Full-text search** | Weighted scoring: headline ×10, full_text ×5, summary ×3, snippet ×2, with freshness and coverage bonuses |
| **Story Echoes** | Proper-noun keyword collision finds related stories across the corpus |
| **Breadcrumb navigation** | A→B→C exploration chain with depth badge and Escape key pop-back |
| **Keyword Pills** | Clickable `#topic` chips jump from detail view to search |
| **Timeline drill-down** | Click any sparkline bar to slice results to a single day |
| **Knowledge Graph** | 35-entity force-directed Canvas visualization with drag, hover, click-to-search |
| **Personalization** | Zero-ML affinity matrix: bookmarks (+1/keyword) and searches (+0.5) reorder the feed |

### Interaction Design

| Element | Detail |
|---------|--------|
| Swipe easing | Quintic Out — `cubic-bezier(0.23, 1, 0.32, 1)` |
| Ripple lighting | Energy-sensing elliptical Canvas blooms, screen-blended onto cards |
| Bookmark | Spring pop + glow pulse animation, in-place DOM update |
| Zen Reading Mode | 3 font scales (16/18/20px) via Aa toggle, persisted in localStorage |
| Drop cap | Fraunces serif, 3em, on first paragraph of detail view |

---

## Repository Structure

```
ai-news-app/
├── generate.py                # Pipeline orchestrator: fetch → categorize → scrape → generate
├── fetcher.py                 # RSS ingestion + Mistral LLM story extraction
├── categorizer.py             # Cross-newsletter dedup + categorization
├── database.py                # SQLite schema, CRUD, migrations
├── sources.py                 # Feed URLs + 8 category definitions
├── scrape_ktn_stories.py      # Newsletter prose recovery (BeautifulSoup)
├── scrape_full_text.py        # Generic article extraction (trafilatura)
├── scrape_archives.py         # Backfill historical data from Beehiiv
├── clean_ai_valley.py         # Archive boilerplate cleanup
├── serve.py                   # Flask dev server (/api/stories, /api/fetch)
├── scheduler.py               # Optional APScheduler cron (7:30 AM + 6:30 PM)
├── static/
│   └── index.html             # Frontend template (~2200 lines)
├── digest.html                # Generated output (self-contained SPA)
├── vercel.json                # Vercel deployment config
└── requirements.txt
```

## Database Schema

```
articles                          stories
┌─────────────────────┐          ┌─────────────────────┐
│ id (PK)             │          │ id (PK)             │
│ title               │          │ date                │
│ url (UNIQUE)        │    M:N   │ category            │
│ source_name         │◄────────▶│ headline            │
│ published_at        │          │ summary             │
│ summary             │          │ created_at          │
│ content_snippet     │          └─────────────────────┘
│ full_text           │
│ language            │          story_articles (junction)
└─────────────────────┘          ┌─────────────────────┐
                                 │ story_id (FK)       │
                                 │ article_id (FK)     │
                                 └─────────────────────┘
```

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `KTN_FEED_ID` | Yes | Kill the Newsletter feed identifier |
| `MISTRAL_API_KEY` | Yes | Mistral AI API key for story extraction + categorization |

### Adding Newsletter Sources

1. Subscribe to a newsletter using the Kill the Newsletter email address
2. Newsletter appears automatically in the Atom feed
3. Add sender detection pattern in `fetcher.py` (author email / Beehiiv bounce ID matching)

### Automated Scheduling

```bash
python scheduler.py  # Runs pipeline at 7:30 AM and 6:30 PM Paris time
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.13, SQLite3 (WAL mode), BeautifulSoup4, trafilatura |
| **LLM** | Mistral AI — Small Latest (extraction + categorization, free tier available) |
| **Frontend** | Vanilla JS (ES6+), CSS3, Canvas 2D — no build tools |
| **Runtime deps** | Google Fonts, Vercel Analytics/Speed Insights (esm.sh), Google Favicon API |
| **Fonts** | Outfit (body), Fraunces (display / drop caps) |
| **Physics** | Custom Verlet integration (ripple engine), Coulomb + Hooke force sim (knowledge graph) |
| **Deployment** | Vercel (static HTML) or local Python (dynamic regeneration) |

## Performance

| Metric | Value |
|--------|-------|
| Pipeline end-to-end | ~30–60s |
| Input latency (JS event) | 0.1ms |
| Long tasks during transitions | 0 (never >50ms) |
| DOM leakage (3 nav cycles) | 0 nodes |
| Output file size | Single HTML, <500KB |
| External runtime requests | Google Fonts, Vercel Analytics, favicon API |

## License

ISC
