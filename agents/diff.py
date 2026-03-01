"""
agents/diff.py — Narrative diff agent. Compares origin text vs current post text.
Invariant: Input two strings; output DiffResult. Does not scrape or cluster; must never
throw uncaught — returns empty diff on failure.
"""

from __future__ import annotations

import json
import logging
import re

from schemas import DiffResult
from config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, API_TIMEOUT_SECONDS
from prompts import DIFF_SYSTEM, DIFF_USER_TEMPLATE

logger = logging.getLogger(__name__)


def narrative_diff(origin_text: str, current_text: str) -> DiffResult:
    """
    LLM returns JSON { "removed": [...], "added": [...] }. Parse and return DiffResult.
    On failure or invalid JSON, return DiffResult(removed=[], added=[]).
    """
    if not origin_text and not current_text:
        return DiffResult(removed=[], added=[])

    if not OPENAI_API_KEY:
        return DiffResult(removed=[], added=[])

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS)
        resp = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": DIFF_SYSTEM},
                {"role": "user", "content": DIFF_USER_TEMPLATE.format(origin_text=origin_text or "(none)", current_text=current_text or "(none)")},
            ],
            max_tokens=400,
        )
        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown code block if present
        if raw.startswith("```"):
            raw = re.sub(r"^```\w*\n?", "", raw).rstrip("`")
        data = json.loads(raw)
        removed = list(data.get("removed", [])) if isinstance(data.get("removed"), list) else []
        added = list(data.get("added", [])) if isinstance(data.get("added"), list) else []
        return DiffResult(removed=removed, added=added)
    except Exception as e:
        logger.warning("Diff LLM failed: %s", e)
        return DiffResult(removed=[], added=[])
