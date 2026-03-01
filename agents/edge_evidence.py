"""
agents/edge_evidence.py — Evidence scoring for provenance edges.
Computes quote overlap, n-gram overlap, paraphrase (embedding) for pair (A, B).
Never throws; returns 0 on failure.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

import numpy as np

from config import (
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    API_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    if not OPENAI_API_KEY or not texts:
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS)
        resp = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=texts)
        return [e.embedding for e in resp.data]
    except Exception as e:
        logger.warning("Edge evidence embedding failed: %s", e)
        return []


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z0-9]{2,}\b", (text or "").lower())


def _ngrams(tokens: list[str], n: int) -> set[str]:
    out: set[str] = set()
    for i in range(len(tokens) - n + 1):
        out.add(" ".join(tokens[i : i + n]))
    return out


def quote_overlap(text_a: str, text_b: str, min_len: int = 10) -> float:
    """
    Fraction of A's content that appears in B (as substring).
    Returns 0–1. Uses sliding window for phrases.
    """
    a = (text_a or "").strip()
    b = (text_b or "").strip()
    if not a or not b:
        return 0.0

    # Normalize whitespace
    a_norm = " ".join(a.split())
    b_norm = " ".join(b.split())
    if len(a_norm) < min_len:
        return 1.0 if a_norm in b_norm else 0.0

    # Sliding windows of length min_len to len(a)
    matched = 0
    total = 0
    step = max(1, min_len // 2)
    for start in range(0, len(a_norm) - min_len + 1, step):
        phrase = a_norm[start : start + min(50, len(a_norm) - start)]
        if len(phrase) < min_len:
            continue
        total += 1
        if phrase in b_norm:
            matched += 1
    return matched / total if total > 0 else 0.0


def ngram_overlap(text_a: str, text_b: str, n: int = 4) -> float:
    """Jaccard similarity of n-grams. Returns 0–1."""
    toks_a = _tokenize(text_a)
    toks_b = _tokenize(text_b)
    if not toks_a or not toks_b:
        return 0.0
    ng_a = _ngrams(toks_a, min(n, len(toks_a)))
    ng_b = _ngrams(toks_b, min(n, len(toks_b)))
    if not ng_a or not ng_b:
        return 0.0
    inter = len(ng_a & ng_b)
    union = len(ng_a | ng_b)
    return inter / union if union > 0 else 0.0


def paraphrase_score(text_a: str, text_b: str) -> float:
    """Embedding cosine similarity. Returns 0–1."""
    if not text_a or not text_b:
        return 0.0
    vecs = _embed_batch([text_a[:2000], text_b[:2000]])
    if len(vecs) < 2:
        return 0.0
    return max(0.0, _cosine(np.array(vecs[0]), np.array(vecs[1])))


def edge_evidence_score(
    text_a: str,
    text_b: str,
    w_quote: float = 0.4,
    w_ngram: float = 0.3,
    w_paraphrase: float = 0.3,
) -> tuple[float, list[str], float, float, float]:
    """
    Combined evidence score for A -> B.
    Returns (score 0–1, evidence types, quote, ngram, paraphrase).
    Caller should require ≥ MIN_SIGNALS_FOR_EDGE signals (quote/ngram/paraphrase above thresholds).
    """
    q = quote_overlap(text_a, text_b)
    ng = ngram_overlap(text_a, text_b)
    p = paraphrase_score(text_a, text_b)

    types: list[str] = []
    if q > 0.1:
        types.append("quote_overlap")
    if ng > 0.05:
        types.append("ngram")
    if p > 0.7:
        types.append("paraphrase")

    score = w_quote * q + w_ngram * min(1.0, ng * 3) + w_paraphrase * p
    return min(1.0, score), types, q, ng, p
