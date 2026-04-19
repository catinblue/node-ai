# Node — AI Intelligence Terminal

[![Python 3.13](https://img.shields.io/badge/Python-3.13-blue.svg)](https://www.python.org/)
[![Mistral AI](https://img.shields.io/badge/LLM-Mistral_AI-orange.svg)](https://mistral.ai/)
[![PWA Installable](https://img.shields.io/badge/PWA-Installable-green.svg)](#install-as-a-mobile-app-pwa)

Turn 5 AI newsletters into a swipeable, installable intelligence terminal — LLM-deduplicated, physics-driven, zero backend, one Python pipeline.

## How It Works

```
  Newsletters (email)              Pipeline (Python)                Browser (digest.html)
 ┌──────────────────┐         ┌──────────────────────┐          ┌──────────────────────┐
 │  AlphaSignal     │         │  fetcher.py           │          │  Swipeable card feed  │
 │  The Neuron      │  KTN    │  categorizer.py      │  embed   │  Full-text search     │
 │  AI Valley       │──RSS──▶ │  scrape_ktn_stories.py│──JSON──▶ │  Knowledge graph      │
 │  Every           │  feed   │  generate.py          │  into    │  Timeline drill-down  │
 │  AI Tinkerers    │         │                      │  HTML    │  Bookmarks + export   │
 └──────────────────┘         └──────────────────────┘          └──────────────────────┘
                                       │                                   │
                                       ▼                                   ▼
                                 SQLite (news.db)                  Installable as a PWA
                              articles ←M:N→ stories               (offline after 1st visit)
```

## Quick Start

```bash
pip install -r requirements.txt

# Configure API keys
cp .env.example .env
# Edit .env: set KTN_FEED_ID and MISTRAL_API_KEY

# Run the full pipeline
python generate.py

# Opens digest.html — everything after this runs client-side
```

Regenerate HTML from an existing local database (no API calls, no tokens consumed):

```bash
python generate.py --no-fetch
```

> `--no-fetch` requires a pre-existing `news.db`. A fresh clone has no database — run the full pipeline at least once first.

---

## Install as a Mobile App (PWA)

Node ships as a Progressive Web App. On a deployed URL, install it like any native app:

1. Open the site in **Safari** (iOS) or **Chrome** (Android)
2. Tap **Share → Add to Home Screen**
3. Launch from the home-screen icon — standalone mode, no browser chrome

| Feature | Behavior |
|---------|----------|
| Standalone display | Full-screen, no Safari UI, custom status-bar color |
| Custom icon | `icon.svg` — 512×512 Node ◧ glyph, amber on near-black |
| Offline shell | Service Worker caches HTML + manifest + icon after first visit |
| Cache strategy | Stale-While-Revalidate for same-origin; third-party bypasses cache |
| No build step | Single `sw.js`, single `manifest.json`, zero tooling |

> Fonts load from Google Fonts at runtime. Offline = system-font fallback (functional but visually degraded). Everything else (swipe, search, graph, export) works without network once the shell is cached.

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

Single-file SPA. ~2500 lines of vanilla JS + CSS + Canvas 2D. Zero frameworks, zero build tools. Loads Google Fonts, Vercel Analytics (via esm.sh), and Google favicons at runtime.

### Views

| View | Features |
|------|----------|
| **Feed** | Tinder-style swipeable card stack, 5-layer depth stagger, Canvas ripple lighting, scrubbable slider |
| **Search** | Weighted full-text scoring, keyword highlighting, 30-day timeline sparkline, click-to-drill-down by day |
| **Graph** | Force-directed keyword co-occurrence map (Coulomb + Hooke + gravity), drag, hover, click-to-search |
| **Saved** | Bento-lite bookmark grid, one-click Markdown export with tags, sources, and excerpts |

### Intelligence Features

| Feature | How It Works |
|---------|--------------|
| **Full-text search** | Weighted scoring: headline ×10, full_text ×5, summary ×3, snippet ×2, plus freshness and coverage bonuses |
| **Story Echoes** | Proper-noun keyword collision finds related stories across the corpus |
| **Breadcrumb navigation** | A→B→C exploration chain with depth badge and Escape-key pop-back |
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
| Zen Reading Mode | 3 font scales (16 / 18 / 20 px) via `Aa` toggle, persisted in localStorage |
| Drop cap | Fraunces serif, 3em, on first paragraph of detail view |

### Mobile Optimization

| Feature | Detail |
|---------|--------|
| Overscroll cancel | `overscroll-behavior-y: none` — kills iOS elastic rubber-band |
| Graph touch | Unified pointer handlers; tap surfaces neighbor highlight; drag &lt; 5px = keyword search |
| UI chrome selection | `user-select: none` globally, re-enabled on `.art-text` and form inputs |
| Status bar | `apple-mobile-web-app-status-bar-style: black-translucent` |

---

## Architecture

### Repository Structure

```
ai-news-app/
├── generate.py                # Pipeline orchestrator: fetch → categorize → scrape → generate
├── fetcher.py                 # RSS ingestion + Mistral LLM story extraction
├── categorizer.py             # Cross-newsletter dedup + categorization
├── database.py                # SQLite schema, CRUD, migrations
├── sources.py                 # Feed URLs + 8 category definitions
├── scrape_ktn_stories.py      # Newsletter prose recovery (BeautifulSoup)
├── scrape_full_text.py        # Generic article extraction (trafilatura)
├── scrape_archives.py         # One-shot Beehiiv archive backfill
├── clean_ai_valley.py         # One-shot boilerplate stripper (AI Valley archives)
├── serve.py                   # Flask dev server (local only)
├── scheduler.py               # APScheduler cron alternative (local 24/7 boxes)
├── static/
│   └── index.html             # Frontend template (~2500 lines)
├── digest.html                # Generated output — self-contained SPA (tracked in git)
├── manifest.json              # PWA manifest
├── sw.js                      # Service Worker (Stale-While-Revalidate)
├── icon.svg                   # PWA icon (512×512 ◧ glyph)
├── vercel.json                # Vercel rewrite: / → /digest.html
├── .github/workflows/         # GitHub Actions cron (06:00 + 16:00 UTC)
├── requirements.txt
├── README.md                  # This file
└── HANDOFF.md                 # Full engineering handoff for new maintainers
```

### Database Schema

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

---

## Configuration

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `KTN_FEED_ID` | Yes | Kill the Newsletter feed identifier |
| `MISTRAL_API_KEY` | Yes | Mistral AI API key for story extraction + categorization |

### Adding Newsletter Sources

1. Subscribe to a newsletter using the Kill the Newsletter email address
2. Newsletter appears automatically in the Atom feed
3. Add sender detection pattern in `fetcher.py` (author email or Beehiiv bounce-ID matching)
4. Mention the new source in `categorizer.py`'s build_prompt so the LLM knows the total newsletter count

### Automated Scheduling

Two options:

```bash
# Option A: GitHub Actions (production — runs at 06:00 and 16:00 UTC)
# See .github/workflows/update.yml. Requires secrets:
#   MISTRAL_API_KEY, KTN_FEED_ID

# Option B: Local APScheduler cron daemon
python scheduler.py   # 07:30 + 18:30 Europe/Paris
```

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.13, SQLite3 (WAL mode), BeautifulSoup4, trafilatura |
| **LLM** | Mistral AI — Small Latest (extraction + categorization, free tier available) |
| **Frontend** | Vanilla JS (ES6+), CSS3, Canvas 2D — no build tools |
| **PWA** | Web App Manifest + Service Worker (Stale-While-Revalidate, same-origin) |
| **Runtime deps** | Google Fonts, Vercel Analytics / Speed Insights (esm.sh), Google Favicon API |
| **Fonts** | Outfit (body), Fraunces (display / drop caps) |
| **Physics** | Custom Verlet integration (ripple engine), Coulomb + Hooke force sim (knowledge graph) |
| **Deployment** | Vercel (static HTML) — daily refresh via GitHub Actions |

## Performance

| Metric | Value |
|--------|-------|
| Pipeline end-to-end | ~30–60s |
| Input latency (JS event) | 0.1ms |
| Long tasks during transitions | 0 (never > 50ms) |
| DOM leakage (3 nav cycles) | 0 nodes |
| Output file size | Single HTML, ~500KB |
| First-visit network | Google Fonts, esm.sh, Google Favicon API |
| Repeat-visit network | None (shell served from SW cache) |

---

## Further Reading

- **[HANDOFF.md](HANDOFF.md)** — full engineering handoff (~560 lines): architecture invariants, file-by-file tour, common tasks, things to NOT do, file:line quick-reference.

## License

ISC
