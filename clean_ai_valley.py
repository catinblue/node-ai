"""
Historical-debt cleanup for AI Valley archive entries.

The 106 AI Valley archive articles were scraped long ago with a truncated
500-char content_snippet that starts with a fixed boilerplate:

    > Sign up | Follow us on X | Sponsor Together with Howdy...
    Happy Tuesday, AI family, and welcome to another AI Valley edition.
    Today's climb through the Valley reveals: [actual headlines]

This script strips the boilerplate prefix and writes the cleaned remainder
to full_text, so the detail page (which prefers full_text) shows real
newsletter topic lists with Drop Cap formatting instead of sponsor sludge.

Usage:
    python clean_ai_valley.py                # clean all pending
    python clean_ai_valley.py --dry-run      # preview without writing
"""

import argparse
import re
import sys

from database import get_connection, update_article_full_text


# Pivot phrases — everything before (and including) these markers is boilerplate.
# Ordered by specificity: transition phrases first, fallback to general ones.
PIVOT_PATTERNS = [
    r"here (?:are|is) the biggest things? worth knowing today[:\s]*",
    r"through the Valley reveals[:\s]*",
    r"the biggest things worth knowing[:\s]*",
    r"here(?:'s| is) what'?s worth knowing[:\s]*",
    r"welcome (?:back )?to (?:another )?AI Valley(?:\s+edition)?\.\s*",
]
PIVOT_RE = re.compile("|".join(PIVOT_PATTERNS), re.IGNORECASE)

# Trailing junk to strip from the end
TRAIL_PATTERNS = [
    r"Plus trending AI tools.*$",
    r"Let'?s dive into the Valley.*$",
    r"Let'?s dig in.*$",
]
TRAIL_RE = re.compile("|".join(TRAIL_PATTERNS), re.IGNORECASE | re.DOTALL)

MIN_CLEANED_LENGTH = 60   # reject cleans that leave too little behind


def clean_snippet(snippet):
    """Strip boilerplate prefix and trailing junk from an AI Valley snippet."""
    if not snippet:
        return None

    # Find the last pivot match and take everything after it
    matches = list(PIVOT_RE.finditer(snippet))
    if matches:
        pivot = matches[-1]
        cleaned = snippet[pivot.end():]
    else:
        cleaned = snippet

    # Strip trailing newsletter sponsor/nav sludge
    cleaned = TRAIL_RE.sub("", cleaned).strip()

    # Normalize whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) < MIN_CLEANED_LENGTH:
        return None
    return cleaned


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    conn = get_connection()
    rows = conn.execute(
        """SELECT id, title, content_snippet FROM articles
           WHERE url LIKE '%theaivalley.com/p/%'
             AND (full_text IS NULL OR full_text = '')
             AND content_snippet IS NOT NULL"""
    ).fetchall()
    conn.close()

    if not rows:
        print("No AI Valley archive articles pending cleanup.")
        return 0

    print(f"Cleaning {len(rows)} AI Valley archive entries...")
    print()

    stats = {"cleaned": 0, "rejected": 0, "no_pivot": 0}
    samples = []

    for r in rows:
        original = r["content_snippet"] or ""
        cleaned = clean_snippet(original)

        if cleaned is None:
            stats["rejected"] += 1
            continue

        # Track if pivot was found vs. just trimmed
        if "through the Valley reveals" not in original and "AI Valley edition" not in original:
            stats["no_pivot"] += 1

        if len(samples) < 3:
            samples.append((r["title"], original[:80], cleaned[:120]))

        if not args.dry_run:
            update_article_full_text(r["id"], cleaned)
        stats["cleaned"] += 1

    print(f"  Cleaned: {stats['cleaned']}")
    print(f"  Rejected (too short after strip): {stats['rejected']}")
    print()
    print("Samples:")
    for title, raw, clean in samples:
        safe_title = title[:50].encode("ascii", "replace").decode()
        safe_raw = raw.encode("ascii", "replace").decode()
        safe_clean = clean.encode("ascii", "replace").decode()
        print(f"  * {safe_title}")
        print(f"      BEFORE: {safe_raw}...")
        print(f"      AFTER:  {safe_clean}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
