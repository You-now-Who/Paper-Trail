"""
audit/mutation_log.py — Append-only mutation log (JSONL).
Invariant: Never overwrite; append one JSON object per line. Never throws.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from config import MUTATION_LOG_PATH

logger = logging.getLogger(__name__)


def append_mutation(trace_id: str, agent_id: str, mutation_type: str, source_span: str, target_span: str, confidence: float, evidence_indices: list[int], abstained: bool = False) -> None:
    """Append one mutation entry to the log. Creates directory/file if needed."""
    try:
        MUTATION_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "trace_id": trace_id,
            "agent_id": agent_id,
            "mutation_type": mutation_type,
            "source_span": source_span[:500],
            "target_span": target_span[:500],
            "confidence": confidence,
            "evidence_corpus_indices": evidence_indices,
            "abstained": abstained,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(MUTATION_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Mutation log append failed: %s", e)
