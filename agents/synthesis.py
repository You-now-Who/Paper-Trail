"""
agents/synthesis.py — Build UserSummary from pipeline outputs.
Invariant: Takes origin, timeline, diff, rule_checks, semantic_verifications, mutations.
Outputs one_liner, confidence (low/medium/high). Never throws.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from config import (
    SEMANTIC_SIMILARITY_THRESHOLD,
    CONFIDENCE_LOW_THRESHOLD,
    CONFIDENCE_MEDIUM_THRESHOLD,
)
from schemas import UserSummary

if TYPE_CHECKING:
    from schemas import OriginCard, DiffResult, RuleCheckResult, SemanticVerificationResult, MutationLogEntry


def _aggregate_confidence(
    rule_checks: list["RuleCheckResult"],
    semantic_verifications: list["SemanticVerificationResult"],
    mutations_log: list["MutationLogEntry"] | None = None,
) -> str:
    """Return 'low' | 'medium' | 'high'. Rules + semantic + mutation confidence; unverified caps at medium."""
    r = 1.0
    if rule_checks:
        passed = sum(1 for rc in rule_checks if rc.passed)
        r = passed / len(rule_checks)

    c = 1.0
    if semantic_verifications:
        confs = [sv.confidence for sv in semantic_verifications]
        c = sum(confs) / len(confs) if confs else 0.5

    # Mutation confidence: mean of evidence-backed mutations
    if mutations_log:
        m_confs = [m.confidence for m in mutations_log]
        c = (c + sum(m_confs) / len(m_confs)) / 2 if m_confs else c

    # Unverified claim (below threshold) caps at medium
    unverified = bool(semantic_verifications) and any(sv.confidence < SEMANTIC_SIMILARITY_THRESHOLD for sv in semantic_verifications)

    if r < 0.5 or unverified:
        return "low"
    if r >= 0.8 and c >= CONFIDENCE_MEDIUM_THRESHOLD:
        return "high"
    return "medium"


def build_user_summary(
    origin: "OriginCard",
    timeline: list,
    diff: "DiffResult",
    rule_checks: list["RuleCheckResult"],
    semantic_verifications: list["SemanticVerificationResult"],
    total_sources: int,
    errors: list[str],
    warnings: list[str],
    mutations_log: list["MutationLogEntry"] | None = None,
) -> UserSummary:
    """Build minimal UserSummary for extension."""
    confidence = _aggregate_confidence(rule_checks, semantic_verifications, mutations_log)

    source = origin.source or "bluesky"
    community = origin.community or "bluesky"

    if total_sources == 0:
        one_liner = "No prior sources found. Low confidence."
    elif source == "reddit":
        one_liner = f"Likely from r/{community}. {confidence.capitalize()} confidence."
    else:
        one_liner = f"Likely from {source}. {confidence.capitalize()} confidence."

    if errors:
        one_liner += " (Some errors.)"
    elif warnings:
        one_liner += " (Limited sources.)"

    origin_snippet = (origin.text or "")[:100]
    if len(origin.text or "") > 100:
        origin_snippet += "…"

    return UserSummary(
        one_liner=one_liner,
        confidence=confidence,
        origin_snippet=origin_snippet,
        show_more=True,
    )
