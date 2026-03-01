"""
agents/mutation_detectors.py — Per-edge mutation detection.
Quote reuse, paraphrase. Attach mutations to edges.
Never throws; returns empty list on failure.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from agents.edge_evidence import quote_overlap, paraphrase_score
from schemas import MutationRecord

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

MIN_QUOTE_LEN = 15


def _find_longest_substring(text_a: str, text_b: str, min_len: int = 10) -> tuple[str, str, float]:
    """Find longest substring of A that appears in B. Returns (source_span, target_span, overlap_ratio)."""
    a = (text_a or "").strip()
    b = (text_b or "").strip()
    if not a or not b or len(a) < min_len:
        return ("", "", 0.0)

    best_len = 0
    best_a = ""
    best_b = ""

    for start in range(len(a)):
        for end in range(start + min_len, min(start + 200, len(a) + 1)):
            phrase = a[start:end]
            if phrase in b:
                if end - start > best_len:
                    best_len = end - start
                    best_a = phrase
                    best_b = phrase
    if best_len == 0:
        return ("", "", 0.0)
    ratio = best_len / min(len(a), len(b)) if (a and b) else 0.0
    return (best_a, best_b, ratio)


def detect_mutations(text_a: str, text_b: str) -> list[MutationRecord]:
    """
    Run mutation detectors for edge A -> B.
    Returns list of MutationRecord (quote_reuse, paraphrase).
    """
    mutations: list[MutationRecord] = []
    a = (text_a or "").strip()
    b = (text_b or "").strip()
    if not a or not b:
        return mutations

    # Quote reuse
    source_span, target_span, ratio = _find_longest_substring(a, b, MIN_QUOTE_LEN)
    if ratio > 0.1:
        mutations.append(MutationRecord(
            type="quote_reuse",
            source_span=source_span[:200],
            target_span=target_span[:200],
            confidence=min(1.0, ratio * 2),
            agent_id="quote_reuse",
        ))

    # Paraphrase (embedding similarity)
    p = paraphrase_score(a, b)
    if p > 0.75 and not mutations:
        mutations.append(MutationRecord(
            type="paraphrase",
            source_span=a[:150],
            target_span=b[:150],
            confidence=p,
            agent_id="paraphrase",
        ))
    elif p > 0.75 and mutations:
        mutations.append(MutationRecord(
            type="paraphrase",
            source_span="",
            target_span="",
            confidence=p,
            agent_id="paraphrase",
        ))

    return mutations
