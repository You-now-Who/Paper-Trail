"""
report.py — Generate full HTML report with graphs, nodes, and all reasoning.
Invariant: Accepts JSON from ProvenanceResponse; outputs standalone HTML with vis-network graph.
Tailwind + orange/black theme + animations. Compact timeline (no full text).
"""

from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any


def _format_timestamp(ts: str) -> str:
    """Format ISO timestamp to short label (e.g. Jan 15, 10:30)."""
    s = (ts or "").strip()
    if not s:
        return ""
    try:
        s_norm = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s_norm)
        return dt.strftime("%b %d, %H:%M")
    except (ValueError, TypeError):
        return s[:16] if len(s) >= 10 else s


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
    provenance_graph = data.get("provenance_graph") or {}
    same_message_spread = data.get("same_message_spread") or {}

    # Build provenance graph nodes: use provenance_graph if available (supports branching)
    nodes: list[dict] = []
    edges: list[dict] = []

    propagated_message = (provenance_graph.get("propagated_message") or "").strip()
    propagation_node_indices = set(provenance_graph.get("propagation_node_indices") or [])
    propagation_authors = provenance_graph.get("propagation_authors") or []

    # Confidence (uncertainty) for node coloring: same as badge (low/medium/high)
    conf = us.get("confidence", "medium")

    if provenance_graph.get("nodes") and provenance_graph.get("edges"):
        pg_nodes = provenance_graph.get("nodes", [])
        pg_edges = provenance_graph.get("edges", [])
        main_path = set(provenance_graph.get("main_path", []))
        for i, n in enumerate(pg_nodes):
            # Node color = uncertainty (confidence): low, medium, or high
            group = conf if conf in ("low", "medium", "high") else "medium"
            label = _format_timestamp(n.get("timestamp") or "")
            if n.get("is_current"):
                label = f"Current ({label})" if label else "Current post"
            kind = n.get("propagation_kind") or ""
            if kind:
                label = (label + f" [{kind}]")[:50]
            author = n.get("author") or ""
            title = _escape((n.get("text") or "")[:200])
            if author:
                title = f"@{_escape(author)}\n{title}"
            nodes.append({
                "id": i,
                "label": label + ("…" if len(label) >= 50 else ""),
                "title": title,
                "url": n.get("url") or "",
                "group": group,
            })
        for e in pg_edges:
            lab = f"{e.get('evidence_score', 0):.0%}" if e.get("evidence_score") else ""
            edges.append({
                "from": e.get("source", 0),
                "to": e.get("target", 0),
                "label": _escape(lab)[:30],
            })
    else:
        # Fallback: linear chain from origin + timeline
        node_id = 0
        origin_url = origin.get("url") or ""
        origin_label = _format_timestamp(origin.get("timestamp") or "")
        if origin_label:
            origin_label = f"Origin ({origin_label})"
        else:
            origin_label = f"Origin ({origin.get('source', '')} · {origin.get('community', '')})"
        nodes.append({
                "id": node_id,
                "label": origin_label[:40] + "…" if len(origin_label) > 40 else origin_label,
                "title": _escape((origin.get("text") or "")[:200]),
                "url": origin_url,
                "group": conf if conf in ("low", "medium", "high") else "medium",
            })
        prev_id = node_id
        node_id += 1
        for i, te in enumerate(timeline):
            te_url = te.get("url") or ""
            te_label = _format_timestamp(te.get("timestamp") or "")
            if te_label:
                te_label = f"v{i+1} ({te_label})"
            else:
                te_label = f"v{i+1} ({te.get('source', '')} · {te.get('community', '')})"
            nodes.append({
                "id": node_id,
                "label": te_label[:40] + "…" if len(te_label) > 40 else te_label,
                "title": _escape((te.get("text") or "")[:200]),
                "url": te_url,
                "group": conf if conf in ("low", "medium", "high") else "medium",
            })
            edges.append({"from": prev_id, "to": node_id, "label": _escape((te.get("mutation_note") or "")[:50])})
            prev_id = node_id
            node_id += 1
        nodes.append({
            "id": node_id,
            "label": "Current post",
            "title": "The post you traced",
            "url": current_post_url,
            "group": conf if conf in ("low", "medium", "high") else "medium",
        })
        edges.append({"from": prev_id, "to": node_id})

    graph_data = json.dumps({"nodes": nodes, "edges": edges})

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
        f'<tr class="border-b border-zinc-800/50"><td class="py-3 px-4 text-amber-400">{_escape(m.get("agent_id", ""))}</td><td class="py-3 px-4 text-zinc-400">{_escape(m.get("mutation_type", ""))}</td><td class="py-3 px-4 text-zinc-500 max-w-[180px] truncate" title="{_escape((m.get("source_span") or "")[:200])}">{_escape((m.get("source_span") or "")[:60] or "—")}</td><td class="py-3 px-4 text-zinc-500 max-w-[180px] truncate" title="{_escape((m.get("target_span") or "")[:200])}">{_escape((m.get("target_span") or "")[:60] or "—")}</td><td class="py-3 px-4 text-zinc-400">{int(m.get("confidence", 0)*100)}%</td></tr>'
        for m in mutations_log
    )

    diff_removed = "".join(f'<span class="inline-block px-2 py-1 rounded-md bg-red-500/20 text-red-400 text-sm mr-2 mb-2">− {_escape(p)}</span>' for p in (diff.get("removed") or []))
    diff_added = "".join(f'<span class="inline-block px-2 py-1 rounded-md bg-emerald-500/20 text-emerald-400 text-sm mr-2 mb-2">+ {_escape(p)}</span>' for p in (diff.get("added") or []))

    origin_link = f'<a href="{_escape(origin.get("url", ""))}" target="_blank" rel="noopener" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-lg bg-amber-500/20 text-amber-400 text-sm font-medium hover:bg-amber-500/30 transition-colors">View post →</a>' if origin.get("url") else ""

    # Richer stats for same-message section (from propagation nodes)
    pg_nodes = provenance_graph.get("nodes") or []
    n_prop = len(propagation_node_indices)
    count_verbatim = sum(1 for i in propagation_node_indices if i < len(pg_nodes) and (pg_nodes[i].get("propagation_kind") or "") == "verbatim")
    count_paraphrased = sum(1 for i in propagation_node_indices if i < len(pg_nodes) and (pg_nodes[i].get("propagation_kind") or "") == "paraphrased")
    count_shifted = sum(1 for i in propagation_node_indices if i < len(pg_nodes) and (pg_nodes[i].get("propagation_kind") or "") == "shifted")
    reddit_prop = sum(1 for i in propagation_node_indices if i < len(pg_nodes) and (pg_nodes[i].get("source") or "").lower() == "reddit")
    bluesky_prop = sum(1 for i in propagation_node_indices if i < len(pg_nodes) and (pg_nodes[i].get("source") or "").lower() == "bluesky")
    n_accounts = len(propagation_authors)
    accounts_list = same_message_spread.get("accounts") or propagation_authors
    msg_snippet = (same_message_spread.get("message_snippet") or propagated_message or "")[:220]
    same_message_detected = same_message_spread.get("detected") or (n_accounts >= 2 and n_prop >= 2)

    # Build propagation section: always show when we have a graph (so user sees a clear difference)
    same_message_section = ""
    has_graph = bool(provenance_graph.get("nodes"))
    tracked_msg = msg_snippet or (propagated_message or "")[:220]
    if has_graph and not tracked_msg:
        for n in pg_nodes:
            if n.get("is_current"):
                tracked_msg = (n.get("text") or "")[:220]
                break
    if has_graph and tracked_msg:
        # Full visual section when multiple accounts or multiple posts carry the message
        if same_message_detected and n_accounts > 0:
            account_pills = "".join(
                f'<span class="inline-flex items-center px-3 py-1.5 rounded-full bg-amber-500/20 text-amber-200 text-sm font-medium mr-2 mb-2">@{_escape(a)}</span>'
                for a in accounts_list if a
            )
            total_kind = count_verbatim + count_paraphrased + count_shifted or 1
            bar_v = int(100 * count_verbatim / total_kind) if total_kind else 0
            bar_p = int(100 * count_paraphrased / total_kind) if total_kind else 0
            bar_s = int(100 * count_shifted / total_kind) if total_kind else 0
            platform_line = []
            if reddit_prop:
                platform_line.append(f"Reddit: {reddit_prop}")
            if bluesky_prop:
                platform_line.append(f"Bluesky: {bluesky_prop}")
            platform_str = " · ".join(platform_line) if platform_line else "—"
            same_message_section = f'''
    <section class="mb-12 animate-fade-in rounded-2xl border-2 border-amber-500/50 bg-gradient-to-br from-amber-500/10 to-orange-500/5 p-6 shadow-xl overflow-hidden" style="animation-delay: 85ms">
      <div class="flex items-start gap-4 mb-4">
        <div class="w-12 h-12 rounded-xl bg-amber-500/30 flex items-center justify-center shrink-0">
          <svg class="w-6 h-6 text-amber-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"/></svg>
        </div>
        <div class="flex-1 min-w-0">
          <h2 class="text-base font-bold uppercase tracking-wider text-amber-400 mb-1">Same message across many accounts</h2>
          <p class="text-zinc-500 text-sm">One message appearing across multiple accounts in the last 7 days.</p>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-5">
        <div class="rounded-xl bg-zinc-900/80 border border-zinc-700 p-4 text-center">
          <div class="text-2xl font-bold text-amber-400">{n_accounts}</div>
          <div class="text-xs uppercase tracking-wider text-zinc-500 mt-1">Accounts</div>
        </div>
        <div class="rounded-xl bg-zinc-900/80 border border-zinc-700 p-4 text-center">
          <div class="text-2xl font-bold text-amber-400">{n_prop}</div>
          <div class="text-xs uppercase tracking-wider text-zinc-500 mt-1">Posts</div>
        </div>
        <div class="rounded-xl bg-zinc-900/80 border border-zinc-700 p-4 text-center">
          <div class="text-lg font-bold text-zinc-300">{platform_str}</div>
          <div class="text-xs uppercase tracking-wider text-zinc-500 mt-1">By platform</div>
        </div>
        <div class="rounded-xl bg-zinc-900/80 border border-zinc-700 p-4">
          <div class="flex gap-1 h-2 rounded-full overflow-hidden bg-zinc-800 mb-2">
            <div class="bg-emerald-500" style="width:{bar_v}%"></div>
            <div class="bg-amber-500" style="width:{bar_p}%"></div>
            <div class="bg-orange-500" style="width:{bar_s}%"></div>
          </div>
          <div class="text-xs text-zinc-500 flex justify-between"><span>{count_verbatim} verbatim</span><span>{count_paraphrased} paraphrased</span><span>{count_shifted} shifted</span></div>
        </div>
      </div>
      <div class="rounded-xl bg-zinc-900/60 border border-zinc-700 p-4 mb-4">
        <p class="text-xs uppercase tracking-wider text-amber-400/90 mb-2">Shared message</p>
        <p class="text-zinc-300 text-sm leading-relaxed">"{_escape(msg_snippet)}"{'…' if len(msg_snippet) >= 220 else ''}</p>
      </div>
      <p class="text-xs uppercase tracking-wider text-zinc-500 mb-2">Accounts sharing this message</p>
      <div class="flex flex-wrap gap-2">{account_pills}</div>
    </section>'''
        elif n_prop >= 1:
            # Compact: at least one node carries the message
            account_pills = "".join(
                f'<span class="inline-flex px-2 py-1 rounded-full bg-zinc-700/50 text-zinc-300 text-xs mr-1 mb-1">@{_escape(a)}</span>'
                for a in accounts_list if a
            )
            same_message_section = f'''
    <section class="mb-12 animate-fade-in rounded-2xl border border-amber-500/30 bg-amber-500/5 p-5 shadow-lg" style="animation-delay: 85ms">
      <h2 class="text-sm font-bold uppercase tracking-wider text-amber-400 mb-2">Message propagation</h2>
      <p class="text-zinc-300 text-sm mb-3">"{_escape(tracked_msg[:200])}{'…' if len(tracked_msg) > 200 else ''}"</p>
      <div class="flex flex-wrap items-center gap-4 text-sm">
        <span class="text-amber-400 font-semibold">{n_prop} post(s)</span>
        <span class="text-zinc-500">·</span>
        <span class="text-zinc-400">{n_accounts} account(s)</span>
        {f'<span class="text-zinc-500">·</span><span class="text-zinc-400">{account_pills or "—"}</span>' if accounts_list else ''}
      </div>
    </section>'''
        else:
            # Graph exists but no other posts carry this message
            same_message_section = f'''
    <section class="mb-12 animate-fade-in rounded-2xl border border-zinc-700 bg-zinc-900/40 p-5" style="animation-delay: 85ms">
      <h2 class="text-sm font-bold uppercase tracking-wider text-zinc-400 mb-2">Tracked message</h2>
      <p class="text-zinc-300 text-sm mb-2">"{_escape(tracked_msg[:200])}{'…' if len(tracked_msg) > 200 else ''}"</p>
      <p class="text-zinc-500 text-xs">No other posts in the last 7 days carry this message.</p>
    </section>'''

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

    {same_message_section}

    <section class="mb-12 animate-fade-in" style="animation-delay: 100ms">
      <h2 class="text-sm font-semibold uppercase tracking-widest text-zinc-500 mb-4">Provenance Graph</h2>
      <p class="text-zinc-500 text-sm mb-3">Only posts from the last 7 days. Chronological (earliest → current). One post can branch into multiple later posts. Click a node to open the post.</p>
      {f'''<div class="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 mb-4"><p class="text-amber-200 font-medium text-sm mb-1">Tracked message</p><p class="text-zinc-300 text-sm">{_escape(propagated_message)}</p><p class="text-zinc-500 text-xs mt-2">This message appears in {len(propagation_node_indices)} node(s) — verbatim, paraphrased, or shifted.</p>{f'<p class="text-amber-300 text-sm mt-2 font-medium">Multiple accounts sharing this message: {_escape(", ".join("@" + a for a in propagation_authors if a))}</p>' if len(propagation_authors) > 1 else ''}</div>''' if propagated_message else ''}
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
      <p class="text-zinc-500 text-xs mb-2">Evidence: source span → target span (hover for full text).</p>
      <div class="rounded-2xl border border-zinc-800 bg-zinc-900/50 overflow-hidden shadow-xl overflow-x-auto">
        <table class="w-full min-w-[500px]"><thead><tr class="text-left text-zinc-500 text-xs uppercase tracking-wider"><th class="py-3 px-4">Agent</th><th class="py-3 px-4">Type</th><th class="py-3 px-4">Source span</th><th class="py-3 px-4">Target span</th><th class="py-3 px-4">Conf</th></tr></thead><tbody>{mut_rows}</tbody></table>
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
          low: {{ color: {{ background: "#ef4444", border: "#f87171" }} }},
          medium: {{ color: {{ background: "#f97316", border: "#fb923c" }} }},
          high: {{ color: {{ background: "#22c55e", border: "#4ade80" }} }},
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
