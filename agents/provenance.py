"""
agents/provenance.py — Provenance ordering agent. Orders clusters chronologically and
writes one-sentence mutation notes per transition.
Invariant: Input list[Cluster] + corpus; output ordered timeline with mutation_note.
Does not scrape or cluster; must never throw uncaught — returns timeline without notes on failure.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from config import OPENAI_API_KEY, OPENAI_CHAT_MODEL, API_TIMEOUT_SECONDS
from prompts import PROVENANCE_SYSTEM, PROVENANCE_USER_TEMPLATE

if TYPE_CHECKING:
    from schemas import RawPost, Cluster, TimelineEntry, OriginCard

logger = logging.getLogger(__name__)


def _repr_cluster(corpus: list["RawPost"], indices: list[int], max_len: int = 400) -> str:
    """One block of text for a cluster: concatenate first few posts, truncated."""
    parts = []
    for i in indices[:5]:
        if i < len(corpus):
            parts.append(corpus[i].text[:200])
    text = " | ".join(parts)[:max_len]
    return text or "(no text)"


def build_timeline(
    corpus: list["RawPost"],
    clusters: list["Cluster"],
    source_post_text: str,
) -> tuple["OriginCard", list["TimelineEntry"]]:
    """
    Clusters are already ordered by earliest_timestamp. Build origin from first cluster
    and timeline entries for each cluster; call LLM for mutation notes. On LLM failure,
    return timeline with empty mutation_note strings.
    """
    from schemas import OriginCard, TimelineEntry

    if not clusters or not corpus:
        origin = OriginCard(
            text=source_post_text[:500],
            source="bluesky",
            community="bluesky",
            timestamp="",
        )
        return origin, []

    first = clusters[0]
    first_idx = first.indices[0] if first.indices else 0
    first_post = corpus[first_idx] if first_idx < len(corpus) else None
    if first_post:
        origin = OriginCard(
            text=first_post.text[:500],
            source=first_post.source,
            community=first_post.community,
            timestamp=first_post.timestamp,
            url=first_post.url or "",
        )
    else:
        origin = OriginCard(
            text=source_post_text[:500],
            source="bluesky",
            community="bluesky",
            timestamp="",
        )

    timeline: list[TimelineEntry] = []
    mutation_notes: list[str] = []

    if len(clusters) > 1:
        cluster_blocks = "\n\n---\n\n".join(
            f"Cluster {i+1} (earliest {c.earliest_timestamp}):\n{_repr_cluster(corpus, c.indices)}"
            for i, c in enumerate(clusters)
        )
        try:
            from openai import OpenAI
            client = OpenAI(api_key=OPENAI_API_KEY, timeout=API_TIMEOUT_SECONDS)
            resp = client.chat.completions.create(
                model=OPENAI_CHAT_MODEL,
                messages=[
                    {"role": "system", "content": PROVENANCE_SYSTEM},
                    {"role": "user", "content": PROVENANCE_USER_TEMPLATE.format(cluster_blocks=cluster_blocks)},
                ],
                max_tokens=500,
                temperature=0,
            )
            raw = (resp.choices[0].message.content or "").strip()
            for line in raw.splitlines():
                line = line.strip()
                if line and not re.match(r"^\d+[.)]", line):
                    mutation_notes.append(line)
                elif line:
                    mutation_notes.append(re.sub(r"^\d+[.)]\s*", "", line).strip())
        except Exception as e:
            logger.warning("Provenance LLM failed: %s", e)

    for i, c in enumerate(clusters):
        idx = c.indices[0] if c.indices else 0
        post = corpus[idx] if idx < len(corpus) else None
        if not post:
            continue
        note = mutation_notes[i - 1] if i > 0 and i - 1 < len(mutation_notes) else ""
        timeline.append(
            TimelineEntry(
                text=post.text[:500],
                source=post.source,
                community=post.community,
                timestamp=post.timestamp,
                mutation_note=note,
                url=post.url or "",
            )
        )

    return origin, timeline
