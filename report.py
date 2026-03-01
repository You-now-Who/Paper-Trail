"""
report.py — Generate full HTML report with graphs, nodes, and all reasoning.
Invariant: Accepts JSON from ProvenanceResponse; outputs standalone HTML with vis-network graph.
Tailwind + orange/black theme + animations. Compact timeline (no full text).
"""

from __future__ import annotations

import html
import json
from typing import Any


def _escape(s: str) -> str:
    return html.escape(s or "", quote=True)


def generate_report(data: dict[str, Any]) -> str:
    """
    Generate full HTML report. data = ProvenanceResponse serialized to dict.
    Tailwind CDN, orange/black theme, animations, compact timeline.
    """
    us = data.get("user_summary") or {}
    origin = data.get("origin") or {}
    timeline = data.get("timeline") or []
    diff = data.get("diff") or {}
    reply = data.get("reply_draft") or ""
    rule_checks = data.get("rule_checks") or []
    semantic_verifications = data.get("semantic_verifications") or []
    mutations_log = data.get("mutations_log") or []
    errors = data.get("errors") or []
    warnings = data.get("warnings") or []
    current_post_url = data.get("current_post_url") or ""
    total_sources = data.get("total_sources_checked", 0)

    # Build provenance graph nodes
    nodes: list[dict] = []
    edges: list[dict] = []
    node_id = 0

    origin_url = origin.get("url") or ""
    origin_label = f"Origin ({origin.get('source', '')} · {origin.get('community', '')})"
    nodes.append({
        "id": node_id,
        "label": origin_label[:40] + "…" if len(origin_label) > 40 else origin_label,
        "title": _escape((origin.get("text") or "")[:200]),
        "url": origin_url,
        "group": "origin",
    })
    prev_id = node_id
    node_id += 1

    for i, te in enumerate(timeline):
        te_url = te.get("url") or ""
        te_label = f"v{i+1} ({te.get('source', '')} · {te.get('community', '')})"
        nodes.append({
            "id": node_id,
            "label": te_label[:40] + "…" if len(te_label) > 40 else te_label,
            "title": _escape((te.get("text") or "")[:200]),
            "url": te_url,
            "group": "timeline",
        })
        edges.append({"from": prev_id, "to": node_id, "label": _escape((te.get("mutation_note") or "")[:50])})
        prev_id = node_id
        node_id += 1

    nodes.append({
        "id": node_id,
        "label": "Current post",
        "title": "The post you traced",
        "url": current_post_url,
        "group": "current",
    })
    edges.append({"from": prev_id, "to": node_id})
    graph_data = json.dumps({"nodes": nodes, "edges": edges})

    conf = us.get("confidence", "medium")
    badge_class = f"px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider " + {
        "low": "bg-red-500/20 text-red-400",
        "medium": "bg-amber-500/20 text-amber-400",
        "high": "bg-emerald-500/20 text-emerald-400",
    }.get(conf, "bg-amber-500/20 text-amber-400")

    # Compact timeline: stepper without full text
    timeline_html = ""
    for i, te in enumerate(timeline):
        note = te.get("mutation_note") or ""
        url = te.get("url") or ""
        timeline_html += f"""
    <div class="flex gap-4 animate-fade-in" style="animation-delay: {(i+1)*50}ms">
      <div class="flex flex-col items-center">
        <div class="w-10 h-10 rounded-full bg-amber-500/20 text-amber-400 flex items-center justify-center font-bold text-sm shrink-0">{i+1}</div>
        {f'<div class="w-0.5 flex-1 bg-amber-500/30 min-h-4"></div>' if i < len(timeline) - 1 else ''}
      </div>
      <div class="pb-6 flex-1">
        <div class="text-zinc-400 text-sm">{_escape(te.get("source", ""))} · {_escape(te.get("community", ""))} · {_escape(te.get("timestamp", "")[:10])}</div>
        {f'<p class="text-zinc-500 italic text-sm mt-1">{_escape(note)}</p>' if note else ''}
        {f'<a href="{_escape(url)}" target="_blank" rel="noopener" class="inline-flex items-center gap-2 mt-2 px-3 py-1.5 rounded-lg bg-amber-500/20 text-amber-400 text-sm font-medium hover:bg-amber-500/30 transition-colors">View post →</a>' if url else ''}
      </div>
    </div>"""

    rule_rows = "".join(
        f'<tr class="border-b border-zinc-800/50 hover:bg-zinc-900/50 transition-colors"><td class="py-3 px-4 text-zinc-300">{_escape(rc.get("rule_id", ""))}</td><td class="py-3 px-4"><span class="{"text-emerald-400" if rc.get("passed") else "text-red-400"}">{"Pass" if rc.get("passed") else "Fail"}</span></td><td class="py-3 px-4 text-zinc-500 text-sm">{_escape(rc.get("detail", ""))}</td></tr>'
        for rc in rule_checks
    )

    sv_rows = ""
    for sv in semantic_verifications:
        c = sv.get("confidence", 0)
        pct = int(c * 100)
        color = "bg-emerald-500" if c >= 0.75 else "bg-amber-500" if c >= 0.5 else "bg-red-500"
        sv_rows += f'<tr class="border-b border-zinc-800/50"><td class="py-3 px-4 text-zinc-300 max-w-xs truncate">{_escape((sv.get("claim") or "")[:120])}</td><td class="py-3 px-4"><div class="h-2 w-24 rounded-full bg-zinc-800 overflow-hidden"><div class="h-full rounded-full {color} transition-all duration-500" style="width:{pct}%"></div></div><span class="text-zinc-500 text-sm ml-2">{pct}%</span></td><td class="py-3 px-4 text-zinc-500 text-sm">{_escape(sv.get("method", ""))}</td></tr>'

    mut_rows = "".join(
        f'<tr class="border-b border-zinc-800/50"><td class="py-3 px-4 text-amber-400">{_escape(m.get("agent_id", ""))}</td><td class="py-3 px-4 text-zinc-400">{_escape(m.get("mutation_type", ""))}</td><td class="py-3 px-4 text-zinc-500 max-w-[150px] truncate">{_escape((m.get("source_span") or "")[:60])}</td><td class="py-3 px-4 text-zinc-500 max-w-[150px] truncate">{_escape((m.get("target_span") or "")[:60])}</td><td class="py-3 px-4 text-zinc-400">{int(m.get("confidence", 0)*100)}%</td></tr>'
        for m in mutations_log
    )

    diff_removed = "".join(f'<span class="inline-block px-2 py-1 rounded-md bg-red-500/20 text-red-400 text-sm mr-2 mb-2">− {_escape(p)}</span>' for p in (diff.get("removed") or []))
    diff_added = "".join(f'<span class="inline-block px-2 py-1 rounded-md bg-emerald-500/20 text-emerald-400 text-sm mr-2 mb-2">+ {_escape(p)}</span>' for p in (diff.get("added") or []))

    origin_link = f'<a href="{_escape(origin.get("url", ""))}" target="_blank" rel="noopener" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/20 text-amber-400 text-sm font-medium hover:bg-amber-500/30 transition-colors">View post →</a>' if origin.get("url") else ""

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Paper Trail — Full Report</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
  <style>
    @keyframes fadeIn {{
      from {{ opacity: 0; transform: translateY(10px); }}
      to {{ opacity: 1; transform: translateY(0); }}
    }}
    .animate-fade-in {{
      animation: fadeIn 0.4s ease-out forwards;
      opacity: 0;
    }}
    body {{ font-family: system-ui, -apple-system, sans-serif; }}
  </style>
  <script>
    tailwind.config = {{
      theme: {{
        extend: {{
          colors: {{
            zinc: {{ 950: '#0a0a0a' }}
          }}
        }}
      }}
    }}
  </script>
</head>
<body class="bg-zinc-950 text-zinc-100 min-h-screen">
  <div class="max-w-4xl mx-auto px-6 py-12">
    <header class="mb-12 animate-fade-in">
      <h1 class="text-3xl font-bold bg-gradient-to-r from-amber-400 to-amber-600 bg-clip-text text-transparent">Paper Trail</h1>
      <p class="text-zinc-500 mt-1">Full provenance report</p>
    </header>

    <section class="mb-12 animate-fade-in" style="animation-delay: 50ms">
      <div class="flex flex-wrap items-center gap-4 p-6 rounded-2xl bg-zinc-900/50 border border-zinc-800 shadow-xl">
        <p class="text-lg font-medium text-zinc-100 flex-1">{_escape(us.get("one_liner", ""))}</p>
        <span class="{badge_class}">{_escape(str(conf))}</span>
        <span class="text-zinc-500 text-sm">Sources: {total_sources}</span>
      </div>
    </section>

    <section class="mb-12 animate-fade-in" style="animation-delay: 100ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Provenance Graph</h2>
      <p class="text-zinc-500 text-sm mb-3">Click a node to open the post</p>
      <div id="provenance-graph" class="w-full h-[420px] rounded-2xl border border-zinc-800 bg-zinc-900/50 overflow-hidden shadow-xl"></div>
    </section>

    <section class="mb-12 animate-fade-in" style="animation-delay: 150ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Timeline</h2>
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 shadow-xl">
        <div class="flex gap-4">
          <div class="flex flex-col items-center">
            <div class="w-10 h-10 rounded-full bg-amber-500 text-zinc-950 flex items-center justify-center font-bold text-sm shrink-0">O</div>
            <div class="w-0.5 flex-1 bg-amber-500/30 min-h-4"></div>
          </div>
          <div class="pb-6 flex-1">
            <div class="text-zinc-400 text-sm">{_escape(origin.get("source", ""))} · {_escape(origin.get("community", ""))} · {_escape((origin.get("timestamp") or "")[:10])}</div>
            <p class="text-zinc-500 text-sm mt-1">Origin</p>
            {origin_link}
          </div>
        </div>
        {timeline_html}
        <div class="flex gap-4">
          <div class="flex flex-col items-center">
            <div class="w-10 h-10 rounded-full bg-red-500/20 text-red-400 flex items-center justify-center font-bold text-sm shrink-0">C</div>
          </div>
          <div class="pb-2 flex-1">
            <div class="text-zinc-400 text-sm">Current post</div>
            {f'<a href="{_escape(current_post_url)}" target="_blank" rel="noopener" class="inline-flex items-center gap-2 mt-2 px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 text-sm font-medium hover:bg-red-500/30 transition-colors">View post →</a>' if current_post_url else ''}
          </div>
        </div>
      </div>
    </section>

    <section class="mb-12 animate-fade-in" style="animation-delay: 200ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Rule Checks</h2>
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/50 overflow-hidden shadow-xl">
        <table class="w-full"><thead><tr class="text-left text-zinc-500 text-xs uppercase tracking-wider"><th class="py-3 px-4">Rule</th><th class="py-3 px-4">Result</th><th class="py-3 px-4">Detail</th></tr></thead><tbody>{rule_rows}</tbody></table>
      </div>
    </section>

    <section class="mb-12 animate-fade-in" style="animation-delay: 250ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Semantic Verifications</h2>
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/50 overflow-hidden shadow-xl">
        <table class="w-full"><thead><tr class="text-left text-zinc-500 text-xs uppercase tracking-wider"><th class="py-3 px-4">Claim</th><th class="py-3 px-4">Confidence</th><th class="py-3 px-4">Method</th></tr></thead><tbody>{sv_rows}</tbody></table>
      </div>
    </section>

    <section class="mb-12 animate-fade-in" style="animation-delay: 300ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Mutation Log</h2>
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/50 overflow-hidden shadow-xl overflow-x-auto">
        <table class="w-full min-w-[500px]"><thead><tr class="text-left text-zinc-500 text-xs uppercase tracking-wider"><th class="py-3 px-4">Agent</th><th class="py-3 px-4">Type</th><th class="py-3 px-4">Source</th><th class="py-3 px-4">Target</th><th class="py-3 px-4">Conf</th></tr></thead><tbody>{mut_rows}</tbody></table>
      </div>
    </section>

    <section class="mb-12 animate-fade-in" style="animation-delay: 350ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Origin</h2>
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 shadow-xl">
        <p class="text-zinc-400 text-sm">{_escape(origin.get("source", ""))} · {_escape(origin.get("community", ""))}</p>
        <p class="text-zinc-300 mt-3 whitespace-pre-wrap break-words max-h-32 overflow-y-auto text-sm">{_escape((origin.get("text") or "")[:500])}</p>
        {origin_link}
      </div>
    </section>
"""
    if diff.get("removed") or diff.get("added"):
        html_content += f"""
    <section class="mb-12 animate-fade-in" style="animation-delay: 400ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Diff (Origin → Current)</h2>
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 shadow-xl flex flex-wrap gap-2">
        {diff_removed}{diff_added}
      </div>
    </section>
"""
    if reply:
        html_content += f"""
    <section class="mb-12 animate-fade-in" style="animation-delay: 450ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Reply Draft</h2>
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 shadow-xl">
        <p class="text-zinc-300 whitespace-pre-wrap break-words">{_escape(reply)}</p>
      </div>
    </section>
"""
    if errors or warnings:
        html_content += f"""
    <section class="mb-12 animate-fade-in" style="animation-delay: 500ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Errors & Warnings</h2>
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/50 p-6 shadow-xl space-y-2">
        {''.join(f'<p class="text-red-400 text-sm">{_escape(e)}</p>' for e in errors)}
        {''.join(f'<p class="text-amber-400 text-sm">{_escape(w)}</p>' for w in warnings)}
      </div>
    </section>
"""

    html_content += f"""
    <script>
      const graphData = {graph_data};
      const container = document.getElementById("provenance-graph");
      const options = {{
        nodes: {{
          shape: "dot",
          size: 18,
          font: {{ size: 12, color: "#fafafa" }},
          borderWidth: 2,
        }},
        edges: {{ arrows: "to", color: "#52525b" }},
        groups: {{
          origin: {{ color: {{ background: "#f97316", border: "#fb923c" }} }},
          timeline: {{ color: {{ background: "#a16207", border: "#ca8a04" }} }},
          current: {{ color: {{ background: "#ef4444", border: "#f87171" }} }},
        }},
        physics: {{ enabled: true, barnesHut: {{ gravitationalConstant: -2500, springLength: 130 }} }},
      }};
      const nodes = new vis.DataSet(graphData.nodes);
      const edges = new vis.DataSet(graphData.edges);
      const network = new vis.Network(container, {{ nodes, edges }}, options);
      network.on("click", function(params) {{
        if (params.nodes.length && graphData.nodes[params.nodes[0]]?.url) {{
          window.open(graphData.nodes[params.nodes[0]].url, "_blank");
        }}
      }});
    </script>
  </div>
</body>
</html>
"""
    return html_content
