"""
agents/message_propagation.py — Track one core message as it propagates across nodes.
For smear-campaign focus: find THAT message spreading asynchronously among many posts.
Extracts the message from the current post, scores each node for carrying it, classifies verbatim/paraphrased/shifted.
Never throws; returns empty message / no nodes on failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from config import (
    OPENAI_API_KEY,
    OPENAI_CHAT_MODEL,
    API_TIMEOUT_SECONDS,
    THETA_CARRIES_MESSAGE,
    MESSAGE_EXTRACTION_MAX_CHARS,
)
from prompts import MESSAGE_EXTRACTION_SYSTEM, MESSAGE_EXTRACTION_USER_TEMPLATE
from agents.edge_evidence import quote_overlap, ngram_overlap, paraphrase_score

if TYPE_CHECKING:
    from schemas import ProvenanceNode

logger = logging.getLogger(__name__)


def extract_message(post_text: str) -> str:
    """
    Extract the single core claim/message from the post (for propagation tracking).
    Returns one short sentence; empty on failure or no API.
    """
    text = (post_text or "").strip()[:MESSAGE_EXTRACTION_MAX_CHARS]
    if not text or not OPENAI_API_KEY:
        return ""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS)
        resp = client.chat.completions.create(
            model=OPENAI_CHAT_MODEL,
            messages=[
                {"role": "system", "content": MESSAGE_EXTRACTION_SYSTEM},
                {"role": "user", "content": MESSAGE_EXTRACTION_USER_TEMPLATE.format(post_text=text)},
            ],
            max_tokens=80,
            temperature=0,
        )
        msg = (resp.choices[0].message.content or "").strip()
        return msg[:300] if msg else ""
    except Exception as e:
        logger.warning("Message extraction failed: %s", e)
        return ""


def score_carries_message(message: str, node_text: str) -> float:
    """
    Score 0–1: how much does node_text carry the same message?
    Uses quote overlap (message -> node) and paraphrase similarity.
    """
    if not message or not node_text:
        return 0.0
    q = quote_overlap(message, node_text, min_len=8)
    p = paraphrase_score(message, node_text)
    # Weight so that either strong quote or strong paraphrase counts
    return min(1.0, 0.5 * q + 0.5 * p)


def propagation_kind(message: str, node_text: str, score: float) -> str:
    """
    Classify how this node carries the message: verbatim, paraphrased, or shifted.
    Empty string if score below threshold (doesn't carry).
    """
    if not message or not node_text or score < THETA_CARRIES_MESSAGE:
        return ""
    q = quote_overlap(message, node_text, min_len=8)
    ng = ngram_overlap(message, node_text, n=3)
    p = paraphrase_score(message, node_text)
    if q >= 0.15 or ng >= 0.2:
        return "verbatim"
    if p >= 0.72:
        return "paraphrased"
    return "shifted"


def compute_propagation(
    message: str,
    nodes: list["ProvenanceNode"],
) -> tuple[list[int], list[str]]:
    """
    For each node, score and classify. Returns (indices that carry the message, propagation_kind per node).
    """
    indices: list[int] = []
    kinds: list[str] = []
    for i, node in enumerate(nodes):
        text = node.text or ""
        sc = score_carries_message(message, text)
        kind = propagation_kind(message, text, sc)
        kinds.append(kind)
        if kind:
            indices.append(i)
    return indices, kinds
