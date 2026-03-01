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
from datetime import datetime, timezone, timedelta
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
    ProvenanceGraph,
    SameMessageSpread,
    BotScore,
)
from config import (
    OPENAI_API_KEY,
    API_TIMEOUT_SECONDS,
    PIPELINE_MAX_SECONDS,
    CORPUS_DAYS_LIMIT,
    MIN_EDGES_TO_USE_GRAPH,
    PROPAGATION_ACCOUNTS_ALERT_THRESHOLD,
    MAX_SEARCH_QUERIES,
    SEARCH_POST_SNIPPET_LEN,
    BOT_SCORE_ENABLED,
    BOT_SCORE_POSTS_LIMIT,
)
from prompts import KEYWORD_EXTRACTION_SYSTEM, KEYWORD_EXTRACTION_USER_TEMPLATE

# Scrapers and agents
from scrapers.reddit import scrape_reddit_async
from scrapers.bluesky import search_bluesky, get_author_feed_async
from agents.bot_score import compute_bot_score
from agents.cluster import cluster_posts
from agents.provenance import build_timeline
from agents.provenance_graph import build_provenance_graph, graph_to_origin_and_timeline
from agents.diff import narrative_diff
from agents.reply import draft_reply
from agents.structural_rules import run_structural_rules
from agents.semantic_verifier import verify_diff_phrases, verify_mutation_notes
from agents.synthesis import build_user_summary
from audit.mutation_log import append_mutation
from report import generate_report

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def _get_bot_score(author_feed_task: asyncio.Task | None) -> BotScore | None:
    """Await author feed task and return BotScore if we have enough posts."""
    if author_feed_task is None:
        return None
    try:
        posts = await author_feed_task
        if not posts or len(posts) < 2:
            return BotScore(score=0.0, signal="Not enough posts", posts_analyzed=len(posts) if posts else 0)
        score, signal = compute_bot_score(posts)
        return BotScore(score=score, signal=signal, posts_analyzed=len(posts))
    except Exception as e:
        logger.warning("Bot score failed: %s", e)
        return None

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
    """
    Robust search phrases: always include post snippet + n-grams + LLM phrases.
    Returns up to MAX_SEARCH_QUERIES; never empty when post_text is non-empty.
    """
    if not post_text or not post_text.strip():
        return []
    text = post_text.strip()
    # 1) Always use start of post as first query (literal match)
    snippet = " ".join(text[:SEARCH_POST_SNIPPET_LEN].split())
    if len(snippet) < 10:
        snippet = text[:80].strip() or "post"
    robust: List[str] = [snippet]

    # 2) N-gram phrases from post (3–5 word chunks) for extra coverage
    words = re.findall(r"\b[a-zA-Z0-9]{2,}\b", text)
    stop = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "to", "of", "and", "in", "on", "at", "for", "with", "this", "that", "it", "its"}
    for n in (5, 4, 3):
        for i in range(max(0, len(words) - n)):
            phrase = " ".join(words[i : i + n])
            if phrase and phrase not in robust and len(phrase) >= 8:
                robust.append(phrase)
                if len(robust) >= 5:
                    break
        if len(robust) >= 5:
            break

    # 3) Word-based fallback (significant words)
    candidates = [w for w in words if w.lower() not in stop][:25]
    for w in candidates:
        if w not in robust and len(robust) < MAX_SEARCH_QUERIES:
            robust.append(w)

    if not OPENAI_API_KEY:
        return robust[:MAX_SEARCH_QUERIES]

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY.strip(), timeout=API_TIMEOUT_SECONDS)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": KEYWORD_EXTRACTION_SYSTEM},
                {"role": "user", "content": KEYWORD_EXTRACTION_USER_TEMPLATE.format(post_text=text[:2000])},
            ],
            max_tokens=200,
            temperature=0,
        )
        raw = (resp.choices[0].message.content or "").strip()
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        for ln in lines:
            ln = re.sub(r"^[\d\-*.)]+\s*", "", ln).strip()
            if ln and ln not in robust and len(ln) >= 3:
                robust.append(ln[:80])
                if len(robust) >= MAX_SEARCH_QUERIES:
                    break
    except Exception as e:
        logger.warning("Keyword extraction failed: %s", e)

    return robust[:MAX_SEARCH_QUERIES] if robust else [text[:80] or "post"]


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
        keywords = _extract_keywords(req.text or "")
        if not keywords:
            keywords = [(req.text or "post")[:80]]
    except Exception as e:
        logger.warning("Keyword extraction error: %s", e)
        keywords = [(req.text or "post")[:80]] if req.text else ["post"]

    # Parallel: scrapers + author feed for bot score (Bluesky handle)
    reddit_task = asyncio.create_task(scrape_reddit_async(keywords))
    bluesky_task = asyncio.create_task(search_bluesky(keywords, exclude_url=req.url))
    author_feed_task: asyncio.Task | None = None
    if BOT_SCORE_ENABLED and (req.author or "").strip():
        author_feed_task = asyncio.create_task(
            get_author_feed_async((req.author or "").strip().lstrip("@"), BOT_SCORE_POSTS_LIMIT)
        )

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
    # Only consider posts from the last N days
    cutoff = (datetime.now(timezone.utc) - timedelta(days=CORPUS_DAYS_LIMIT)).isoformat()
    corpus = [p for p in corpus if (p.timestamp or "") >= cutoff]
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
        bot_score = await _get_bot_score(author_feed_task)
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
            bot_score=bot_score,
            errors=errors,
            warnings=warnings,
        )

    # Provenance graph (evidence-based): relevance filter, edge formation, path finding
    provenance_graph: ProvenanceGraph | None = None
    origin: OriginCard
    timeline: list[TimelineEntry]
    diff: DiffResult
    mutations_log: list[MutationLogEntry] = []

    try:
        provenance_graph = build_provenance_graph(
            corpus,
            req.text or "",
            req.url or "",
            req.timestamp or "",
            req.author or "",
        )
    except Exception as e:
        logger.warning("Provenance graph failed: %s", e)
        provenance_graph = None

    if provenance_graph and len(provenance_graph.main_path) >= 2 and len(provenance_graph.edges) >= MIN_EDGES_TO_USE_GRAPH:
        # Use new graph-based provenance (origin + timeline from graph path)
        origin, timeline = graph_to_origin_and_timeline(provenance_graph)
        if not origin:
            origin = OriginCard(
                text=req.text[:500] if req.text else "",
                source="bluesky",
                community="bluesky",
                timestamp=req.timestamp or "",
                url=req.url or "",
            )
        diff = narrative_diff(origin.text, req.text or "")
        mutation_summary = timeline[0].mutation_note if timeline else ""
        # Build mutations_log from graph edges on main path
        trace_id = str(uuid.uuid4())
        path = provenance_graph.main_path
        edge_map = {(e.source, e.target): e for e in provenance_graph.edges}
        for i in range(1, len(path)):
            e = edge_map.get((path[i - 1], path[i]))
            if e:
                for m in e.mutations:
                    mutations_log.append(MutationLogEntry(
                        trace_id=trace_id,
                        agent_id=m.agent_id,
                        mutation_type=m.type,
                        source_span=m.source_span,
                        target_span=m.target_span,
                        confidence=m.confidence,
                        evidence_corpus_indices=[],
                        abstained=False,
                    ))
                    append_mutation(trace_id, m.agent_id, m.type, m.source_span, m.target_span, m.confidence, [])
    else:
        # Fallback: cluster + provenance (legacy) or abstention when graph evidence weak
        if provenance_graph and len(provenance_graph.main_path) >= 2 and len(provenance_graph.edges) < max(1, MIN_EDGES_TO_USE_GRAPH):
            warnings.append("Provenance uncertain: few edges; showing fallback.")
        clusters = cluster_posts(corpus)
        if not clusters:
            clusters = [Cluster(indices=list(range(len(corpus))), earliest_timestamp=corpus[0].timestamp)]
        origin, timeline = build_timeline(corpus, clusters, req.text or "")
        diff = narrative_diff(origin.text, req.text or "")
        mutation_summary = timeline[0].mutation_note if timeline else ""
        # Mutation log from diff (legacy)
        trace_id = str(uuid.uuid4())
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

    # Structural rules (including origin-in-corpus validation)
    rule_checks = run_structural_rules(corpus, timeline, total_sources, origin_text=origin.text or "")

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

    # User summary (primary for extension)
    user_summary = build_user_summary(
        origin, timeline, diff, rule_checks, semantic_verifications, total_sources, errors, warnings, mutations_log=mutations_log
    )

    # Same-message spread detector: many accounts sharing the same message (neutral label)
    same_message_spread: SameMessageSpread | None = None
    if provenance_graph and provenance_graph.propagation_authors and len(provenance_graph.propagation_authors) >= PROPAGATION_ACCOUNTS_ALERT_THRESHOLD:
        same_message_spread = SameMessageSpread(
            detected=True,
            account_count=len(provenance_graph.propagation_authors),
            message_snippet=(provenance_graph.propagated_message or "")[:120],
            accounts=list(provenance_graph.propagation_authors),
        )
        if user_summary and user_summary.one_liner:
            user_summary = user_summary.model_copy(
                update={"one_liner": user_summary.one_liner + f" Same message across {len(provenance_graph.propagation_authors)} accounts."}
            )
    elif provenance_graph and (provenance_graph.propagated_message or provenance_graph.propagation_node_indices):
        # Always surface propagation in one-liner when we have graph + any propagation data
        n_nodes = len(provenance_graph.propagation_node_indices)
        n_acc = len(provenance_graph.propagation_authors or [])
        if user_summary and user_summary.one_liner and "Same message across" not in user_summary.one_liner:
            user_summary = user_summary.model_copy(
                update={"one_liner": user_summary.one_liner + f" Message: {n_nodes} post(s), {n_acc} account(s)."}
            )
    if same_message_spread is None:
        same_message_spread = SameMessageSpread(
            detected=False,
            account_count=len(provenance_graph.propagation_authors) if provenance_graph else 0,
            message_snippet=(provenance_graph.propagated_message or "")[:120] if provenance_graph else "",
            accounts=list(provenance_graph.propagation_authors) if provenance_graph else [],
        )

    bot_score = await _get_bot_score(author_feed_task)
    return ProvenanceResponse(
        user_summary=user_summary,
        origin=origin,
        timeline=timeline,
        diff=diff,
        reply_draft=reply,
        total_sources_checked=total_sources,
        current_post_url=req.url or "",
        provenance_graph=provenance_graph,
        rule_checks=rule_checks,
        semantic_verifications=semantic_verifications,
        mutations_log=mutations_log,
        same_message_spread=same_message_spread,
        bot_score=bot_score,
        errors=errors,
        warnings=warnings,
    )


if __name__ == "__main__":
    import uvicorn
    from config import BACKEND_HOST, BACKEND_PORT
    uvicorn.run(app, host=BACKEND_HOST, port=BACKEND_PORT)
