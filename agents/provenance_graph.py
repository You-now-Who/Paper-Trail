"""
agents/provenance_graph.py — Build provenance graph from corpus + current post.
Relevance filter, edge formation (quote/ngram/paraphrase), path finding.
Never throws; returns empty graph on failure.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np

from config import (
    OPENAI_API_KEY,
    OPENAI_EMBEDDING_MODEL,
    API_TIMEOUT_SECONDS,
    THETA_RELEVANCE,
    THETA_EDGE,
    MIN_QUOTE_FOR_EDGE,
    MIN_NGRAM_FOR_EDGE,
    MIN_PARAPHRASE_FOR_SIGNAL,
    MIN_SIGNALS_FOR_EDGE,
    MAX_PATH_LENGTH,
    MAX_OUT_EDGES_PER_NODE,
    CONNECTION_SANITY_CHECK_ENABLED,
    CONNECTION_SANITY_MAX_CHECKS,
)
from agents.edge_evidence import edge_evidence_score
from agents.mutation_detectors import detect_mutations
from agents.message_propagation import extract_message, compute_propagation
from agents.connection_sanity import connection_makes_sense
from schemas import ProvenanceGraph, ProvenanceNode, ProvenanceEdge

if TYPE_CHECKING:
    from schemas import RawPost

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
        logger.warning("Provenance graph embedding failed: %s", e)
        return []


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _before_or_equal(ts_a: str, ts_b: str) -> bool:
    """True if ts_a is before or equal to ts_b (ISO string compare). Empty = unknown, treat as not before."""
    a, b = (ts_a or "").strip(), (ts_b or "").strip()
    if not b:
        return True
    if not a:
        return False
    return a <= b


def _has_cycle(edges: list[tuple[int, int]], n_nodes: int) -> bool:
    """True if adding edges would create a cycle. Uses DFS."""
    adj: dict[int, list[int]] = {i: [] for i in range(n_nodes)}
    for u, v in edges:
        adj[u].append(v)
    visited = [False] * n_nodes
    rec = [False] * n_nodes

    def dfs(i: int) -> bool:
        visited[i] = True
        rec[i] = True
        for j in adj[i]:
            if not visited[j]:
                if dfs(j):
                    return True
            elif rec[j]:
                return True
        rec[i] = False
        return False

    for i in range(n_nodes):
        if not visited[i] and dfs(i):
            return True
    return False


def build_provenance_graph(
    corpus: list["RawPost"],
    current_text: str,
    current_url: str,
    current_timestamp: str,
    current_author: str = "",
) -> ProvenanceGraph:
    """
    Build provenance graph: relevance filter, edge formation, path finding.
    Returns ProvenanceGraph with nodes, edges, main_path.
    """
    if not corpus:
        return ProvenanceGraph(nodes=[], edges=[], main_path=[], alternative_paths=[])

    # Corpus indices 0..n-1; current is index n
    n_corpus = len(corpus)
    current_idx = n_corpus
    texts = [p.text[:2000] for p in corpus] + [current_text[:2000]]

    # Embed all
    vecs = _embed_batch(texts)
    if len(vecs) != len(texts):
        return ProvenanceGraph(nodes=[], edges=[], main_path=[], alternative_paths=[])

    vecs_arr = np.array(vecs, dtype=np.float64)
    current_vec = vecs_arr[current_idx]

    # Timestamp helper: corpus index -> timestamp string
    def ts(idx: int) -> str:
        if idx < n_corpus:
            return corpus[idx].timestamp
        return current_timestamp

    # Relevance filter: keep corpus posts with sim >= THETA_RELEVANCE and not after current post
    relevant: list[int] = []
    for i in range(n_corpus):
        if not _before_or_equal(corpus[i].timestamp, current_timestamp):
            continue
        s = _cosine(vecs_arr[i], current_vec)
        if s >= THETA_RELEVANCE:
            relevant.append(i)

    if not relevant:
        return ProvenanceGraph(nodes=[], edges=[], main_path=[], alternative_paths=[])

    # Node order: chronological (earliest first, current last); stable sort by index for determinism
    node_indices = sorted(relevant, key=lambda i: (ts(i), i)) + [current_idx]
    nodes: list[ProvenanceNode] = []
    for idx in node_indices:
        if idx < n_corpus:
            p = corpus[idx]
            nodes.append(ProvenanceNode(
                index=idx,
                text=p.text[:500],
                source=p.source,
                community=p.community,
                timestamp=p.timestamp,
                url=p.url or "",
                author=p.author or "",
                is_current=False,
            ))
        else:
            nodes.append(ProvenanceNode(
                index=current_idx,
                text=current_text[:500],
                source="bluesky",
                community="bluesky",
                timestamp=current_timestamp,
                url=current_url,
                author=current_author,
                is_current=True,
            ))

    # Map: node_idx (corpus or current) -> position in nodes list
    idx_to_pos: dict[int, int] = {node_indices[i]: i for i in range(len(node_indices))}
    current_pos = idx_to_pos[current_idx]

    # Build edges: for each (A, B) with A.timestamp < B.timestamp and A, B in node_indices
    candidate_edges: list[tuple[float, int, int, list[str]]] = []
    for i in node_indices:
        for j in node_indices:
            if i == j:
                continue
            if ts(i) >= ts(j):
                continue
            # i -> j
            text_i = corpus[i].text[:2000] if i < n_corpus else current_text[:2000]
            text_j = corpus[j].text[:2000] if j < n_corpus else current_text[:2000]
            score, ev_types, quote, ngram, paraphrase = edge_evidence_score(text_i, text_j)
            # Multi-signal: require ≥ MIN_SIGNALS_FOR_EDGE so edges are well-supported
            signals = (1 if quote >= MIN_QUOTE_FOR_EDGE else 0) + (1 if ngram >= MIN_NGRAM_FOR_EDGE else 0) + (1 if paraphrase >= MIN_PARAPHRASE_FOR_SIGNAL else 0)
            if score >= THETA_EDGE and signals >= MIN_SIGNALS_FOR_EDGE:
                candidate_edges.append((score, i, j, ev_types))

    # Stable sort: score desc, then (i, j) for determinism
    candidate_edges.sort(key=lambda x: (-x[0], x[1], x[2]))
    # Optional: only keep edges where it makes sense for B to derive from A (same story/event)
    if CONNECTION_SANITY_CHECK_ENABLED and candidate_edges:
        sane: list[tuple[float, int, int, list[str]]] = []
        for score, i, j, ev_types in to_check:
            text_i = corpus[i].text[:2000] if i < n_corpus else current_text[:2000]
            text_j = corpus[j].text[:2000] if j < n_corpus else current_text[:2000]
            if connection_makes_sense(text_i, text_j):
                sane.append((score, i, j, ev_types))
        candidate_edges = sane + candidate_edges[CONNECTION_SANITY_MAX_CHECKS:]

    # Add edges greedily, enforcing DAG and max out-degree
    edges_added: list[tuple[int, int, float, list[str]]] = []
    out_degree: dict[int, int] = {idx: 0 for idx in node_indices}

    for score, i, j, ev_types in candidate_edges:
        pos_i, pos_j = idx_to_pos[i], idx_to_pos[j]
        if out_degree[i] >= MAX_OUT_EDGES_PER_NODE:
            continue
        test_edges = [(idx_to_pos[a], idx_to_pos[b]) for a, b, _, _ in edges_added] + [(pos_i, pos_j)]
        if _has_cycle(test_edges, len(node_indices)):
            continue
        edges_added.append((i, j, score, ev_types))
        out_degree[i] += 1

    edges: list[ProvenanceEdge] = []
    for i, j, score, ev_types in edges_added:
        pos_i, pos_j = idx_to_pos[i], idx_to_pos[j]
        text_i = corpus[i].text[:2000] if i < n_corpus else current_text[:2000]
        text_j = corpus[j].text[:2000] if j < n_corpus else current_text[:2000]
        mutations = detect_mutations(text_i, text_j)
        edges.append(ProvenanceEdge(
            source=pos_i,
            target=pos_j,
            evidence_score=score,
            evidence_types=ev_types,
            mutations=mutations,
        ))

    # Path finding: roots -> current
    in_degree = {p: 0 for p in range(len(node_indices))}
    adj: dict[int, list[tuple[int, float]]] = {p: [] for p in range(len(node_indices))}
    for e in edges:
        in_degree[e.target] += 1
        adj[e.source].append((e.target, e.evidence_score))

    roots = [p for p in range(len(node_indices)) if in_degree[p] == 0]
    if not roots:
        return ProvenanceGraph(nodes=nodes, edges=edges, main_path=[], alternative_paths=[])

    # DFS to find all simple paths from roots to current_pos
    all_paths: list[tuple[list[int], float]] = []

    def dfs(path: list[int], score_prod: float):
        if len(path) > MAX_PATH_LENGTH:
            return
        cur = path[-1]
        if cur == current_pos:
            all_paths.append((path[:], score_prod))
            return
        for nxt, escore in adj[cur]:
            if nxt in path:
                continue
            path.append(nxt)
            dfs(path, score_prod * escore)
            path.pop()

    for r in roots:
        dfs([r], 1.0)

    if not all_paths:
        return ProvenanceGraph(nodes=nodes, edges=edges, main_path=[], alternative_paths=[])

    # Rank by geometric mean (or product) of edge scores; prefer shorter paths for tie
    all_paths.sort(key=lambda x: (-x[1], len(x[0])))
    main_path = all_paths[0][0]
    alternative_paths = [p[0] for p in all_paths[1:4] if p[1] >= THETA_EDGE ** len(p[0])]

    # Propagation: track that one message across nodes (smear-campaign focus)
    propagated_message = ""
    propagation_node_indices: list[int] = []
    propagation_authors: list[str] = []
    try:
        propagated_message = extract_message(current_text)
        if not propagated_message and current_text:
            propagated_message = (current_text or "").strip()[:200]  # Fallback: use post start as message
        if propagated_message:
            propagation_node_indices, propagation_kinds = compute_propagation(propagated_message, nodes)
            nodes = [n.model_copy(update={"propagation_kind": propagation_kinds[i]}) for i, n in enumerate(nodes)]
            # Unique authors among propagation nodes (multiple accounts saying same thing)
            seen: set[str] = set()
            for i in propagation_node_indices:
                a = (nodes[i].author or "").strip()
                if a and a.lower() not in {s.lower() for s in seen}:
                    seen.add(a)
            propagation_authors = list(seen)
    except Exception as e:
        logger.warning("Message propagation step failed: %s", e)

    return ProvenanceGraph(
        nodes=nodes,
        edges=edges,
        main_path=main_path,
        alternative_paths=alternative_paths,
        propagated_message=propagated_message,
        propagation_node_indices=propagation_node_indices,
        propagation_authors=propagation_authors,
    )


def graph_to_origin_and_timeline(graph: ProvenanceGraph) -> tuple["OriginCard | None", list["TimelineEntry"]]:
    """Convert ProvenanceGraph main_path to OriginCard + TimelineEntry list for backward compatibility."""
    from schemas import OriginCard, TimelineEntry

    if not graph.main_path or not graph.nodes:
        return None, []

    path = graph.main_path
    nodes = graph.nodes
    edge_map: dict[tuple[int, int], ProvenanceEdge] = {(e.source, e.target): e for e in graph.edges}

    origin_node = nodes[path[0]]
    origin = OriginCard(
        text=origin_node.text[:500],
        source=origin_node.source,
        community=origin_node.community,
        timestamp=origin_node.timestamp,
        url=origin_node.url,
    )

    timeline: list[TimelineEntry] = []
    for i in range(1, len(path) - 1):
        prev, curr = path[i - 1], path[i]
        node = nodes[curr]
        edge = edge_map.get((prev, curr))
        note = ""
        if edge and edge.mutations:
            types = [m.type for m in edge.mutations if m.type]
            note = ", ".join(types) if types else ""
        timeline.append(TimelineEntry(
            text=node.text[:500],
            source=node.source,
            community=node.community,
            timestamp=node.timestamp,
            mutation_note=note,
            url=node.url,
        ))

    return origin, timeline
