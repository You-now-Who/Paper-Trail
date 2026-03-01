"""
scrapers/reddit.py — Reddit scraper agent only. Fetches posts from r/all by search.
Invariant: Returns list[RawPost]; does not cluster, analyze, or format. Must never
throw uncaught; failures log and return empty list.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from schemas import RawPost
from config import REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT, REDDIT_MAX_POSTS, API_TIMEOUT_SECONDS

logger = logging.getLogger(__name__)


def search_reddit(keywords: list[str]) -> list[RawPost]:
    """
    Search Reddit (r/all) for each keyword; merge and sort by date, oldest first.
    Synchronous PRAW run in thread with timeout. Returns empty list on any failure.
    """
    if not REDDIT_CLIENT_ID or not REDDIT_CLIENT_SECRET:
        logger.warning("Reddit credentials missing; skipping Reddit scrape")
        return []

    try:
        import praw
    except ImportError:
        logger.warning("praw not installed; skipping Reddit scrape")
        return []

    seen_urls: set[str] = set()
    posts: list[RawPost] = []

    def _run() -> list[RawPost]:
        reddit = praw.Reddit(
            client_id=REDDIT_CLIENT_ID,
            client_secret=REDDIT_CLIENT_SECRET,
            user_agent=REDDIT_USER_AGENT,
        )
        for q in keywords[:5]:
            if len(posts) >= REDDIT_MAX_POSTS:
                break
            try:
                for submission in reddit.subreddit("all").search(q, sort="new", time_filter="year", limit=25):
                    url = getattr(submission, "url", "") or f"https://reddit.com{submission.permalink}"
                    if url in seen_urls:
                        continue
                    seen_urls.add(url)
                    ts = datetime.fromtimestamp(submission.created_utc, tz=timezone.utc).isoformat()
                    text = (getattr(submission, "title", "") or "") + " " + (getattr(submission, "selftext", "") or "")
                    text = (text or submission.title or "")[:2000].strip()
                    if not text:
                        continue
                    posts.append(
                        RawPost(
                            text=text,
                            source="reddit",
                            community=getattr(submission.subreddit, "display_name", "reddit"),
                            timestamp=ts,
                            url=url,
                            author=getattr(submission.author, "name", None) if submission.author else None,
                            extra={"upvotes": getattr(submission, "score", 0)},
                        )
                    )
                    if len(posts) >= REDDIT_MAX_POSTS:
                        break
            except Exception as e:
                logger.warning("Reddit search failed for %s: %s", q, e)
        posts.sort(key=lambda p: p.timestamp)
        return posts[:REDDIT_MAX_POSTS]

    try:
        return _run()
    except Exception as e:
        logger.exception("Reddit scraper failed: %s", e)
        return []


async def scrape_reddit_async(keywords: list[str]) -> list[RawPost]:
    """Async wrapper: run sync PRAW in executor with timeout."""
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, lambda: search_reddit(keywords)),
            timeout=API_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Reddit scraper timed out")
        return []
    except Exception as e:
        logger.exception("Reddit scrape error: %s", e)
        return []
