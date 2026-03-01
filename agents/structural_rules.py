"""
agents/structural_rules.py — Deterministic structural checks only.
Invariant: No semantic checks (e.g. quote matching, attribution). Those use semantic_verifier.
Rules: TIMESTAMP_ORDER, CORPUS_VALID. Output RuleCheckResult. Never throws.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from schemas import RuleCheckResult

if TYPE_CHECKING:
    from schemas import RawPost, TimelineEntry


def check_timestamp_order(timeline: list["TimelineEntry"]) -> RuleCheckResult:
    """Verify timeline entries are ordered by timestamp ascending."""
    if not timeline:
        return RuleCheckResult(rule_id="TIMESTAMP_ORDER", passed=True, detail="Empty timeline")
    prev = ""
    for e in timeline:
        ts = (e.timestamp or "").strip()
        if prev and ts and ts < prev:
            return RuleCheckResult(rule_id="TIMESTAMP_ORDER", passed=False, detail=f"Out of order: {ts} before {prev}")
        if ts:
            prev = ts
    return RuleCheckResult(rule_id="TIMESTAMP_ORDER", passed=True, detail="Ordered ascending")


def check_corpus_valid(corpus: list["RawPost"], corpus_size: int) -> RuleCheckResult:
    """Verify corpus exists and indices would be in range."""
    if corpus_size == 0:
        return RuleCheckResult(rule_id="CORPUS_VALID", passed=True, detail="No corpus (expected for empty)")
    if len(corpus) == 0:
        return RuleCheckResult(rule_id="CORPUS_VALID", passed=False, detail="Corpus empty but corpus_size > 0")
    if corpus_size > len(corpus):
        return RuleCheckResult(rule_id="CORPUS_VALID", passed=False, detail=f"corpus_size {corpus_size} > len {len(corpus)}")
    return RuleCheckResult(rule_id="CORPUS_VALID", passed=True, detail=f"Corpus ok, size={len(corpus)}")


def run_structural_rules(
    corpus: list["RawPost"],
    timeline: list["TimelineEntry"],
    corpus_size: int,
) -> list[RuleCheckResult]:
    """Run all structural rules. Returns list of RuleCheckResult."""
    results: list[RuleCheckResult] = []
    results.append(check_corpus_valid(corpus, corpus_size))
    results.append(check_timestamp_order(timeline))
    return results
