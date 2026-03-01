"""
schemas.py — Single source of truth for all pipeline data structures.
Invariant: Every agent receives and returns these types. Must never define ad-hoc dicts
or duplicate field definitions in other modules.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# --- Request from extension ---
class TraceRequest(BaseModel):
    """Payload from content script when user clicks Trace."""
    text: str = Field(..., description="Post body text from DOM")
    timestamp: str = Field(..., description="ISO timestamp of the source post")
    author: str = Field(..., description="Bluesky handle of post author")
    url: str = Field(..., description="Permalink to source post")


# --- Raw post: unified shape from Reddit and Bluesky scrapers ---
class RawPost(BaseModel):
    """One post from Reddit or Bluesky. Same shape for both sources."""
    text: str = Field(..., description="Post/comment body text")
    source: Literal["reddit", "bluesky"] = Field(..., description="Origin platform")
    community: str = Field(..., description="Subreddit name or 'bluesky'")
    timestamp: str = Field(..., description="ISO timestamp")
    url: str = Field(..., description="Permalink")
    author: str | None = Field(None, description="Handle or username if available")
    extra: dict | None = Field(None, description="Optional platform-specific metadata")


# --- Clustering: one cluster = list of RawPost indices into merged corpus ---
class Cluster(BaseModel):
    """One semantic cluster: indices into the merged corpus list."""
    indices: list[int] = Field(..., description="Indices into merged RawPost list")
    earliest_timestamp: str = Field(..., description="Min timestamp in cluster for ordering")


# --- Provenance timeline entries (same shape as origin card) ---
class OriginCard(BaseModel):
    """Earliest detected version: one card in the UI."""
    text: str = Field(..., description="Snippet or full text of this version")
    source: str = Field(..., description="reddit or bluesky")
    community: str = Field(..., description="Subreddit or bluesky")
    timestamp: str = Field(..., description="ISO timestamp")


class TimelineEntry(BaseModel):
    """One hop in the mutation timeline."""
    text: str = Field(..., description="Text of this version")
    source: str = Field(..., description="reddit or bluesky")
    community: str = Field(..., description="Subreddit or bluesky")
    timestamp: str = Field(..., description="ISO timestamp")
    mutation_note: str = Field(..., description="One-sentence note on what changed from previous")


# --- Diff output ---
class DiffResult(BaseModel):
    """Word-level diff: origin vs current post."""
    removed: list[str] = Field(default_factory=list, description="Phrases removed from origin")
    added: list[str] = Field(default_factory=list, description="Phrases added in current")


# --- Full response to extension ---
class ProvenanceResponse(BaseModel):
    """Complete response for the inline panel. Fail gracefully: partial data + flags."""
    origin: OriginCard = Field(..., description="Earliest detected version")
    timeline: list[TimelineEntry] = Field(default_factory=list, description="Ordered mutation hops")
    diff: DiffResult = Field(default_factory=lambda: DiffResult(), description="Added/removed phrases")
    reply_draft: str = Field("", description="Ready-to-post Bluesky reply with receipts")
    total_sources_checked: int = Field(0, description="Reddit + Bluesky posts considered")
    errors: list[str] = Field(default_factory=list, description="Non-fatal errors (e.g. scraper timeout)")
    warnings: list[str] = Field(default_factory=list, description="e.g. no Reddit results")
