"""
config.py — All environment variables, timeouts, and tunable constants.
Invariant: No magic numbers in scrapers or agents; they import from here. Must never
hardcode API keys or timeouts elsewhere.
"""

import os
from pathlib import Path

_env_path = Path(__file__).resolve().parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(_env_path)
except ImportError:
    pass

# Fallback: manual parse if dotenv didn't load
if _env_path.exists():
    with open(_env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                v = v.strip().strip('"').strip("'").replace("\r", "").replace("\n", "").strip()
                os.environ[k.strip()] = v

# --- Timeouts (seconds) ---
API_TIMEOUT_SECONDS = 10
PIPELINE_MAX_SECONDS = 20

# --- Reddit (PRAW) ---
REDDIT_CLIENT_ID = os.environ.get("REDDIT_CLIENT_ID", "")
REDDIT_CLIENT_SECRET = os.environ.get("REDDIT_CLIENT_SECRET", "")
REDDIT_USER_AGENT = os.environ.get("REDDIT_USER_AGENT", "PaperTrail/1.0")

# --- Bluesky (atproto) ---
# Search may require auth per docs.bsky.app/docs/api/app-bsky-feed-search-posts
BLUESKY_HANDLE = os.environ.get("BLUESKY_HANDLE", "")
BLUESKY_APP_PASSWORD = os.environ.get("BLUESKY_APP_PASSWORD", "")

# --- OpenAI ---
def _clean_key(s: str) -> str:
    """Strip whitespace and Windows CRLF that can cause 401."""
    return (s or "").strip().replace("\r", "").replace("\n", "")

OPENAI_API_KEY = _clean_key(os.environ.get("OPENAI_API_KEY", ""))
OPENAI_EMBEDDING_MODEL = "text-embedding-3-small"
OPENAI_CHAT_MODEL = "gpt-4o-mini"

# --- Scraper limits ---
REDDIT_MAX_POSTS = 50
BLUESKY_MAX_POSTS = 50

# --- Clustering ---
CLUSTER_SIMILARITY_THRESHOLD = 0.82  # Cosine similarity; tune so minor wording stays in same cluster
MAX_CLUSTERS = 20  # Cap to avoid runaway

# --- Backend ---
BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))
