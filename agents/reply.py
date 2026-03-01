"""
agents/reply.py — Reply drafter agent. Drafts a Bluesky reply with provenance.
Invariant: Input origin snippet, current text, mutation summary; output reply string.
Does not scrape or cluster; must never throw uncaught — returns fallback string on failure.
"""

from __future__ import annotations

import logging

from config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, API_TIMEOUT_SECONDS
from prompts import REPLY_SYSTEM, REPLY_USER_TEMPLATE

logger = logging.getLogger(__name__)


def draft_reply(
    origin_source: str,
    origin_community: str,
    origin_timestamp: str,
    origin_snippet: str,
    current_text: str,
    mutation_summary: str,
) -> str:
    """
    One LLM call to produce a short Bluesky reply (max 300 chars) citing origin and
    key mutation. On failure, return a simple fallback reply.
    """
    fallback = f"Origin: {origin_source}/{origin_community} ({origin_timestamp}). Trace via Paper Trail."

    if not OPENAI_API_KEY:
        return fallback

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS)
        resp = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": REPLY_SYSTEM},
                {
                    "role": "user",
                    "content": REPLY_USER_TEMPLATE.format(
                        origin_source=origin_source,
                        origin_community=origin_community,
                        origin_timestamp=origin_timestamp,
                        origin_snippet=(origin_snippet or "")[:300],
                        current_text=(current_text or "")[:500],
                        mutation_summary=mutation_summary or "None noted.",
                    ),
                },
            ],
            max_tokens=150,
            temperature=0,
        )
        reply = (resp.choices[0].message.content or "").strip()[:300]
        return reply if reply else fallback
    except Exception as e:
        logger.warning("Reply LLM failed: %s", e)
        return fallback
