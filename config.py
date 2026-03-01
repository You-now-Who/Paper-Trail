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
# Search robustness: more queries = better chance of finding related posts
MAX_SEARCH_QUERIES = 10  # Use up to this many keyword phrases per platform
SEARCH_POST_SNIPPET_LEN = 100  # Always search with this many chars of the post as first query

# --- Clustering ---
CLUSTER_SIMILARITY_THRESHOLD = 0.82  # Cosine similarity; tune so minor wording stays in same cluster
MAX_CLUSTERS = 20  # Cap to avoid runaway

# --- Semantic verification (model-based) ---
SEMANTIC_SIMILARITY_THRESHOLD = 0.75  # Claim supported if max cosine(corpus) >= this
CONFIDENCE_LOW_THRESHOLD = 0.4  # Below = "low"
CONFIDENCE_MEDIUM_THRESHOLD = 0.7  # Above = "high"; between = "medium"
MUTATION_LOG_PATH = Path(__file__).resolve().parent / "data" / "mutations.jsonl"

# --- Provenance graph ---
# To use the NEW graph path (not legacy): set MIN_EDGES_TO_USE_GRAPH = 0, MIN_SIGNALS_FOR_EDGE = 1,
# and CONNECTION_SANITY_CHECK_ENABLED = False. Stricter = fewer false links but more legacy fallback.
CORPUS_DAYS_LIMIT = 7  # Only consider posts from the last N days
THETA_RELEVANCE = 0.72  # Min sim(post, current) to keep post (lower = more candidates)
THETA_EDGE = 0.45  # Min evidence score to add edge A -> B
# Multi-signal: require at least N of (quote, ngram, paraphrase) to add edge
MIN_QUOTE_FOR_EDGE = 0.06  # Quote overlap threshold (shared phrases)
MIN_NGRAM_FOR_EDGE = 0.10  # Ngram Jaccard threshold (shared word runs)
MIN_PARAPHRASE_FOR_SIGNAL = 0.68  # Paraphrase (embedding sim) counts as one signal
MIN_SIGNALS_FOR_EDGE = 1  # Require ≥1 signal to add edge (set 2 for stricter)
MAX_PATH_LENGTH = 10
MAX_OUT_EDGES_PER_NODE = 5
# Use new graph path when we have a path of 2+ nodes (set 1 to require at least one edge)
MIN_EDGES_TO_USE_GRAPH = 0  # 0 = use graph whenever main_path has 2+ nodes
# Sanity check: only add edge A→B if it makes sense for B to derive from A (same story/event)
CONNECTION_SANITY_CHECK_ENABLED = False  # Set True for stricter; False to get more graph edges
CONNECTION_SANITY_MAX_CHECKS = 25  # Max LLM calls per graph (top candidates only)

# --- Message propagation (track one message across many nodes) ---
THETA_CARRIES_MESSAGE = 0.55  # Min score (quote+paraphrase vs message) to count node as carrying the message
MESSAGE_EXTRACTION_MAX_CHARS = 500  # Cap post text for message extraction
# Same-message detector: alert when this many or more distinct accounts carry the same message
PROPAGATION_ACCOUNTS_ALERT_THRESHOLD = 3

# --- Backend ---
BACKEND_HOST = os.environ.get("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8000"))
