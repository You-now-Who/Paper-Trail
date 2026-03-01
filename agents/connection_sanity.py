"""
agents/connection_sanity.py — Check if it makes sense for one post to connect to another in the provenance graph.
Same story/event, B could derive from A; rejects same-topic-different-event or nonsensical links.
Never throws; returns True (allow) on failure so graph still builds when API is down.
"""

from __future__ import annotations

import logging
import re

from config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, API_TIMEOUT_SECONDS
from prompts import CONNECTION_SANITY_SYSTEM, CONNECTION_SANITY_USER_TEMPLATE

logger = logging.getLogger(__name__)

# Truncate so we don't blow context
MAX_TEXT_LEN = 600


def connection_makes_sense(text_a: str, text_b: str) -> bool:
    """
    Returns True if it plausibly makes sense for B to derive from A (same story/event).
    Returns False if they're different events or the link is nonsensical.
    On API failure returns True (fail open: allow edge so graph still builds).
    """
    a = (text_a or "").strip()[:MAX_TEXT_LEN]
    b = (text_b or "").strip()[:MAX_TEXT_LEN]
    if not a or not b:
        return True
    if not OPENAI_API_KEY:
        return True
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS)
        resp = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": CONNECTION_SANITY_SYSTEM},
                {"role": "user", "content": CONNECTION_SANITY_USER_TEMPLATE.format(text_a=a, text_b=b)},
            ],
            max_tokens=10,
            temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip().upper()
        if re.search(r"\bYES\b", raw):
            return True
        if re.search(r"\bNO\b", raw):
            return False
        # Unclear answer: allow (fail open)
        return True
    except Exception as e:
        logger.warning("Connection sanity check failed: %s", e)
        return True
