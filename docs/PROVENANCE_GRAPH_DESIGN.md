# Provenance Graph — Mutation Detection System Design

## Problem Statement

The current system has three critical flaws:

1. **False positives**: Search returns posts that share keywords but are not derived from each other (e.g. two posts about "Iran" that are unrelated).
2. **Linear chain assumption**: We force Origin → v1 → v2 → … → Current. Reality: narratives branch (one post inspires many), merge (multiple sources combine), and evolve in parallel.
3. **Weak mutation detection**: We cluster by topic similarity and assume chronological order implies derivation. There is no evidence that A actually inspired B.

---

## Design Overview

Replace the **linear timeline** with a **provenance graph** where:

- **Nodes** = posts (corpus + current post).
- **Edges** = "B derived from A" with evidence and confidence.
- **Multiple parents** = merging (B combines A₁ and A₂).
- **Multiple children** = branching (A inspires B₁ and B₂).
- **Abstention** = if no strong evidence, return "no clear provenance" instead of fabricating a chain.

---

## 1. Provenance Graph (DAG)

### Graph Structure

```
Nodes:  N = {corpus posts} ∪ {current post}
Edges: E ⊆ N × N, directed, (A, B) ∈ E ⟺ "B derived from A"

Constraints:
- Temporal: A.timestamp < B.timestamp (A must be earlier)
- Evidence: edge has evidence_score ≥ θ_edge
- No cycles: enforce DAG (topological order exists)
```

### Edge Semantics

An edge A → B means: *B was influenced by or derived from A*, with supporting evidence.

Edges are **not** implied by:

- Same topic only (semantic similarity)
- Chronological order alone

Edges **require** at least one of:

- Quote overlap (exact or near-exact substring)
- Distinctive phrase reuse (rare n-grams shared)
- Structural similarity + high semantic similarity (same narrative arc)

---

## 2. Edge Formation (When Do We Add A → B?)

### Step 1: Candidate Pairs

Only consider (A, B) where:

- A.timestamp < B.timestamp
- A, B both in corpus ∪ current
- Semantic similarity sim(A, B) ≥ θ_rel (e.g. 0.7) — filters totally unrelated posts

### Step 2: Evidence Scoring

For each candidate (A, B), compute:

| Evidence Type        | Description                               | Score 0–1                          |
|----------------------|-------------------------------------------|------------------------------------|
| **Quote overlap**    | Long substring of A appears in B          | Jaccard or % of A quoted in B      |
| **Distinctive n-grams** | Rare phrases (e.g. 4–6 words) shared  | # shared / min(|A|, |B|) in phrase space |
| **Paraphrase**       | Embedding similarity of aligned spans     | Cosine sim of best span alignment  |
| **Structure**        | Same narrative structure (intro, claims, conclusion) | LLM or template match      |

### Step 3: Combined Edge Score

```
edge_score(A → B) = w₁·quote + w₂·ngram + w₃·paraphrase + w₄·structure
```

We add edge A → B only if `edge_score ≥ θ_edge` (e.g. 0.5).

### Step 4: Sparsification

- Prefer edges with **strongest evidence**.
- Enforce DAG: if adding (A, B) creates a cycle, skip.
- Limit fan-out: cap number of out-edges per node to avoid hub nodes.

---

## 3. Relevance Filtering (Reducing False Positives)

Before building the graph:

1. **Relevance to current post**:  
   For each corpus post C, require `sim(C, current) ≥ θ_relevance` (e.g. 0.65).  
   Drop posts below this threshold.

2. **Minimal corpus size**:  
   If < N posts pass relevance, return "no clear provenance" or lower confidence.

3. **Query expansion**:  
   Use LLM or embeddings to expand search phrases beyond raw keywords so we retrieve more on-topic posts.

---

## 4. Path Finding (What to Show)

Given current post **C** and graph **G**:

1. **Roots**: Nodes with no in-edges (or earliest in each connected component).
2. **Paths**: All simple paths from roots to C.
3. **Main path**: Path with highest geometric mean of edge scores.
4. **Alternative paths**: Other paths with score above a threshold.

### Timeline Derivation

- **Primary timeline** = nodes along the main path, in topological order.
- **Branching** = if C has multiple in-edges, show "merged from [A₁, A₂, …]".
- **Confidence** = product of edge scores along the path; cap at "low" if any edge is weak.

---

## 5. Mutation Detection (Per Edge)

For each edge A → B, run **mutation detectors**:

| Detector       | Input            | Output                          | Evidence                             |
|----------------|------------------|---------------------------------|--------------------------------------|
| **Quote reuse**| Spans from A in B| `{type: quote_reuse, spans, conf}` | Exact/near substring match           |
| **Quote edit** | A quote vs B variant | `{type: quote_edit, orig, edited}` | Levenshtein, edit distance           |
| **Paraphrase** | A span vs B span | `{type: paraphrase, conf}`      | Embedding cosine, n-gram overlap     |
| **Attribution**| "X said" in A vs B | `{type: attribution_change}`   | Named-entity / attribution patterns  |
| **Add/remove** | Facts in A vs B  | `{type: fact_added, fact_removed}` | LLM or NER with span linking        |

Each detector returns **evidence spans** (source_span, target_span) or **ABSTAIN** if no evidence.

Mutations are attached to the edge; they explain *how* B changed relative to A.

---

## 6. Abstention and Confidence

- **No edges into current post**: Return "No clear provenance found" and low confidence.
- **Weak path** (any edge < θ_edge): Cap confidence at "medium"; show "uncertain derivation".
- **Multiple strong paths**: Show primary path and mention "alternative sources" in the report.

---

## 7. Pipeline (High Level)

```
1. Scrapers → corpus (Reddit + Bluesky)
2. Relevance filter → drop posts with sim(post, current) < θ_relevance
3. Embed all posts + current
4. For each pair (A, B) with A.timestamp < B.timestamp:
   - Compute evidence scores (quote, ngram, paraphrase, structure)
   - If edge_score ≥ θ_edge and no cycle: add edge A → B
5. Path finding: roots → current, rank paths by score
6. For each edge on main path: run mutation detectors
7. Build timeline from main path nodes; attach mutation notes
8. Diff: origin (first node on path) vs current
9. Synthesis: UserSummary + provenance graph for report
```

---

## 8. Data Structures

```python
class ProvenanceNode:
    index: int          # corpus index or -1 for current
    text: str
    source: str
    community: str
    timestamp: str
    url: str

class ProvenanceEdge:
    source: int         # node index
    target: int
    evidence_score: float
    evidence_types: list[str]  # ["quote_overlap", "paraphrase", ...]
    mutations: list[MutationRecord]

class MutationRecord:
    type: str           # quote_reuse, quote_edit, paraphrase, attribution_change, fact_added, fact_removed
    source_span: str
    target_span: str
    confidence: float
    agent_id: str

class ProvenanceGraph:
    nodes: list[ProvenanceNode]
    edges: list[ProvenanceEdge]
    main_path: list[int]        # node indices from root to current
    alternative_paths: list[list[int]]
```

---

## 9. Implementation Phases

### Phase 1: Relevance Filter + Edge Pruning
- Filter corpus by `sim(post, current) ≥ θ_relevance`
- Compute pair-wise evidence (quote overlap, n-gram) for temporal pairs
- Add edges only when evidence exceeds threshold
- Output: graph with edges, no path finding yet

### Phase 2: Path Finding
- Identify roots and all paths to current
- Rank paths by edge score
- Derive timeline from main path

### Phase 3: Mutation Detectors
- Quote reuse (substring / Jaccard)
- Paraphrase (embedding alignment)
- Attach mutations to edges

### Phase 4: Integration
- Replace current clustering → provenance pipeline with graph pipeline
- Update report to show graph (branching/merging)
- Abstention when no strong path

---

## 10. Thresholds (Tunable)

| Parameter       | Suggested | Purpose                          |
|----------------|-----------|-----------------------------------|
| θ_relevance    | 0.65      | Min sim to current to keep post  |
| θ_edge         | 0.50      | Min evidence to add edge         |
| θ_quote        | 0.3       | Min quote overlap for quote type |
| CLUSTER_SIMILARITY | 0.82  | Keep for pre-filter clustering?  |
| MAX_PATH_LENGTH| 10        | Cap path length                  |

---

## Summary

| Current Problem        | Design Solution                                |
|------------------------|-------------------------------------------------|
| Random events          | Relevance filter + evidence-based edges         |
| Linear chain           | Provenance graph (DAG) with branching/merging   |
| Weak mutation detection| Quote overlap, n-gram, paraphrase, attribution  |
| No evidence            | Every edge has evidence_score; abstain if weak  |
