"""
main.py — FastAPI app: /trace and /health only; orchestrates scrapers and agents.
Invariant: Single entrypoint; all external calls wrapped so one failure cannot crash
the pipeline; parallel scrapers, sequential agents; returns ProvenanceResponse always.
"""

from __future__ import annotations

import asyncio
import logging
import re
import uuid
from typing import List

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from schemas import (
    TraceRequest,
    ProvenanceResponse,
    OriginCard,
    TimelineEntry,
    DiffResult,
    RawPost,
    Cluster,
    UserSummary,
    MutationLogEntry,
)
from config import (
    OPENAI_API_KEY,
    API_TIMEOUT_SECONDS,
    PIPELINE_MAX_SECONDS,
)
from prompts import KEYWORD_EXTRACTION_SYSTEM, KEYWORD_EXTRACTION_USER_TEMPLATE

# Scrapers and agents
from scrapers.reddit import scrape_reddit_async
from scrapers.bluesky import search_bluesky
from agents.cluster import cluster_posts
from agents.provenance import build_timeline
from agents.diff import narrative_diff
from agents.reply import draft_reply
from agents.structural_rules import run_structural_rules
from agents.semantic_verifier import verify_diff_phrases, verify_mutation_notes
from agents.synthesis import build_user_summary
from audit.mutation_log import append_mutation
from report import generate_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Paper Trail", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://bsky.app", "https://*.bsky.app", "http://localhost:8080", "http://127.0.0.1:8080"],
    allow_origin_regex=r"chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _extract_keywords(post_text: str) -> List[str]:
    """LLM or fallback: 3–5 search phrases. Never raises."""
    if not post_text or not post_text.strip():
        return []
    # Fallback: significant words (skip stopwords-ish)
    stop = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "and", "in", "on", "at", "for", "with", "this", "that", "it", "its"}
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", post_text.lower())
    candidates = [w for w in words if w not in stop][:20]
    # Prefer longer phrases: take first 5 unique
    seen = set()
    fallback = []
    for w in candidates:
        if w not in seen:
            seen.add(w)
            fallback.append(w)
        if len(fallback) >= 5:
            break
    if not fallback:
        fallback = candidates[:5] if candidates else [post_text[:50]]

    if not OPENAI_API_KEY:
        return fallback

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY.strip(), timeout=API_TIMEOUT_SECONDS)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": KEYWORD_EXTRACTION_SYSTEM},
                {"role": "user", "content": KEYWORD_EXTRACTION_USER_TEMPLATE.format(post_text=post_text[:2000])},
            ],
            max_tokens=200,
        )
        raw = (resp.choices[0].message.content or "").strip()
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        phrases = []
        for ln in lines:
            ln = re.sub(r"^[\d\-*.)]+\s*", "", ln).strip()
            if ln and len(phrases) < 5:
                phrases.append(ln[:80])
        return phrases if phrases else fallback
    except Exception as e:
        logger.warning("Keyword extraction failed: %s", e)
        return fallback


def _merge_dedupe(reddit_posts: List[RawPost], bluesky_posts: List[RawPost]) -> List[RawPost]:
    """Merge and deduplicate by URL. Chronological order."""
    seen: set[str] = set()
    out: List[RawPost] = []
    for p in reddit_posts + bluesky_posts:
        u = (p.url or "").strip().rstrip("/")
        if u and u not in seen:
            seen.add(u)
            out.append(p)
    out.sort(key=lambda x: x.timestamp)
    return out


@app.get("/health")
def health():
    """Content script pings on load to verify backend is running."""
    return {"status": "ok"}


@app.post("/report", response_class=HTMLResponse)
async def report(req: Request):
    """Generate full HTML report. Accepts JSON body (ProvenanceResponse)."""
    try:
        data = await req.json()
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return HTMLResponse(content=generate_report(data))


@app.post("/trace")
async def trace(req: TraceRequest) -> ProvenanceResponse:
    """
    Main endpoint: run Reddit + Bluesky in parallel, then cluster → provenance → diff → reply.
    Always returns ProvenanceResponse; errors and warnings in response fields.
    """
    errors: List[str] = []
    warnings: List[str] = []

    try:
        keywords = _extract_keywords(req.text)
        if not keywords:
            keywords = [req.text[:80] if req.text else "post"]
    except Exception as e:
        logger.warning("Keyword extraction error: %s", e)
        keywords = [req.text[:80] if req.text else "post"]

    # Parallel scrapers with timeout
    reddit_task = asyncio.create_task(scrape_reddit_async(keywords))
    bluesky_task = asyncio.create_task(search_bluesky(keywords, exclude_url=req.url))

    try:
        reddit_posts, bluesky_posts = await asyncio.wait_for(
            asyncio.gather(reddit_task, bluesky_task, return_exceptions=True),
            timeout=API_TIMEOUT_SECONDS + 2,
        )
    except asyncio.TimeoutError:
        errors.append("Scrapers timed out")
        reddit_posts = []
        bluesky_posts = []

    if isinstance(reddit_posts, BaseException):
        errors.append(f"Reddit scraper failed: {reddit_posts}")
        reddit_posts = []
    if isinstance(bluesky_posts, BaseException):
        errors.append(f"Bluesky scraper failed: {bluesky_posts}")
        bluesky_posts = []

    if not reddit_posts:
        warnings.append("No Reddit results")
    if not bluesky_posts:
        warnings.append("No Bluesky results")

    corpus = _merge_dedupe(
        reddit_posts if isinstance(reddit_posts, list) else [],
        bluesky_posts if isinstance(bluesky_posts, list) else [],
    )
    total_sources = len(corpus)

    # No corpus: return source post as origin, empty timeline, empty diff, simple reply
    if not corpus:
        origin = OriginCard(
            text=req.text[:500] if req.text else "",
            source="bluesky",
            community="bluesky",
            timestamp=req.timestamp or "",
        )
        diff = narrative_diff("", req.text or "")
        reply = draft_reply(
            origin_source="bluesky",
            origin_community="bluesky",
            origin_timestamp=req.timestamp or "",
            origin_snippet=req.text[:200] if req.text else "",
            current_text=req.text or "",
            mutation_summary="No prior sources found.",
        )
        rule_checks = run_structural_rules([], [], 0)
        user_summary = build_user_summary(origin, [], diff, rule_checks, [], 0, errors, warnings)
        return ProvenanceResponse(
            user_summary=user_summary,
            origin=origin,
            timeline=[],
            diff=diff,
            reply_draft=reply,
            total_sources_checked=0,
            current_post_url=req.url or "",
            rule_checks=rule_checks,
            semantic_verifications=[],
            mutations_log=[],
            errors=errors,
            warnings=warnings,
        )

    # Cluster (sync)
    clusters = cluster_posts(corpus)
    if not clusters:
        clusters = [Cluster(indices=list(range(len(corpus))), earliest_timestamp=corpus[0].timestamp)]

    # Build timeline and origin
    origin, timeline = build_timeline(corpus, clusters, req.text or "")

    # Diff: origin text vs current (request) text
    diff = narrative_diff(origin.text, req.text or "")

    # Reply draft
    mutation_summary = timeline[0].mutation_note if timeline else ""
    reply = draft_reply(
        origin_source=origin.source,
        origin_community=origin.community,
        origin_timestamp=origin.timestamp,
        origin_snippet=origin.text[:200],
        current_text=req.text or "",
        mutation_summary=mutation_summary,
    )

    # Structural rules
    rule_checks = run_structural_rules(corpus, timeline, total_sources)

    # Semantic verification (model-based): diff phrases and mutation notes
    semantic_verifications: list = []
    try:
        sv_diff = verify_diff_phrases(diff.removed, diff.added, corpus, origin.text or "")
        semantic_verifications.extend(sv_diff)
        mutation_notes = [e.mutation_note for e in timeline if e.mutation_note]
        sv_notes = verify_mutation_notes(mutation_notes, corpus)
        semantic_verifications.extend(sv_notes)
    except Exception as e:
        logger.warning("Semantic verification failed: %s", e)

    # Mutation log (append-only)
    trace_id = str(uuid.uuid4())
    mutations_log: list[MutationLogEntry] = []
    for phrase in diff.removed:
        mutations_log.append(MutationLogEntry(
            trace_id=trace_id,
            agent_id="diff",
            mutation_type="phrase_removed",
            source_span=phrase,
            target_span="",
            confidence=0.8,
            evidence_corpus_indices=[],
            abstained=False,
        ))
        append_mutation(trace_id, "diff", "phrase_removed", phrase, "", 0.8, [])
    for phrase in diff.added:
        mutations_log.append(MutationLogEntry(
            trace_id=trace_id,
            agent_id="diff",
            mutation_type="phrase_added",
            source_span="",
            target_span=phrase,
            confidence=0.8,
            evidence_corpus_indices=[],
            abstained=False,
        ))
        append_mutation(trace_id, "diff", "phrase_added", "", phrase, 0.8, [])

    # User summary (primary for extension)
    user_summary = build_user_summary(
        origin, timeline, diff, rule_checks, semantic_verifications, total_sources, errors, warnings
    )

    return ProvenanceResponse(
        user_summary=user_summary,
        origin=origin,
        timeline=timeline,
        diff=diff,
        reply_draft=reply,
        total_sources_checked=total_sources,
        current_post_url=req.url or "",
        rule_checks=rule_checks,
        semantic_verifications=semantic_verifications,
        mutations_log=mutations_log,
        errors=errors,
        warnings=warnings,
    )


if __name__ == "__main__":
    import uvicorn
    from config import BACKEND_HOST, BACKEND_PORT
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)
