"""
AI News Sources Configuration

Sources: AlphaSignal, AI Valley, The Neuron, Every
via Kill the Newsletter (email → Atom feed)
"""

# === RSS Feeds ===

import os
from dotenv import load_dotenv
load_dotenv()

_KTN_FEED_ID = os.getenv("KTN_FEED_ID", "")
_KTN_URL = f"https://kill-the-newsletter.com/feeds/{_KTN_FEED_ID}.xml" if _KTN_FEED_ID else ""

RSS_SOURCES = [
    {
        "name": "Newsletters (AlphaSignal + AI Valley + The Neuron + Every)",
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
        "name_zh": "模型发布",
        "emoji": "🚀",
        "description": "New AI model launches, benchmarks, capabilities",
    },
    {
        "id": "products_tools",
        "name_en": "Products & Tools",
        "name_zh": "产品工具",
        "emoji": "🛠️",
        "description": "New AI products, tools, features, updates",
    },
    {
        "id": "industry_business",
        "name_en": "Industry & Business",
        "name_zh": "行业商业",
        "emoji": "📋",
        "description": "AI industry trends, policy, regulation, adoption, opinions",
    },
    {
        "id": "funding_acquisitions",
        "name_en": "Funding & Acquisitions",
        "name_zh": "融资收购",
        "emoji": "💰",
        "description": "AI startup funding, M&A, valuations, IPOs",
    },
    {
        "id": "research",
        "name_en": "Research",
        "name_zh": "研究突破",
        "emoji": "📄",
        "description": "Notable research papers, breakthroughs, new techniques",
    },
    {
        "id": "open_source",
        "name_en": "Open Source",
        "name_zh": "开源项目",
        "emoji": "🔓",
        "description": "Open source AI models, datasets, frameworks, tools",
    },
    {
        "id": "editorial",
        "name_en": "Editorial",
        "name_zh": "深度阅读",
        "emoji": "📖",
        "description": "Long-form editorial articles and deep dives from Every",
    },
    {
        "id": "sci_tech_trends",
        "name_en": "Sci-Tech Trends",
        "name_zh": "科技趋势",
        "emoji": "🔬",
        "description": "Cross-disciplinary science and tech beyond pure AI — chips, quantum, biotech, robotics, hardware, infrastructure",
    },
]
