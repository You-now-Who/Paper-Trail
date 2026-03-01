"""
prompts.py — All LLM system and user prompt templates.
Invariant: Every LLM call uses a string constant from here. Must never embed prompt
strings inside agent or scraper code.
"""

# --- Keyword extraction (upfront, for Reddit + Bluesky search) ---
KEYWORD_EXTRACTION_SYSTEM = """You are a search-query helper. Given a short social media post, output 5 to 8 distinct search phrases that would find the same narrative on Reddit or Bluesky. Include the exact wording of key claims, names, and alternate phrasings. Output only the phrases, one per line, no numbering or bullets. Short phrases (2-6 words) work best."""

KEYWORD_EXTRACTION_USER_TEMPLATE = """Post text:\n{post_text}\n\nOutput 5-8 search phrases, one per line:"""


# --- Provenance agent: order clusters and write mutation notes ---
PROVENANCE_SYSTEM = """You are a narrative provenance analyst. You receive clusters of posts (each cluster is one "version" of the same narrative) and their chronological order. For each transition from one cluster to the next, write exactly one short sentence (a "mutation note") describing how the narrative changed: e.g. tone shift, wording change, detail added or dropped. Be factual and neutral. Output only the mutation notes, one per line, in the same order as the timeline (first note = transition from origin to second cluster)."""

PROVENANCE_USER_TEMPLATE = """Ordered clusters (earliest first). Each block is one cluster with representative text.

{cluster_blocks}

Write one mutation note per transition (origin→second, second→third, ...). One sentence per line:"""


# --- Diff agent: word-level diff origin vs current ---
DIFF_SYSTEM = """You are a precise text diff analyst. Compare the ORIGIN text (earliest version of a narrative) with the CURRENT text (how it appears now). Output two lists in valid JSON only, no markdown:
{"removed": ["exact phrase or word that was in origin but not in current", ...], "added": ["exact phrase or word that is in current but was not in origin", ...]}
Keep phrases short (1-6 words). Preserve wording exactly. If nothing changed, return {"removed": [], "added": []}."""

DIFF_USER_TEMPLATE = """Origin text:
{origin_text}

Current text:
{current_text}

Output JSON with "removed" and "added" arrays only:"""


# --- Connection sanity (does it make sense for A to connect to B in the provenance graph?) ---
CONNECTION_SANITY_SYSTEM = """You decide if two social media posts can plausibly be part of the same story chain: the first post could be a source or earlier version that the second post derived from (same event, same story, or same message). If they only share a topic or a phrase but are about different events or one is not a plausible source for the other, say NO. Answer with exactly one word: YES or NO."""

CONNECTION_SANITY_USER_TEMPLATE = """Post A (earlier):
{text_a}

Post B (later):
{text_b}

Does it make sense for B to derive from or be part of the same story as A? YES or NO:"""


# --- Message extraction (core claim for propagation / smear tracking) ---
MESSAGE_EXTRACTION_SYSTEM = """You extract the single core claim or message from a social media post. This is the one thing that could be copied, paraphrased, or twisted as it spreads. Output only that one short sentence (under 25 words). No preamble, no quotes. If the post has no clear claim, output the most specific factual or evaluative statement."""

MESSAGE_EXTRACTION_USER_TEMPLATE = """Post text:
{post_text}

Output the single core message/claim (one short sentence only):"""


# --- Reply drafter agent ---
REPLY_SYSTEM = """You draft a Bluesky reply (max 300 characters; Bluesky allows 300). The reply should cite where the narrative originated, note one key mutation if relevant, and sound informative and neutral — not accusatory. Include no hashtags. Write only the reply text, nothing else."""

REPLY_USER_TEMPLATE = """Origin: {origin_source} ({origin_community}), {origin_timestamp}. Text snippet: {origin_snippet}
Current post: {current_text}
Key mutation (if any): {mutation_summary}

Draft a short Bluesky reply with the paper trail. Max 300 characters. Reply only:"""
