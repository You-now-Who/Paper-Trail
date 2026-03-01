"""
agents/bot_score.py — Heuristic bot score from recent post timestamps and text.
Uses last N posts: inter-post interval regularity, posting rate, and post-length uniformity.
Returns 0–1 (higher = more bot-like) and a short signal string.
"""

from __future__ import annotations

import statistics
from datetime import datetime, timezone
from typing import Any

def _parse_ts(ts: str) -> float:
    """Parse ISO timestamp to Unix seconds."""
    try:
        s = (ts or "").replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.timestamp()
    except Exception:
        return 0.0


def compute_bot_score(recent_posts: list[dict[str, Any]]) -> tuple[float, str]:
    """
    Compute a 0–1 bot-likelihood score from recent posts.
    Each item in recent_posts should have "timestamp" (ISO str) and "text" (str).
    Returns (score, signal) where signal is a one-liner explaining the main signal.
    """
    if not recent_posts or len(recent_posts) < 2:
        return (0.0, "Not enough posts to score")

    # Sort by time ascending (oldest first)
    posts = sorted(
        [p for p in recent_posts if p.get("timestamp")],
        key=lambda p: _parse_ts(p["timestamp"]),
    )
    if len(posts) < 2:
        return (0.0, "Not enough posts to score")

    scores: list[float] = []
    signals: list[str] = []

    # 1) Inter-post interval regularity: low variance/mean ratio = very regular = bot-like
    times = [_parse_ts(p["timestamp"]) for p in posts]
    intervals: list[float] = []
    for i in range(1, len(times)):
        delta = times[i] - times[i - 1]
        if delta > 0:
            intervals.append(delta)
    if intervals:
        mean_i = statistics.mean(intervals)
        if mean_i > 0:
            try:
                std_i = statistics.stdev(intervals)
            except Exception:
                std_i = 0.0
            # Coefficient of variation: low = very regular
            cv = std_i / mean_i if mean_i else 1.0
            # Regularity score: low CV -> high bot score (capped so 0.1 CV -> ~0.9)
            regularity = max(0.0, 1.0 - min(2.0, cv))
            scores.append(regularity)
            if regularity > 0.6:
                signals.append("very regular posting times")

    # 2) Posting rate: very high posts-per-day suggests automation
    span_seconds = max(times) - min(times) if len(times) >= 2 else 1.0
    span_days = span_seconds / 86400.0 or 0.001
    posts_per_day = len(posts) / span_days
    if posts_per_day > 20:
        rate_score = min(1.0, (posts_per_day - 20) / 80)  # 100/day -> 1.0
        scores.append(rate_score)
        signals.append(f"high posting rate ({posts_per_day:.0f}/day)")
    elif posts_per_day > 10:
        rate_score = 0.3 + 0.3 * min(1.0, (posts_per_day - 10) / 10)
        scores.append(rate_score)
        signals.append(f"elevated posting rate ({posts_per_day:.0f}/day)")

    # 3) Post length uniformity: similar length every time can indicate templates
    lengths = [len((p.get("text") or "").strip()) for p in posts]
    if len(lengths) >= 3:
        try:
            mean_l = statistics.mean(lengths)
            std_l = statistics.stdev(lengths)
            if mean_l > 10:
                cv_len = std_l / mean_l
                if cv_len < 0.3:  # very uniform length
                    uniformity = 1.0 - (cv_len / 0.3)
                    scores.append(uniformity * 0.5)  # cap contribution
                    signals.append("very similar post lengths")
        except Exception:
            pass

    if not scores:
        return (0.0, "No strong bot signals")

    # Combined: weighted average, clamp 0–1
    combined = sum(scores) / len(scores) if scores else 0.0
    combined = max(0.0, min(1.0, combined))
    signal = "; ".join(signals[:2]) if signals else "pattern-based score"
    return (round(combined, 3), signal)
