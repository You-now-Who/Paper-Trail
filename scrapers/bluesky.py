"""
scrapers/bluesky.py — Bluesky search agent only. Fetches related posts via atproto.
Invariant: Returns list[RawPost]; does not cluster or analyze. Excludes source post URL.
Must never throw uncaught; failures log and return empty list.
Uses sync Client with login per docs.bsky.app — search may require auth.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from schemas import RawPost
from config import (
    BLUESKY_MAX_POSTS,
    API_TIMEOUT_SECONDS,
    BLUESKY_HANDLE,
    BLUESKY_APP_PASSWORD,
    MAX_SEARCH_QUERIES,
)

logger = logging.getLogger(__name__)


def _parse_timestamp(record: object) -> str:
    """Get ISO timestamp from atproto record."""
    created = getattr(record, "createdAt", None) or getattr(record, "created_at", None)
    if hasattr(record, "get") and callable(getattr(record, "get")):
        created = created or record.get("createdAt") or record.get("created_at")
    if created:
        try:
            s = str(created)
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.isoformat()
        except Exception:
            pass
    return datetime.now(timezone.utc).isoformat()


def _post_text(record: object) -> str:
    """Extract text from post record (PostView has .record.text)."""
    val = getattr(record, "text", None)
    if val is None and hasattr(record, "get") and callable(getattr(record, "get")):
        val = record.get("text", "")
        if val is None:
            v = record.get("value")
            val = v.get("text", "") if isinstance(v, dict) else ""
    if isinstance(val, str):
        return val[:2000].strip()
    return ""


def _search_sync(keywords: list[str], exclude_url: str) -> list[RawPost]:
    """
    Sync search using atproto Client with login.
    Per docs.bsky.app: search may require auth.
    """
    try:
        from atproto import Client
    except ImportError:
        logger.warning("atproto not installed; skipping Bluesky search")
        return []

    if not BLUESKY_HANDLE or not BLUESKY_APP_PASSWORD:
        logger.warning("BLUESKY_HANDLE and BLUESKY_APP_PASSWORD required; set in .env")
        return []

    seen_urls: set[str] = set()
    if exclude_url:
        seen_urls.add(exclude_url)
    posts: list[RawPost] = []

    try:
        client = Client()
        client.login(BLUESKY_HANDLE, BLUESKY_APP_PASSWORD)
    except Exception as e:
        logger.warning("Bluesky login failed: %s", e)
        return []

    for q in keywords[:MAX_SEARCH_QUERIES]:
        if len(posts) >= BLUESKY_MAX_POSTS:
            break
        try:
            resp = client.app.bsky.feed.search_posts(params={"q": q, "limit": 25})
        except Exception as e:
            logger.warning("Bluesky search failed for %s: %s", q, e)
            continue

        posts_list = getattr(resp, "posts", None) or []
        if not posts_list:
            continue

        for p in posts_list:
            if len(posts) >= BLUESKY_MAX_POSTS:
                break
            uri = getattr(p, "uri", None)
            if not uri or uri in seen_urls:
                continue
            seen_urls.add(uri)

            if uri.startswith("at://"):
                path = uri.replace("at://", "").replace("/app.bsky.feed.post/", "/post/")
                url = f"https://bsky.app/profile/{path}"
            else:
                url = f"https://bsky.app/{uri}"

            # PostView: .record has .text, .createdAt; .author has .handle
            rec = getattr(p, "record", p)
            text = _post_text(rec) or _post_text(p)
            if not text:
                continue

            ts = _parse_timestamp(rec)
            auth = getattr(p, "author", None)
            author = getattr(auth, "handle", None) or getattr(auth, "did", "") if auth else ""

            posts.append(
                RawPost(
                    text=text,
                    source="bluesky",
                    community="bluesky",
                    timestamp=ts,
                    url=url,
                    author=author or None,
                    extra={},
                )
            )

    posts.sort(key=lambda p: p.timestamp)
    return posts[:BLUESKY_MAX_POSTS]


async def search_bluesky(keywords: list[str], exclude_url: str | None = None) -> list[RawPost]:
    """
    Search Bluesky for posts matching keywords. Exclude post at exclude_url.
    Uses sync Client with login; runs in executor for async pipeline.
    """
    exclude_url = (exclude_url or "").strip().rstrip("/")
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: _search_sync(keywords, exclude_url)),
            timeout=API_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Bluesky scraper timed out")
        return []
    except Exception as e:
        logger.exception("Bluesky scrape error: %s", e)
        return []
