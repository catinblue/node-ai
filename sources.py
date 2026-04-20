"""
AI News Sources Configuration

Sources: AlphaSignal, The Neuron, AI Valley, Every, AI Tinkerers
via Kill the Newsletter (email → Atom feed)
"""

# === RSS Feeds ===

import os
from dotenv import load_dotenv
load_dotenv()

_KTN_FEED_ID = os.getenv("KTN_FEED_ID", "")
_KTN_URL = f"https://kill-the-newsletter.com/feeds/{_KTN_FEED_ID}.xml" if _KTN_FEED_ID else ""

# Active newsletter roster — the single source of truth downstream.
# To add a source: append here AND add a detection branch in
# fetcher.fetch_one_source (otherwise the article will be labelled "Unknown").
NEWSLETTER_NAMES = ["AlphaSignal", "The Neuron", "AI Valley", "Every", "AI Tinkerers"]

RSS_SOURCES = [
    {
        "name": f"Newsletters ({' + '.join(NEWSLETTER_NAMES)})",
        "url": _KTN_URL,
        "language": "en",
    },
] if _KTN_URL else []

# === API Sources ===

API_SOURCES = []


# === Topic Categories ===

CATEGORIES = [
    {
        "id": "model_releases",
        "name_en": "Model Releases",
                "emoji": "🚀",
        "description": "New AI model launches, benchmarks, capabilities",
    },
    {
        "id": "products_tools",
        "name_en": "Products & Tools",
                "emoji": "🛠️",
        "description": "New AI products, tools, features, updates",
    },
    {
        "id": "industry_business",
        "name_en": "Industry & Business",
                "emoji": "📋",
        "description": "AI industry trends, policy, regulation, adoption, opinions",
    },
    {
        "id": "funding_acquisitions",
        "name_en": "Funding & Acquisitions",
                "emoji": "💰",
        "description": "AI startup funding, M&A, valuations, IPOs",
    },
    {
        "id": "research",
        "name_en": "Research",
                "emoji": "📄",
        "description": "Notable research papers, breakthroughs, new techniques",
    },
    {
        "id": "open_source",
        "name_en": "Open Source",
                "emoji": "🔓",
        "description": "Open source AI models, datasets, frameworks, tools",
    },
    {
        "id": "editorial",
        "name_en": "Editorial",
                "emoji": "📖",
        "description": "Long-form editorial articles and deep dives from Every",
    },
    {
        "id": "sci_tech_trends",
        "name_en": "Sci-Tech Trends",
                "emoji": "🔬",
        "description": "Cross-disciplinary science and tech beyond pure AI — chips, quantum, biotech, robotics, hardware, infrastructure",
    },
]
