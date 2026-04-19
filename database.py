"""
SQLite database layer for storing and querying news articles.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DB_PATH = Path(__file__).parent / "news.db"


def get_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """Create tables if they don't exist and run idempotent migrations."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            url TEXT UNIQUE NOT NULL,
            source_name TEXT NOT NULL,
            published_at TIMESTAMP,
            fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            summary TEXT,
            content_snippet TEXT,
            language TEXT DEFAULT 'en'
        );

        CREATE TABLE IF NOT EXISTS stories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            headline TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS story_articles (
            story_id INTEGER REFERENCES stories(id),
            article_id INTEGER REFERENCES articles(id),
            PRIMARY KEY (story_id, article_id)
        );

        CREATE INDEX IF NOT EXISTS idx_articles_published
            ON articles(published_at);
        CREATE INDEX IF NOT EXISTS idx_articles_url
            ON articles(url);
        CREATE INDEX IF NOT EXISTS idx_stories_date_category
            ON stories(date, category);
    """)
    # Migration: add full_text column if missing (Slice C — original content)
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN full_text TEXT")
    except sqlite3.OperationalError:
        pass  # Column already exists
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN full_text_fetched_at TIMESTAMP")
    except sqlite3.OperationalError:
        pass
    # Migration: terminal status so we never retry dead URLs (KTN 404 etc.)
    # Values: NULL = pending, 'ok' = have content, 'expired' = KTN gone,
    #         'no_download' | 'no_extract' | 'too_short' | 'error' = terminal failure
    try:
        conn.execute("ALTER TABLE articles ADD COLUMN full_text_status TEXT")
    except sqlite3.OperationalError:
        pass
    conn.commit()
    conn.close()


def insert_article(title, url, source_name, published_at=None,
                    summary=None, content_snippet=None, language="en"):
    """Insert an article, skip if URL already exists. Returns True if inserted."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO articles
               (title, url, source_name, published_at, summary, content_snippet, language)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (title, url, source_name, published_at, summary, content_snippet, language),
        )
        conn.commit()
        return cursor.rowcount > 0
    finally:
        conn.close()


def get_articles_for_date(date_str):
    """Get all articles for a given date (YYYY-MM-DD)."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT * FROM articles
           WHERE date(published_at) = ?
           ORDER BY published_at DESC""",
        (date_str,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_unprocessed_articles(date_str):
    """Get articles from the last 48h that haven't been assigned to a story yet."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT a.* FROM articles a
           LEFT JOIN story_articles sa ON a.id = sa.article_id
           WHERE date(a.published_at) BETWEEN date(?, '-1 day') AND date(?, '+1 day')
             AND sa.story_id IS NULL
           ORDER BY a.published_at DESC""",
        (date_str, date_str),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def insert_story(date_str, category, headline, summary, article_ids):
    """Insert a story and link it to its source articles."""
    conn = get_connection()
    cursor = conn.execute(
        """INSERT INTO stories (date, category, headline, summary)
           VALUES (?, ?, ?, ?)""",
        (date_str, category, headline, summary),
    )
    story_id = cursor.lastrowid
    for aid in article_ids:
        conn.execute(
            "INSERT OR IGNORE INTO story_articles (story_id, article_id) VALUES (?, ?)",
            (story_id, aid),
        )
    conn.commit()
    conn.close()
    return story_id


def get_stories_for_date(date_str):
    """Get all stories for a date with their articles in a single query."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.id AS story_id, s.date, s.category, s.headline,
                  s.summary AS story_summary, s.created_at AS story_created_at,
                  a.id AS article_id, a.title, a.url, a.source_name,
                  a.published_at, a.fetched_at, a.summary AS article_summary,
                  a.content_snippet, a.language
           FROM stories s
           LEFT JOIN story_articles sa ON s.id = sa.story_id
           LEFT JOIN articles a ON sa.article_id = a.id
           WHERE s.date = ?
           ORDER BY s.category, s.id""",
        (date_str,),
    ).fetchall()
    conn.close()

    stories_map = {}
    for r in rows:
        r = dict(r)
        sid = r["story_id"]
        if sid not in stories_map:
            stories_map[sid] = {
                "id": sid,
                "date": r["date"],
                "category": r["category"],
                "headline": r["headline"],
                "summary": r["story_summary"],
                "created_at": r["story_created_at"],
                "articles": [],
            }
        if r["article_id"] is not None:
            stories_map[sid]["articles"].append({
                "id": r["article_id"],
                "title": r["title"],
                "url": r["url"],
                "source_name": r["source_name"],
                "published_at": r["published_at"],
                "fetched_at": r["fetched_at"],
                "summary": r["article_summary"],
                "content_snippet": r["content_snippet"],
                "language": r["language"],
            })

    return list(stories_map.values())


def get_all_stories(limit=200):
    """Get all stories with their articles, most recent first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT s.id AS story_id, s.date, s.category, s.headline,
                  s.summary AS story_summary, s.created_at AS story_created_at,
                  a.id AS article_id, a.title, a.url, a.source_name,
                  a.published_at, a.fetched_at, a.summary AS article_summary,
                  a.content_snippet, a.language, a.full_text
           FROM stories s
           LEFT JOIN story_articles sa ON s.id = sa.story_id
           LEFT JOIN articles a ON sa.article_id = a.id
           ORDER BY s.date DESC, s.id""",
    ).fetchall()
    conn.close()

    stories_map = {}
    for r in rows:
        r = dict(r)
        sid = r["story_id"]
        if sid not in stories_map:
            stories_map[sid] = {
                "id": sid,
                "date": r["date"],
                "category": r["category"],
                "headline": r["headline"],
                "summary": r["story_summary"],
                "created_at": r["story_created_at"],
                "articles": [],
            }
        if r["article_id"] is not None:
            stories_map[sid]["articles"].append({
                "id": r["article_id"],
                "title": r["title"],
                "url": r["url"],
                "source_name": r["source_name"],
                "published_at": r["published_at"],
                "summary": r.get("article_summary"),
                "content_snippet": r.get("content_snippet"),
                "full_text": r.get("full_text"),
            })

    result = list(stories_map.values())
    return result[:limit]


def update_article_full_text(article_id, full_text):
    """Persist scraped full text for an article and mark its status as 'ok'."""
    conn = get_connection()
    conn.execute(
        """UPDATE articles
           SET full_text = ?, full_text_fetched_at = CURRENT_TIMESTAMP,
               full_text_status = 'ok'
           WHERE id = ?""",
        (full_text, article_id),
    )
    conn.commit()
    conn.close()


def mark_full_text_status(article_ids, status):
    """Mark a batch of articles with a terminal full_text status so subsequent
    pipeline runs don't re-attempt them. Allowed values:
      'expired'     — KTN source is gone (404)
      'no_download' — downloader returned empty
      'no_extract'  — extractor returned nothing
      'too_short'   — content shorter than MIN_BODY_LENGTH
      'error'       — any other exception
    Selective retry: clear the status (UPDATE ... SET full_text_status = NULL
    WHERE full_text_status = '...') to re-enqueue a specific class."""
    ids = list(article_ids)
    if not ids:
        return
    conn = get_connection()
    placeholders = ",".join("?" for _ in ids)
    conn.execute(
        f"UPDATE articles SET full_text_status = ?, full_text_fetched_at = CURRENT_TIMESTAMP "
        f"WHERE id IN ({placeholders})",
        (status, *ids),
    )
    conn.commit()
    conn.close()


def get_articles_needing_full_text(limit=None, since_days=14):
    """
    Return articles published in the last `since_days` that are linked to a story
    (so we only scrape articles that actually appear in the digest) and don't yet
    have full_text AND haven't been marked as a terminal failure.
    """
    conn = get_connection()
    sql = """
        SELECT DISTINCT a.id, a.url, a.source_name, a.title
        FROM articles a
        INNER JOIN story_articles sa ON a.id = sa.article_id
        WHERE (a.full_text IS NULL OR a.full_text = '')
          AND a.full_text_status IS NULL
          AND a.url IS NOT NULL AND a.url != ''
          AND date(a.published_at) >= date('now', ?)
        ORDER BY a.published_at DESC
    """
    params = [f"-{int(since_days)} days"]
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_available_dates(limit=30):
    """Get dates that have stories, most recent first."""
    conn = get_connection()
    rows = conn.execute(
        """SELECT DISTINCT date FROM stories
           ORDER BY date DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [r["date"] for r in rows]


# Initialize DB on import
init_db()
