# Node — Engineering Handoff

> **Audience:** A fullstack dev taking over this project cold.
> **Goal:** Everything you need to understand, run, extend, and iterate on the app in one document.
> **Last synced with code:** 2026-04-18 (commit `fee3d37` on `main`).

---

## 1. TL;DR in 60 seconds

**Node** is a single-user AI news intelligence terminal. It:

1. Polls an Atom feed (Kill-the-Newsletter) that aggregates 5 AI newsletters into one email→RSS pipe.
2. Uses **Mistral AI** to extract individual stories from each newsletter email, then merges duplicates across newsletters into one story per topic.
3. Scrapes the original newsletter HTML to recover human-written prose for each story.
4. Writes everything to **SQLite** (`news.db`) and generates a **self-contained `digest.html`** with all story data embedded as JSON.
5. `digest.html` is a ~2500-line vanilla-JS SPA served as a static file on **Vercel**. **GitHub Actions** refreshes it twice daily (06:00 and 16:00 UTC).

No build tools. No framework. No server in production. The frontend is rich (physics-driven swipe deck, knowledge graph, timeline drill-down, search, bookmarks, export, personalization) but all logic lives in one HTML file.

---

## 2. System architecture

```
┌─────────────────────┐       ┌────────────────────────────────────────┐       ┌──────────────────────┐
│  5 AI Newsletters   │       │        Python pipeline (per run)       │       │   digest.html (SPA)  │
│  via email          │       │                                         │       │                      │
│                     │       │  fetcher.py ─► Mistral (extract stories) │       │  Feed (swipe deck)   │
│  AlphaSignal        │  RSS  │       │                                  │       │  Search              │
│  The Neuron         │──────▶│       ▼                                  │──────▶│  Knowledge Graph     │
│  AI Valley          │       │  categorizer.py ─► Mistral (dedup+cat)   │       │  Saved + export      │
│  Every              │       │       │                                  │       │                      │
│  AI Tinkerers       │       │       ▼                                  │       │  Physics, ripple FX  │
│  (Kill-the-Newsltr) │       │  scrape_ktn_stories.py (BS4)             │       │  Local-storage state │
└─────────────────────┘       │       │                                  │       └──────────────────────┘
                              │       ▼                                  │                 ▲
                              │  generate.py (embed JSON, write HTML)    │                 │
                              └────────────────────────────────────────┬─┘                 │
                                              │                        │                   │
                                              ▼                        ▼                   │
                                       news.db (SQLite)         digest.html ───────────────┘
                                       (not in git,              (tracked in git,
                                        cached in CI)             served by Vercel)
```

**Key invariant:** the "product" is `digest.html`. It is a standalone artifact that contains everything the user sees. The Python pipeline exists solely to produce it. Production never runs Python.

---

## 3. Repository layout

```
ai-news-app/
├── generate.py                # Orchestrator — fetch → categorize → scrape → write digest.html
├── fetcher.py                 # RSS + API ingestion, LLM story extraction
├── categorizer.py             # Cross-newsletter dedup + 8-category classification
├── scrape_ktn_stories.py      # Newsletter-prose recovery (BeautifulSoup)
├── scrape_full_text.py        # Generic article-body extraction (trafilatura) — rarely used now
├── scrape_archives.py         # One-shot Beehiiv archive backfill (historical import)
├── clean_ai_valley.py         # One-shot boilerplate stripper for old AI Valley archives
├── database.py                # SQLite schema, CRUD, migrations (init_db runs on import)
├── sources.py                 # Feed URLs + 8 category definitions
├── serve.py                   # Flask dev server (optional, local only)
├── scheduler.py               # Local APScheduler (optional, replaced by GitHub Actions in prod)
│
├── static/
│   └── index.html             # Frontend template (~2500 lines). generate.py embeds JSON into it.
│
├── digest.html                # Self-contained SPA. TRACKED IN GIT — this is what Vercel serves.
├── vercel.json                # 1 line: rewrite / → /digest.html
├── .github/workflows/update.yml # Cron job: 06:00 + 16:00 UTC daily
│
├── requirements.txt           # Python deps
├── package.json               # Only used for Vercel analytics runtime deps (not installed in prod)
├── .env.example               # KTN_FEED_ID + MISTRAL_API_KEY
├── .gitignore                 # news.db + docs/ + screenshots all ignored
├── README.md                  # Public-facing README
└── HANDOFF.md                 # This file
```

**What's gitignored & why:**
- `news.db` — accumulated working data, not a product artifact. CI persists it via `actions/cache` (not `git push`).
- `docs/` — session logs, conversation history (private).
- `.env`, `.claude/`, `.superpowers/`, `.playwright-mcp/`, `.vercel/` — local dev config.
- `*.png`, `*.jpg` — Playwright test screenshots.

**Public surface = source code + config templates + `digest.html`.** Nothing else.

---

## 4. Backend (Python pipeline)

### 4.1 Data flow (one full run)

```
generate.py main()
    │
    ├─ fetch_all()                  # fetcher.py
    │    │
    │    ├─ fetch_all_rss()         # parallel via ThreadPoolExecutor(max_workers=8)
    │    │    └─ For each RSS entry from KTN:
    │    │         ├─ detect which newsletter sent it (author email / title heuristics)
    │    │         ├─ strip HTML, feed text to Mistral
    │    │         ├─ Mistral returns JSON array of {title, summary}
    │    │         └─ insert into articles table with URL "{link}#story-{i}"
    │    │
    │    └─ fetch_all_api()         # currently empty (API_SOURCES = [])
    │
    ├─ categorize_articles(today)   # categorizer.py
    │    │
    │    ├─ Route "Every" articles → editorial category (no LLM call)
    │    ├─ Batch remaining articles (≤ 80 per call) to Mistral
    │    └─ Mistral returns JSON array of {category, headline, summary, article_ids}
    │         → insert into stories table + story_articles junction
    │
    ├─ scrape_ktn_full_text()       # scrape_ktn_stories.py
    │    │
    │    └─ For each KTN URL:
    │         ├─ fetch the newsletter HTML once
    │         ├─ parse into paragraph blocks, drop boilerplate
    │         ├─ keyword-match each article title to its best block
    │         └─ update articles.full_text
    │
    └─ generate_html(stories, today)
         ├─ serialize stories to JSON
         ├─ read static/index.html
         ├─ replace `loadData();` call with embedded `ALL = {...}; CATS = [...]; render();`
         └─ write digest.html
```

### 4.2 Module reference

| File | Purpose | Key functions | Notes |
|------|---------|---------------|-------|
| `generate.py` | Pipeline orchestrator | `main()`, `generate_html()` | `--no-fetch` skips first three stages. Hard-fails if < 5 stories in DB (avoids publishing empty digest). |
| `fetcher.py` | RSS ingestion + LLM extraction | `fetch_all()`, `fetch_one_source()`, `extract_stories_from_newsletter()` | Newsletter detection by `author_email`/Beehiiv bounce ID. Unique URLs synthesized as `{link}#story-{i}` so each story gets its own row. |
| `categorizer.py` | Cross-newsletter dedup + 8-category tagging | `categorize_articles()`, `build_prompt()` | `temperature=0.2`, `max_tokens=4000`, 3-retry exponential backoff. "Every" → always editorial, no LLM. |
| `scrape_ktn_stories.py` | Recover newsletter prose | `run_pipeline()`, `match_article_to_block()` | Exclusive matching: each paragraph block can only back one article (prevents cross-story contamination). |
| `scrape_full_text.py` | Generic article-body scraper | `process_article()` | Uses trafilatura. Not in the main pipeline anymore — kept for backfills. |
| `database.py` | SQLite layer | `init_db()`, `insert_article()`, `get_all_stories()`, etc. | `init_db()` runs on import. Uses WAL mode. Idempotent migrations for `full_text` column via `ALTER TABLE ... IF NOT EXISTS`-by-try/except. |
| `sources.py` | Config | `RSS_SOURCES`, `API_SOURCES`, `CATEGORIES` | KTN URL built from `KTN_FEED_ID` env var. |
| `serve.py` | Flask dev server | `/api/stories`, `/api/fetch`, `/` | For local dev against live DB. Not deployed. Production is 100% static. |
| `scheduler.py` | APScheduler cron | `run_digest()` | Alternative to GitHub Actions for local 24/7 boxes. 07:30 + 18:30 Europe/Paris. |
| `scrape_archives.py` | One-shot Beehiiv backfill | `main()` | Run once to import historical posts. Don't re-run in normal operation. |
| `clean_ai_valley.py` | One-shot data repair | `clean_snippet()` | Already applied to 106 old AI Valley rows. Keep for reference. |

### 4.3 LLM usage — what costs tokens

Two Mistral calls per pipeline run (per newsletter entry, per day):

1. **Extraction** (`fetcher.py`) — one call per newsletter email. Input ≤ 6000 chars. Output: JSON array of stories.
2. **Categorization** (`categorizer.py`) — one call per 80-article batch. Output: array of merged stories.

Model: `mistral-small-latest` (free tier available). Total cost per daily run: pennies.

`--no-fetch` mode consumes zero tokens — useful for frontend iteration.

---

## 5. Database (SQLite)

### 5.1 Schema

```sql
articles                              stories
┌─────────────────────────┐          ┌─────────────────────────┐
│ id INTEGER PK           │          │ id INTEGER PK           │
│ title TEXT              │          │ date TEXT               │
│ url TEXT UNIQUE         │   M:N    │ category TEXT           │
│ source_name TEXT        │◄────────▶│ headline TEXT           │
│ published_at TIMESTAMP  │          │ summary TEXT            │
│ fetched_at TIMESTAMP    │          │ created_at TIMESTAMP    │
│ summary TEXT            │          └─────────────────────────┘
│ content_snippet TEXT    │
│ full_text TEXT          │          story_articles (junction)
│ full_text_fetched_at TS │          ┌─────────────────────────┐
│ language TEXT           │          │ story_id FK             │
└─────────────────────────┘          │ article_id FK           │
                                     │ PRIMARY KEY (both)      │
                                     └─────────────────────────┘

Indexes: idx_articles_published, idx_articles_url, idx_stories_date_category
```

**Note on UNIQUE:** only `articles.url` is UNIQUE. `title` is not. That's how LLM-extracted stories with near-identical titles but distinct `#story-N` fragments coexist.

### 5.2 Content-priority chain (used on the frontend detail view)

```
full_text  (scraped newsletter prose — richest)
    └─ fallback ─▶ content_snippet  (LLM per-story extract)
                        └─ fallback ─▶ story.summary  (LLM aggregate — last resort)
```

Frontend picks the longest `full_text` among the story's articles if ≥ 100 chars, else concatenates unique `content_snippet`s, else uses story-level summary. Logic is in `static/index.html:2122-2150` inside `openArt()`.

### 5.3 Migration pattern

`init_db()` runs on every import and is idempotent. New columns are added via `try/except sqlite3.OperationalError`:

```python
try:
    conn.execute("ALTER TABLE articles ADD COLUMN full_text TEXT")
except sqlite3.OperationalError:
    pass  # already exists
```

To add a new column: add a `try/except` block to `init_db()`. Don't write separate migration files.

---

## 6. Frontend (`static/index.html` / `digest.html`)

### 6.1 File anatomy

Single ~2500-line file. Rough breakdown:

| Lines | Section |
|-------|---------|
| 1–8 | `<head>`, Google Fonts preconnect |
| 9–951 | All CSS (one `<style>` block) |
| 953–1078 | HTML body (app shell, views, nav) |
| 1080–1085 | Vercel Analytics + Speed Insights (ES module import from esm.sh) |
| 1086–1217 | `Ripple` module — Canvas ripple engine (IIFE) |
| 1219–1267 | Global state + helpers (`ALL`, `CATS`, `fs`, `rs`, `esc`, `hi`, date predicates) |
| 1268–1338 | Search scoring (`scoreStory`) + filter (`flt`) |
| 1340–1397 | Story Echoes (`extractKeywords`, `findEchoes`) |
| 1399–1453 | Timeline sparkline |
| 1455–1495 | Personalization (affinity matrix) + search history |
| 1497–1623 | Feed render (`renderHeader`, `renderStack`) |
| 1625–1727 | Swipe engine (`setupSwipe`) |
| 1729–1775 | Saved view render |
| 1777–1796 | Zen reading mode |
| 1798–1897 | Breadcrumb + Knowledge Graph |
| 1899–1960 | Graph init + physics loop |
| 1962–2033 | Export Briefing (.md download via Blob) |
| 2035–2091 | Navigation helpers (echo, breadcrumb, back) |
| 2093–2277 | Detail view (`openArt`, `closeArt`, `go`) |
| 2279–2388 | Search panel render |
| 2390–2451 | Actions (fav, follow, copy) + keyboard |
| 2453–2485 | `loadData()` — only used in serve.py dev mode; overwritten by `generate.py` |

### 6.2 The four views

| View | Element ID | Layout |
|------|-----------|--------|
| Feed | `body-feed` | Tinder-style card stack with 5-layer depth stagger and scrubbable slider. |
| Search | overlays header | Modal bar + keyword highlighting + 30-day timeline sparkline + drill-down by day. |
| Graph | `body-graph` | Full-screen `<canvas>` running a force-directed physics loop (35 top entities). |
| Saved | `body-saved` | Bento-lite list of bookmarked stories + `.md` export button. |

### 6.3 State & persistence

All client-side. No backend in production. Persisted in `localStorage`:

| Key | Type | Purpose |
|-----|------|---------|
| `ai_read` | Set&lt;string&gt; | Story IDs that have been opened (dims card). |
| `ai_fav` | Set&lt;string&gt; | Bookmarked story IDs. |
| `ai_follows` | string[] | Followed source names. |
| `ai_searches` | string[] | Last 8 search queries. |
| `ai_hint` | '1' | Flag: "swipe to browse" hint shown once. |
| `node_zen` | '0' / '1' / '2' | Zen reading mode level. |
| `node_affinity` | `{keyword: score, _cat:<id>: score}` | Personalization matrix. |

### 6.4 Personalization (zero-ML)

Keywords and categories accumulate weight when the user:
- Bookmarks a story → **+1** per extracted keyword, +1 for category.
- Searches for a term → **+0.5** per term after ≥ 3 chars.

`affinityScore(story, aff)` sums matching weights. Used two ways:
- **Feed**: within each date group, stories are sorted by affinity (chronological primary order preserved).
- **Search**: affinity score adds up to **+4** to relevance ranking.

All in `static/index.html:1455-1495` + applied in `flt()` at L1300.

### 6.5 Search — how scoring works

```
scoreStory(x, q):
  headline hit  : +10
  full_text hit : +5   (only first article that matches)
  summary hit   : +3
  snippet hit   : +2   (only first article that matches)
  +3 if today, +1 if this week
  +min(2, articles.length - 1)   # cross-newsletter coverage
  +affinity*0.5, capped at +4
```

Timeline sparkline is built from all-search-results (before drill-down filter). Clicking a bar filters results to that day; clicking the same bar again clears it.

### 6.6 Story Echoes — how relatedness works

For the open story, extract up to 8 proper-noun keywords (via regex + stopword filter at `ECHO_STOP`). Score every other story:

```
scoreEcho:
  keyword overlap × 5
  same category   +2
  ≤ 3 days apart  +3
  ≤ 7 days apart  +1
  candidate's own cross-coverage, up to +2
```

Threshold: `ECHO_MIN_SCORE = 10`. Top 6 shown. Clicking an echo pushes the current article onto `historyStack` and opens the target; breadcrumb shows the depth badge. **Escape key backs up one rung; pressing Escape at root closes.**

---

## 7. UI/UX design system

### 7.1 Visual language

**Editorial, not dashboard.** No emoji icons in the UI, no playful gradients, no skeuomorphic shadows. The aesthetic is magazine + terminal, with a warm amber accent used sparingly.

| Element | Treatment |
|---------|-----------|
| Background | Near-black (`#0D0D0D`) |
| Cards | Three pastel tints rotating (`cream #FFF2C5` / `peach #FFE8E5` / `ice #E0F1FF`) at **0.82 opacity** — that's the golden point between "solid card" and "frosted glass halo." |
| Glow | Each tint has a matching `--glow-*` RGB triple used in `box-shadow` (big spread, low alpha). |
| Accent | **Amber `#F59E0B`** — used only for bookmarks, active states, highlights, selected sparkline bars. Never for body text or borders. |
| Stack depth | 5 behind cards peeking at the bottom, each offset by `i*8px` top, `-i*7px` bottom, `0.12` opacity drop per layer. |

### 7.2 Typography

| Font | Weight | Used for |
|------|--------|----------|
| **Outfit** (var 400–900) | 500–800 | All UI copy, body, pills, navigation. |
| **Fraunces** (var, display) | 700–900 | Section headlines (`.saved-h`, `.graph-title`), drop caps, zen toggle. |

Drop cap: first letter of the first `<p>` in `.art-text` at `3em`, `font-weight:800`, Fraunces. Scales with zen level (2.8em at zen-md, 2.6em at zen-lg).

### 7.3 Motion

- **Easing**: `--ease-quintic: cubic-bezier(0.23, 1, 0.32, 1)` — used for almost every non-linear transition.
- **Swipe**: finger follows exactly during drag; on release, card flies 500px with 18° rotation then unmounts (320ms).
- **Bookmark**: `bk-pop` (scale 1 → 1.32 → 0.93 → 1 in 500ms) + `bk-glow` (expanding ring, 700ms). Force-reflow trick (`void btn.offsetWidth`) to re-trigger animation on rapid toggles.
- **Breadcrumb**: slides in from `-6px` top in 350ms.
- **Detail modal**: slides up from `110vh` in 400ms.

### 7.4 Ripple engine (`static/index.html:1086-1217`)

Canvas 2D, full-viewport, `mix-blend-mode: screen` so canvas pixels *add* brightness to whatever's underneath (NOT opacity — actual light).

On each swipe:
- **Morandi baseline** — 5 desaturated radial blobs drawn on every frame.
- **Ripple spawn** — throttled to one per ~80ms, requires velocity ≥ 0.1px/ms. Size/alpha/life are proportional to velocity; stretch factor elongates along the motion vector.
- Hot white core + colored outer bloom (color inherited from the active card tint: `c-cream` / `c-peach` / `c-ice`).

**Critical quirk**: `.stack-top` does NOT use `backdrop-filter`. Adding it creates an isolation group that breaks `mix-blend-mode: screen` on the canvas sibling. Instead, the parent `.stack-area` has `filter: saturate(1.08) brightness(1.02)` to compensate for the lost saturation.

### 7.5 Knowledge graph physics (`static/index.html:1804-1960`)

- **Nodes**: top 35 keywords by frequency (proper nouns extracted via regex).
- **Edges**: co-occurrences with weight ≥ 2.
- **Forces**: Coulomb repulsion `1400/d²` between every pair; Hooke spring `(d - 90) × 0.007 × weight` along edges; radial gravity `0.004 × (center - position)`.
- **Damping**: `0.86` per tick.
- **Bounds**: clamped to `[35, W-35] × [35, H-35]`.

Drag = move a node; click (drag < 5px) = jump to search with that keyword as query.

### 7.6 Layout invariants

- **App max-width: 430px** (iPhone-class). On wider viewports the app sits centered with 28px rounded corners.
- **Safe-area**: `.stack-area` has `padding-bottom: 96px` to clear the floating nav pill.
- **Stack lift**: `.stack { transform: translateY(-30px) }` lifts the pile so background cards don't collide with the slider below.

---

## 8. Infrastructure

### 8.1 Deployment (Vercel)

- **Trigger**: every push to `main`. GitHub Actions pushes `digest.html` twice daily, each push triggers a Vercel deploy.
- **Build**: none — Vercel serves static files. `vercel.json` rewrites `/` to `/digest.html`.
- **Runtime deps on the frontend**: Google Fonts, esm.sh (Vercel Analytics + Speed Insights), Google Favicon API. No npm install in production.

> **Note on the session-start Vercel hints**: the guidance about `vercel.ts`, Fluid Compute, Next.js, AI SDK, etc. does not apply to this repo. This is a plain static-HTML site with a single `vercel.json` rewrite. No Next.js, no serverless functions. Only touch Vercel config if changing domain or adding a route rewrite.

### 8.2 CI/CD (GitHub Actions, `.github/workflows/update.yml`)

Runs at **06:00 UTC and 16:00 UTC** daily plus manual dispatch. Steps:

1. `actions/checkout@v4`
2. `actions/setup-python@v5` (Python 3.13)
3. `pip install -r requirements.txt`
4. `actions/cache/restore@v4` — restore `news.db` keyed by `news-db-${{ github.run_id }}` with `restore-keys: news-db-` (prefix match — pulls the most recent prior cache).
5. `python generate.py` — runs the full pipeline with `MISTRAL_API_KEY` and `KTN_FEED_ID` from secrets.
6. WAL checkpoint: `PRAGMA wal_checkpoint(TRUNCATE)` — consolidates WAL before caching.
7. `actions/cache/save@v4` — save updated `news.db` with the same unique key.
8. `git add digest.html` + commit (only the HTML ever gets pushed). Skip commit if no diff.

**Required GitHub repository secrets**:
- `MISTRAL_API_KEY`
- `KTN_FEED_ID`

### 8.3 Why `actions/cache` instead of `git push news.db`

- Privacy: news.db contains a rolling local data set, not public content.
- Diff noise: binary DB files blow up git history.
- The cache key uses `run_id` (always unique, so writes never collide) with `restore-keys: news-db-` (prefix match picks the latest previous cache on read).

### 8.4 Local development

```bash
# Copy & fill secrets
cp .env.example .env
# Edit .env: KTN_FEED_ID=..., MISTRAL_API_KEY=...

# Install deps
pip install -r requirements.txt

# Option A: one-shot pipeline (this is what CI runs)
python generate.py              # full run
python generate.py --no-fetch   # regenerate HTML from existing DB (no API calls)

# Option B: live dev server (API-backed frontend)
python serve.py                 # Flask on localhost:8080, hits /api/stories
# Auto-fetches on startup in a background thread.

# Option C: scheduled local daemon
python scheduler.py             # APScheduler: 07:30 + 18:30 Europe/Paris
```

`serve.py` and `scheduler.py` are convenience tools only. They're **not** part of the deployed system. Don't add production features to them.

---

## 9. Critical architectural invariants

Things that look weird but are weird for a reason. **Break these at your peril.**

| Invariant | Why |
|-----------|-----|
| `.stack-top` has no `backdrop-filter` | It would create an isolation group that kills `mix-blend-mode: screen` on the ripple canvas. |
| Per-story URLs are synthesized as `{link}#story-{i}` | `articles.url` is UNIQUE. Multiple stories extracted from the same newsletter email must each have a distinct URL row. |
| `init_db()` runs on import | `--no-fetch` empty-DB guard in `generate.py` checks `get_all_stories(limit=1) == []` **after** import. Checking file existence wouldn't work because the import would already create the file. |
| Exclusive block matching in KTN scraper | Prior version allowed merging adjacent paragraphs, which caused cross-story contamination (next story's opening paragraph bled into the wrong article's `full_text`). |
| `digest.html` is tracked in git, `news.db` is not | `digest.html` IS the product (public). `news.db` is process (private working state). Don't track `news.db` even if "it'd be simpler." |
| Story count floor of 5 | CI aborts if DB has < 5 stories. Prevents publishing an empty digest on a bad run. |
| Frontend has zero build step | Adding a bundler means adding CI build time, cache invalidation concerns, and runtime complexity for a project this size. Stay vanilla unless there's a concrete reason. |

---

## 10. Common tasks

### Add a new newsletter source

1. Subscribe to it using the same Kill-the-Newsletter email.
2. Add a detection branch in `fetcher.py:fetch_one_source()` around L200 (author email or title heuristic).
3. Add its name to the `sources.py` source description.
4. Mention it in `categorizer.py:build_prompt()` so the LLM knows how many newsletters to merge.

### Add a new category

1. Append to `CATEGORIES` in `sources.py`.
2. Add a color entry in `generate.py:CAT_COLORS`.
3. Add a matching entry in `serve.py:CAT_STYLES` (`color`, `glow`, `grad`) if you care about dev-server styling.
4. No frontend change needed — views are data-driven from `CAT_MAP`.

### Change the schedule

`.github/workflows/update.yml` lines 4–6. Use cron syntax. Remember the runner is UTC.

### Modify the frontend without re-fetching

```bash
python generate.py --no-fetch
```

Regenerates `digest.html` from the existing local DB. No Mistral calls, no HTTP.

### Debug a specific story's content priority

In the browser console after loading:
```js
ALL.find(s => s.headline.includes('partial title'))
```

Look at `articles[*].full_text` vs `content_snippet` vs `summary` to understand which branch of the priority chain is picked.

---

## 11. Known limitations & open roadmap

### 11.1 What's working well

- Pipeline is robust and cheap (cents/run).
- Frontend has rich interaction (swipe, search, graph, export) with no performance regressions.
- Deploy story is clean (GitHub Actions → static file → Vercel).

### 11.2 Rough edges

- **No mobile-first testing on iOS Safari recently.** Swipe + ripple work, but rubber-band scroll interactions on very long `art-text` could use a look.
- **Knowledge graph is desktop-first.** Touch-drag works but hover fallback is awkward on phones.
- **Search is substring-only.** No stemming, no synonym handling. Searching "GPTs" won't match "GPT-5." Consider adding a light synonym map if this becomes a pain point.
- **Category assignments sometimes disagree with human judgement** — Mistral decides, and it's not always right. `Every` is hard-coded to `editorial` to avoid this class of error. Consider a post-hoc rule list for other common misclassifications.
- **`full_text` recovery depends on KTN retaining the email.** KTN purges old entries (HTTP 404). The scraper handles this gracefully (`expired` stat) but older archive stories progressively lose their richer prose.
- **No test suite.** Manual verification happens via `python generate.py --no-fetch` + eyeballing `digest.html`. Before adding tests, decide if the investment is worth it given how small the surface area is.

### 11.3 Roadmap (user-prioritized as of 2026-04-12)

| # | Feature | Status | Notes |
|---|---------|--------|-------|
| 1 | Automation closed-loop | **Done** | GitHub Actions cron + Vercel auto-deploy. |
| 2 | Export saved stories as Markdown | **Done** | `exportBriefing()` in `index.html:1962`. |
| 3 | Knowledge graph visualization | **Done** | Force-directed 35-entity canvas. |
| 4 | Personalized Gravity (zero-ML affinity) | **Done** | `node_affinity` localStorage matrix. |
| 5 | Zen Reading Mode (3 font scales) | **Done** | `Aa` toggle in detail view. |

All 5 initial roadmap items have shipped. Phase 2 is open — suggested directions:

- **Full-text search v2**: incorporate stemming / fuzzy matching (e.g. a small FlexSearch bundle) without breaking the zero-build constraint.
- **Trending detection**: surface stories whose keywords are accelerating week-over-week.
- **Cross-day threading**: link today's story on OpenAI to yesterday's if they share entities ≥ N.
- **Saved-story annotations**: let the user add a short note per bookmark; persist in localStorage and include in export.
- **Share view**: generate a read-only public URL for a single story (requires opting into a tiny serverless function — breaks the "100% static" invariant, think carefully).

---

## 12. Things to NOT do (lessons baked in)

1. **Don't add `backdrop-filter` to `.stack-top`.** It breaks the ripple canvas' `mix-blend-mode: screen`. Use `filter: saturate()` on the parent to compensate.
2. **Don't commit `news.db`.** If you need to reset the DB in CI, invalidate the cache key rather than tracking the file.
3. **Don't use `--no-fetch` on a fresh checkout.** The DB is gitignored; you need at least one full run first. `generate.py` will now abort explicitly if this happens.
4. **Don't ship the dev server.** `serve.py` is for local iteration only. Production is 100% static.
5. **Don't introduce a build step without a real reason.** Vanilla JS + one HTML file is a feature, not a limitation.
6. **Don't amend auto-commits from GitHub Actions.** The commit history is append-only; `git push --force` on `main` would confuse Vercel's deployment dedup.
7. **Don't merge cross-story paragraphs in the KTN scraper.** Previous attempts to include the next paragraph caused topic contamination. Stick with single-block matches.
8. **Don't skip the LLM story-count floor.** An empty digest looks broken and tells you nothing about what went wrong upstream. The `MIN_STORIES = 5` guard in `generate.py` is load-bearing.

---

## 13. Quick reference — where things live

| I want to change... | Edit this |
|----------------------|-----------|
| Newsletter detection logic | `fetcher.py:193-216` |
| LLM categorization prompt | `categorizer.py:build_prompt` |
| KTN content-block scoring | `scrape_ktn_stories.py:match_article_to_block` |
| Category list | `sources.py:CATEGORIES` + `generate.py:CAT_COLORS` |
| App colors / tints / glow | `static/index.html:11-27` (CSS vars) |
| Card stack visual layout | `static/index.html:1533-1546` (`renderStack`) |
| Swipe thresholds / fling | `static/index.html:1682-1704` |
| Ripple params (life, size, elongation) | `static/index.html:1189-1204` (`spawnRipple`) |
| Search scoring weights | `static/index.html:1279-1298` (`scoreStory`) |
| Echo scoring weights | `static/index.html:1368-1385` (`scoreEcho`) |
| Knowledge graph forces | `static/index.html:1833-1864` (`tickGraph`) |
| Personalization weights | `static/index.html:1455-1495` |
| Markdown export format | `static/index.html:1962-2033` (`exportBriefing`) |
| CI schedule | `.github/workflows/update.yml:4-6` |
| Vercel routing | `vercel.json` |

---

## 14. Contact & conventions

- **License**: ISC.
- **Branch model**: `main` only. Feature work lives on short-lived branches merged back. Auto-commits from Actions always target `main`.
- **Commit style**: imperative (`fix:`, `docs:`, `rewrite ...`, `auto: refresh digest ...`).
- **README style**: progressive disclosure, ASCII diagrams, tables over paragraphs. See `README.md`.

Welcome aboard. Read `README.md` next for the public-facing pitch, then try `python generate.py` to watch the pipeline run end-to-end. When in doubt, the code is the source of truth — this doc is derived from it, not the other way around.
