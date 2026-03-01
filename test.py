"""Test Bluesky search only. Run from project root: python test.py"""

import asyncio
import json

from scrapers.bluesky import search_bluesky


async def main():
    keywords = ["Apple Watch", "Susie Wiles", "classified meeting Iran"]
    print("Searching Bluesky for:", keywords)
    posts = await search_bluesky(keywords)
    print(f"Found {len(posts)} posts")
    for i, p in enumerate(posts[:5], 1):
        print(f"\n--- {i} ---")
        print(f"  text: {p.text[:150]}...")
        print(f"  author: {p.author}")
        print(f"  timestamp: {p.timestamp}")
        print(f"  url: {p.url}")
    # Also dump first result as JSON for inspection
    if posts:
        print("\n--- First post (JSON) ---")
        print(json.dumps(posts[0].model_dump(), indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
