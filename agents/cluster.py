"""
agents/cluster.py — Clustering agent only. Embeds posts and groups by semantic similarity.
Invariant: Input merged list[RawPost], output list[Cluster]. Does not scrape or format;
must never throw uncaught — returns single-cluster fallback on failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from config import (
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    CLUSTER_SIMILARITY_THRESHOLD,
    MAX_CLUSTERS,
    API_TIMEOUT_SECONDS,
)

if TYPE_CHECKING:
    from schemas import RawPost, Cluster

logger = logging.getLogger(__name__)


def _embed_batch(texts: list[str]) -> list[list[float]]:
    """Call OpenAI embeddings API. Returns list of vectors or empty on failure."""
    if not OPENAI_API_KEY or not texts:
        return []
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS)
        resp = client.embeddings.create(model=OPENAI_EMBEDDING_MODEL, input=texts)
        return [e.embedding for e in resp.data]
    except Exception as e:
        logger.warning("Embedding failed: %s", e)
        return []


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity between two vectors."""
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def cluster_posts(corpus: list["RawPost"]) -> list["Cluster"]:
    """
    Group corpus by semantic similarity. Each cluster has indices into corpus and
    earliest_timestamp. Returns at least one cluster (all indices) on empty or failure.
    """
    from schemas import Cluster

    if not corpus:
        return []

    # Single post -> one cluster
    if len(corpus) == 1:
        return [Cluster(indices=[0], earliest_timestamp=corpus[0].timestamp)]

    texts = [p.text[:8000] for p in corpus]
    vectors = _embed_batch(texts)
    if len(vectors) != len(corpus):
        # Fallback: one cluster per post (chronological order)
        indexed = sorted(range(len(corpus)), key=lambda i: corpus[i].timestamp)
        return [
            Cluster(indices=[i], earliest_timestamp=corpus[i].timestamp)
            for i in indexed
        ]

    n = len(corpus)
    vecs = np.array(vectors, dtype=np.float64)

    # Greedy clustering: merge if sim >= threshold
    assigned = [-1] * n  # cluster id per index
    next_id = 0
    for i in range(n):
        if assigned[i] >= 0:
            continue
        assigned[i] = next_id
        for j in range(i + 1, n):
            if assigned[j] >= 0:
                continue
            if _cosine_sim(vecs[i], vecs[j]) >= CLUSTER_SIMILARITY_THRESHOLD:
                assigned[j] = next_id
        next_id += 1
        if next_id >= MAX_CLUSTERS:
            break

    # Assign any remaining to nearest cluster or own
    for j in range(n):
        if assigned[j] >= 0:
            continue
        best_sim = -1.0
        best_c = 0
        for c in range(next_id):
            rep = next(i for i in range(n) if assigned[i] == c)
            s = _cosine_sim(vecs[j], vecs[rep])
            if s > best_sim:
                best_sim, best_c = s, c
        if best_sim >= CLUSTER_SIMILARITY_THRESHOLD:
            assigned[j] = best_c
        else:
            assigned[j] = next_id
            next_id += 1
            if next_id >= MAX_CLUSTERS:
                break

    # Build Cluster objects: group indices by assigned id, compute earliest_timestamp
    clusters: list[Cluster] = []
    for c in range(next_id):
        indices = [i for i in range(n) if assigned[i] == c]
        if not indices:
            continue
        ts = min(corpus[i].timestamp for i in indices)
        clusters.append(Cluster(indices=indices, earliest_timestamp=ts))

    clusters.sort(key=lambda cl: cl.earliest_timestamp)
    return clusters[:MAX_CLUSTERS]
