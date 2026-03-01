# Paper Trail — System Design v2

## Overview

This design extends the MVP into a **multi-agent provenance system** with:
- **Tiered output**: minimal user-facing summary vs. rich internal analytics
- **Scaled agents**: parallel mutation-detection agents, each with narrow scope
- **Hallucination detection**: evidence linking, confidence scoring, abstention
- **Rule-based analysis**: deterministic checks that LLMs cannot override
- **Structured mutation logging**: append-only audit trail for research and debugging
- **Graphs and visuals**: mathematically grounded provenance graphs for internal use

---

## 1. Tiered Output (User vs Internal)

### User-facing (Extension Panel)

**One sentence + confidence badge.** No timeline dump, no diff list, no reply draft unless explicitly requested.

| Field        | User sees                         | Internal has                               |
|-------------|------------------------------------|--------------------------------------------|
| Origin      | "Likely originated from r/X"       | Full OriginCard, source spans, URLs        |
| Mutation    | "Low / Medium / High confidence"   | Per-mutation log with agent IDs, evidence  |
| Diff        | Hidden                             | Full DiffResult, rule-based flags          |
| Reply       | Hidden (or "Copy reply" if asked)  | Full draft, provenance links               |
| Timeline    | Hidden                             | Full TimelineEntry[], mutation graph       |
| Evidence    | None                               | Spans, similarity scores, rule check results |

**Principle**: The user gets a quick, non-overwhelming answer. Researchers and debuggers get the full pipeline output via an internal API or log.

### API Response Shape

```python
# User-facing (sent to extension)
class UserSummary(BaseModel):
    one_liner: str              # "Likely from r/science. High confidence."
    confidence: Literal["low", "medium", "high"]
    origin_snippet: str         # Optional: first 100 chars of origin
    show_more_url: str | None   # Optional: link to internal dashboard

# Internal (logged, not sent to user)
class InternalTraceResult(BaseModel):
    user_summary: UserSummary
    origin: OriginCard
    timeline: list[TimelineEntry]
    diff: DiffResult
    reply_draft: str
    mutations: list[MutationLogEntry]   # New: structured mutation log
    rule_checks: list[RuleCheckResult]  # New: rule-based analysis results
    hallucination_flags: list[HallucinationFlag]  # New
    provenance_graph: ProvenanceGraph   # New: for visualization
```

---

## 2. Agent Architecture (Scaled)

### Agent Layers

```
┌─────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR (main.py)                        │
│  Scrapers → Corpus → Cluster → Route to agents → Synthesize      │
└─────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
┌───────────────┐         ┌───────────────────┐         ┌───────────────┐
│ STRUCTURAL    │         │ MUTATION AGENTS   │         │ SEMANTIC      │
│ RULES         │         │ (parallel)        │         │ VERIFIER      │
│ (runs first)  │         │                   │         │ (model-based) │
│               │         │ • Factual drift   │         │               │
│ • Timestamp   │         │ • Attribution     │         │ • Embeddings  │
│   order       │         │ • Sentiment shift │         │   (cosine)    │
│ • Corpus      │         │ • Quote manip     │         │ • LLM judge   │
│   valid       │         │ • Paraphrase      │         │   (optional)  │
└───────────────┘         └───────────────────┘         └───────────────┘
        │                           │                           │
        └───────────────────────────┼───────────────────────────┘
                                    ▼
                    ┌───────────────────────────────┐
                    │ SYNTHESIS AGENT               │
                    │ Merges outputs, applies       │
                    │ hallucination filters,        │
                    │ produces UserSummary          │
                    └───────────────────────────────┘
```

### Mutation Agents (Parallel)

Each agent is **narrow** and **evidence-bound**:

| Agent              | Role                          | Output                         | Evidence requirement        |
|--------------------|-------------------------------|--------------------------------|-----------------------------|
| `factual_drift`    | Detect added/removed facts    | `{type, span_origin, span_current, confidence}` | Span in corpus or abstain |
| `attribution`      | Detect "X said" → "Y said"    | Same                           | Attribution string in corpus|
| `sentiment_shift`  | Detect polarity change        | Same                           | Sentiment diff              |
| `quote_manip`      | Detect quote truncation/edit  | Same                           | Quote substring match       |
| `paraphrase`       | Detect semantic drift         | Same                           | Embedding similarity > θ    |

Agents run in parallel. Each **must** output either:
- A mutation with `source_span`, `target_span`, `confidence`
- Or `ABSTAIN` with a short reason (e.g. "No matching span in corpus")

### Hallucination Detection

- **Evidence linking**: Every LLM output (e.g. "mutation note", "diff phrase") must cite a corpus span or be flagged as `UNVERIFIED`.
- **Confidence scoring**: 0–1 per claim. Below threshold → demoted or suppressed from user summary.
- **Abstention**: Agents explicitly output `ABSTAIN` when evidence is weak; synthesis agent never fabricates a narrative from abstentions.
- **Cross-check**: Semantic verifier (model) scores each claim; low scores cap confidence. Structural rules override only invalid states (e.g. bad indices).

---

## 3. Structural Rules (Deterministic) + Semantic Verification (Model)

### Structural Rules Only

Rules are **deterministic** and **structural** — no semantic checks. Run before agents.

| Rule                     | Check                                      | Pass / Fail                |
|--------------------------|--------------------------------------------|----------------------------|
| `TIMESTAMP_ORDER`        | Timeline entries ordered by timestamp      | Pass / Fail                |
| `CORPUS_VALID`           | Corpus non-empty, indices in range         | Pass / Fail                |
| `OUTPUT_FORMAT`          | Outputs have required fields               | Pass / Fail                |

Failed structural rules reduce confidence and are logged. **Semantic checks** (quote in corpus, attribution match, etc.) use a prediction model instead.

### Semantic Verification (Model)

A **prediction model** replaces brittle semantic rules:

- **Input**: Claim (e.g. diff phrase, mutation note) + corpus
- **Output**: Confidence 0–1 that the claim has support in the corpus
- **Method**: Embedding cosine similarity (claim vs. corpus chunks) or LLM judge ("Does X appear, in any form, in the corpus?")
- **Existing models**: OpenAI `text-embedding-3-small` for embeddings; `gpt-4o-mini` for LLM-based verification

Below threshold → flag as unverified; synthesis caps confidence at `medium`.

---

## 4. Mutation Logging

### Schema

```python
class MutationLogEntry(BaseModel):
    trace_id: str                    # Unique per /trace call
    agent_id: str                    # factual_drift, attribution, etc.
    mutation_type: str               # e.g. "quote_truncation"
    source_span: str                 # Span in origin/corpus
    target_span: str                 # Span in current post
    confidence: float                # 0–1
    evidence_corpus_indices: list[int]  # Which RawPosts support this
    rule_check_ids: list[str]        # Rules that validated/invalidated
    abstained: bool                  # True if agent abstained
    timestamp: str                   # ISO
```

### Storage

- **Append-only log** (e.g. JSONL file or DB table)
- Queryable by `trace_id`, `agent_id`, `mutation_type`, `confidence`
- Used for: dashboards, research, debugging, tuning thresholds

---

## 5. Graphs and Visuals (Internal Only)

### Provenance Graph (DAG)

- **Nodes**: Posts (corpus + current). Each node = `(url, timestamp, source)`.
- **Edges**: Directed from origin → later. Edge weight = similarity (cosine) or mutation score.
- **Math**: Cosine similarity on embeddings; Jaccard on tokens; Levenshtein for exact spans.
- **Output**: JSON or GraphML for rendering (e.g. D3, NetworkX). Not sent to extension.

### Mutation Graph

- **Nodes**: Versions (timeline entries).
- **Edges**: Mutations with type labels (`factual_drift`, `quote_manip`, etc.) and confidence.
- **Visual**: Sankey-style flow or node-link. Confidence as edge thickness or color.

### Timeline with Confidence Bands

- X-axis: time. Y-axis: cumulative mutation "distance" (e.g. edit distance or semantic drift).
- Bands: ±1 std from mean confidence per agent. Math: well-defined aggregates.

### Clustering Visualization

- Existing `cluster_posts` uses cosine similarity. Expose:
  - Dendrogram (hierarchical) or
  - 2D projection (PCA/t-SNE/UMAP) of embeddings
- For internal dashboard only.

---

## 6. Implementation Phases

### Phase 1: Tiered Output + Mutation Log
- Add `UserSummary` to response; extension shows only that.
- Introduce `MutationLogEntry`; log mutations from existing diff/provenance agents.
- Append-only mutation log (JSONL).

### Phase 2: Structural Rules + Semantic Verifier
- Implement `TIMESTAMP_ORDER`, `CORPUS_VALID`.
- Implement semantic verifier: embeddings (cosine) or LLM for claim vs. corpus support.

### Phase 3: Scaled Mutation Agents
- Split current provenance/diff logic into narrow agents (factual_drift, attribution, quote_manip, etc.).
- Run in parallel; each outputs structured mutations or ABSTAIN.

### Phase 4: Hallucination Layer
- Evidence linking: require corpus span for every mutation.
- Confidence scoring and abstention; synthesis agent filters low-confidence outputs.

### Phase 5: Graphs + Internal Dashboard
- Provenance graph (DAG) and mutation graph as JSON.
- Optional: simple internal UI (e.g. Streamlit) for researchers.

---

## 7. File / Module Layout (Proposed)

```
Paper-Trail/
├── agents/
│   ├── cluster.py         # (existing)
│   ├── provenance.py      # (existing, may refactor)
│   ├── diff.py            # (existing, may split)
│   ├── reply.py           # (existing)
│   ├── structural_rules.py # NEW: TIMESTAMP_ORDER, CORPUS_VALID
│   ├── semantic_verifier.py # NEW: model-based claim verification
│   ├── mutations/         # NEW: narrow agents
│   │   ├── __init__.py
│   │   ├── factual.py
│   │   ├── attribution.py
│   │   ├── quote_manip.py
│   │   └── paraphrase.py
│   └── hallucination.py   # NEW: evidence + confidence
├── audit/
│   └── mutation_log.py    # Append-only mutation log (avoids shadowing stdlib logging)
├── graphs/
│   ├── provenance.py      # DAG builder
│   └── mutation_graph.py  # Mutation graph builder
├── schemas.py             # + UserSummary, MutationLogEntry, etc.
└── main.py                # Orchestrator wiring
```

---

## 8. Confidence Aggregation (Math)

User-facing confidence = `low | medium | high` derived from:

- Structural rule pass rate: `r = (passed_rules) / (total_rules)`
- Mutation confidence mean: `c = mean([m.confidence for m in mutations])`
- Hallucination flags: any `UNVERIFIED` claim → cap at `medium`

```
if r < 0.5 or any(unverified): return "low"
elif r >= 0.8 and c >= 0.7:   return "high"
else:                         return "medium"
```

Tunable via config.

---

## Summary

| Concern                | Approach                                              |
|------------------------|-------------------------------------------------------|
| Don't bombard user     | UserSummary only; full data internal/log              |
| Graphs & visuals       | DAG, mutation graph, clustering viz; internal only    |
| Strong reasoning       | Narrow agents, evidence linking, abstention           |
| Hallucination detection| Evidence spans, confidence, rule overrides            |
| Structural rules       | Deterministic (timestamp, corpus); semantic = model   |
| Scale of agents        | Parallel mutation agents; structured MutationLogEntry |
| Mutation logging       | Append-only JSONL; queryable by trace/agent/type      |
