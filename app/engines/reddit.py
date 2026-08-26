"""
Reddit public feed engine (JSON API, no browser).

Harvests recent image posts from configurable subreddits and hands them to
the face verification stage — a "watch the public feed" capability rather
than a true reverse search.
"""
from __future__ import annotations

import logging
from typing import List

from app.engines.base import BaseEngine, Candidate, EngineMeta, SearchContext

logger = logging.getLogger(__name__)

DEFAULT_SUBREDDITS = [
    "pics", "portraits", "itookapicture", "photocritique",
    "HumansBeingBros", "mildlyinteresting",
]


class RedditEngine(BaseEngine):
    meta = EngineMeta(
        key="reddit",
        label="Reddit Feed",
        category="feed",
        requires="http",
        description="Scans recent public image posts on selected subreddits",
        homepage="https://www.reddit.com",
    )

    def __init__(self):
        super().__init__()
        self.subreddits = DEFAULT_SUBREDDITS

    async def search(self, ctx: SearchContext) -> List[Candidate]:
        import asyncio as _asyncio

        import aiohttp

        out: List[Candidate] = []
        headers = {"User-Agent": self.random_ua()}
        per_sub = max(3, ctx.max_results // max(1, len(self.subreddits)))

        async def fetch(sub: str):
            url = f"https://www.reddit.com/r/{sub}/new.json?limit={per_sub * 2}"
            try:
                async with ctx.session.get(
                    url, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return
                    data = await resp.json(content_type=None)
            except Exception as e:  # noqa: BLE001
                logger.debug("[reddit] %s failed: %s", sub, e)
                return
            for child in data.get("data", {}).get("children", []):
                p = child.get("data", {})
                permalink = "https://www.reddit.com" + p.get("permalink", "")
                title = (p.get("title") or "")[:200]
                url = (p.get("url") or "").split("?")[0]
                if url.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                    out.append(Candidate(
                        image_url=url, source_url=permalink,
                        title=title, engine=self.meta.key,
                    ))
                for img in (p.get("preview", {}) or {}).get("images", []):
                    src = ((img.get("source") or {}).get("url") or "").replace("&amp;", "&")
                    if src.startswith("http"):
                        out.append(Candidate(
                            image_url=src, source_url=permalink,
                            title=title, engine=self.meta.key,
                        ))

        await _asyncio.gather(*(fetch(s) for s in self.subreddits))
        seen, uniq = set(), []
        for c in out:
            if c.image_url not in seen:
                seen.add(c.image_url)
                uniq.append(c)
        return uniq[: ctx.max_results]
