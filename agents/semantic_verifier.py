"""
agents/semantic_verifier.py — Model-based claim verification.
Invariant: Given claim + corpus, outputs confidence 0–1 that claim has support in corpus.
Uses OpenAI embeddings (cosine similarity) or LLM. Never throws — returns low confidence on failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from config import (
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    OPENAI_CHAT_MODEL,
    SEMANTIC_SIMILARITY_THRESHOLD,
    API_TIMEOUT_SECONDS,
)
from schemas import SemanticVerificationResult

if TYPE_CHECKING:
    from schemas import RawPost

logger = logging.getLogger(__name__)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API."""
    if not OPENAI_API_KEY or not texts:
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS)
        resp = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=texts)
        return [e.embedding for e in resp.data]
    except Exception as e:
        logger.warning("Semantic verifier embedding failed: %s", e)
        return []


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def verify_claim_embeddings(claim: str, corpus: list["RawPost"]) -> SemanticVerificationResult:
    """
    Embed claim and corpus chunks; return max cosine similarity as confidence.
    Handles paraphrases, typos, etc. via semantic similarity.
    """
    if not claim or not claim.strip():
        return SemanticVerificationResult(claim=claim, confidence=0.0, method="embeddings")

    if not corpus:
        return SemanticVerificationResult(claim=claim, confidence=0.0, best_corpus_index=None, method="embeddings")

    corpus_texts = [p.text[:2000] for p in corpus]
    texts = [claim.strip()[:2000]] + corpus_texts
    vectors = _embed_batch(texts)
    if len(vectors) < 2:
        return SemanticVerificationResult(claim=claim, confidence=0.0, method="embeddings")

    claim_vec = np.array(vectors[0], dtype=np.float64)
    best_sim = 0.0
    best_idx: int | None = None
    for i, v in enumerate(vectors[1:]):
        s = _cosine_sim(claim_vec, np.array(v, dtype=np.float64))
        if s > best_sim:
            best_sim = s
            best_idx = i

    return SemanticVerificationResult(
        claim=claim,
        confidence=best_sim,
        best_corpus_index=best_idx,
        method="embeddings",
    )


def verify_diff_phrases(
    removed: list[str],
    added: list[str],
    corpus: list["RawPost"],
    origin_text: str,
) -> list[SemanticVerificationResult]:
    """
    Verify each diff phrase (removed/added) has support.
    - Removed: should appear in origin or corpus
    - Added: should NOT appear in origin (we're checking the inverse: is the added phrase semantically different from corpus? — actually we want: is the *removed* phrase supported in corpus, and is the *added* phrase a mutation?)
    Simpler: verify removed phrases have support in corpus/origin. For added, we don't need to verify — they're new.
    """
    results: list[SemanticVerificationResult] = []
    searchable = corpus + []  # We'll use corpus; for "removed" we check if it's in origin
    origin_for_search = [{"text": origin_text}] if origin_text else []
    search_corpus = [p for p in corpus]  # RawPost has .text

    for phrase in removed:
        if not phrase or not phrase.strip():
            continue
        # Check against origin first (removed from origin → should be in origin)
        r = verify_claim_embeddings(phrase, search_corpus)
        # If origin exists, also check origin "as a post"
        if origin_text and origin_text.strip():
            from schemas import RawPost
            fake = [RawPost(text=origin_text, source="bluesky", community="bluesky", timestamp="", url="")]
            r_origin = verify_claim_embeddings(phrase, fake)
            r = r_origin if r_origin.confidence > r.confidence else r
        results.append(r)

    # Added phrases: no verification needed (they're new). Optionally verify they're NOT in origin (confirms they're novel).
    for phrase in added:
        if not phrase or not phrase.strip():
            continue
        r = verify_claim_embeddings(phrase, search_corpus)
        # Low similarity = phrase is novel (good). High = might be paraphrased from corpus.
        results.append(r)

    return results


def verify_mutation_notes(
    mutation_notes: list[str],
    corpus: list["RawPost"],
) -> list[SemanticVerificationResult]:
    """Verify each mutation note has support in corpus (i.e. describes something real)."""
    results: list[SemanticVerificationResult] = []
    for note in mutation_notes:
        if not note or not note.strip():
            continue
        r = verify_claim_embeddings(note, corpus)
        results.append(r)
    return results
