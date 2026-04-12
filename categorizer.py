"""
Article categorizer + dedup — groups today's articles into stories using Mistral LLM.
"""

import json
import os
import time
from datetime import datetime, timezone

import requests as http_requests
from dotenv import load_dotenv

from sources import CATEGORIES
from database import get_unprocessed_articles, insert_story

load_dotenv()

MISTRAL_API_KEY = os.getenv("MSITRAL_API_KEY")
MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
MODEL = "mistral-small-latest"


def llm_chat(prompt, temperature=0.2, max_tokens=4000):
    """Call Mistral API and return the response text."""
    resp = http_requests.post(MISTRAL_URL,
        headers={"Authorization": f"Bearer {MISTRAL_API_KEY}", "Content-Type": "application/json"},
        json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
              "temperature": temperature, "max_tokens": max_tokens},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]

# Build category list for the prompt
CATEGORY_LIST = "\n".join(
    f'- "{c["id"]}": {c["description"]}' for c in CATEGORIES
)


def build_prompt(articles):
    """Build the LLM prompt from a list of article dicts."""
    articles_text = ""
    for a in articles:
        articles_text += (
            f'[id={a["id"]}] "{a["title"]}"\n'
            f'  source: {a["source_name"]}\n'
            f'  snippet: {(a.get("content_snippet") or "")[:200]}\n\n'
        )

    return f"""You are the editor of a top AI newsletter.
Your job: curate today's raw articles into a sharp daily digest.

The articles come from 4 newsletters: AlphaSignal, The Neuron, AI Valley, and Every.
When MULTIPLE newsletters cover the SAME topic, that's a HOT topic — merge them
into ONE story and include ALL their article IDs. The more newsletters cover a topic,
the higher it should rank.

## Your editorial process:

1. **MERGE aggressively**: If AlphaSignal mentions "Anthropic Claude plans" and The Neuron
   also mentions "Anthropic Claude update", these are the SAME story — merge them into one
   with both article IDs. Look for same company names, same events, same products.

2. **Rank by cross-coverage**: Stories covered by 3-4 newsletters = top priority.
   Stories covered by 2 = high. Stories from only 1 newsletter = normal.

3. **Categorize**: Assign each story to one category.

4. **Write like a newsletter editor**, not a robot:
   - Headlines: specific and punchy (e.g. "Google releases Gemma 4 with Apache 2.0
     license" NOT "New AI Model Releases")
   - Summaries: what happened, why it matters, 2-3 sentences max.

Categories:
{CATEGORY_LIST}

Articles:
{articles_text}

Return ONLY valid JSON — an array of story objects, ordered by importance (most important first):
```json
[
  {{
    "category": "category_id",
    "headline": "Specific, punchy headline (max 100 chars)",
    "summary": "What happened and why it matters. Be specific, not generic. (max 300 chars)",
    "article_ids": [1, 2, 3]
  }}
]
```

Rules:
- Return 8-15 stories maximum. Quality over quantity.
- Drop articles that don't meet the quality bar — NOT every article needs to appear.
- Merge articles about the same event/topic into one story.
- Headlines must name the company/product/person — never write "New AI Model" or "Several companies".
- Summaries must include specific facts — never write "various applications and industries".
- Order the array by importance: the #1 story should be what every AI person is talking about today.
- Return ONLY the JSON array, no markdown fences, no extra text."""


def categorize_articles(date_str):
    """Categorize unprocessed articles for a given date. Returns number of stories created."""
    articles = get_unprocessed_articles(date_str)
    if not articles:
        print(f"No unprocessed articles for {date_str}.")
        return 0

    # Separate Every articles → always "editorial" category
    every_articles = [a for a in articles if a.get("source_name") == "Every"]
    articles = [a for a in articles if a.get("source_name") != "Every"]

    every_count = 0
    for ea in every_articles:
        insert_story(
            date_str=date_str,
            category="editorial",
            headline=ea["title"],
            summary=ea.get("content_snippet") or "",
            article_ids=[ea["id"]],
        )
        every_count += 1
    if every_count:
        print(f"  {every_count} Every editorial(s) added.")

    if not articles:
        return every_count

    print(f"Categorizing {len(articles)} articles for {date_str}...")

    # Groq has token limits — batch if needed (70b model handles ~6000 tokens input)
    MAX_BATCH = 80
    all_stories_count = 0

    for i in range(0, len(articles), MAX_BATCH):
        batch = articles[i:i + MAX_BATCH]
        prompt = build_prompt(batch)

        MAX_RETRIES = 3
        raw = None
        for attempt in range(MAX_RETRIES):
            try:
                raw = llm_chat(prompt, temperature=0.2, max_tokens=4000)
                break
            except Exception as e:
                wait = 2 ** attempt
                print(f"  [RETRY {attempt + 1}/{MAX_RETRIES}] API error: {e} — waiting {wait}s")
                if attempt == MAX_RETRIES - 1:
                    print(f"  [FAIL] Giving up after {MAX_RETRIES} attempts.")
                    return all_stories_count + every_count
                time.sleep(wait)

        raw = raw.strip()

        # Strip markdown fences if the model wraps them anyway
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]
            if raw.endswith("```"):
                raw = raw[:-3]

        try:
            stories = json.loads(raw)
        except json.JSONDecodeError as e:
            print(f"  [FAIL] JSON parse error: {e}")
            print(f"  Raw response: {raw[:500]}")
            return all_stories_count

        # Valid article IDs in this batch
        valid_ids = {a["id"] for a in batch}

        for story in stories:
            aids = [aid for aid in story.get("article_ids", []) if aid in valid_ids]
            if not aids:
                continue
            insert_story(
                date_str=date_str,
                category=story.get("category", "products_tools"),
                headline=story.get("headline", "Untitled"),
                summary=story.get("summary", ""),
                article_ids=aids,
            )
            all_stories_count += 1

        if len(articles) > MAX_BATCH:
            print(f"  Batch {i // MAX_BATCH + 1}: {len(stories)} stories")

    total = all_stories_count + every_count
    print(f"Done — {total} stories created for {date_str}.")
    return total


if __name__ == "__main__":
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    categorize_articles(today)
