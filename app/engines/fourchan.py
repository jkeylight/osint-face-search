"""
4chan public feed engine (JSON API, no browser).

Reads the public board catalogs and hands recent image posts to the face
verification stage.  4chan's API is fully open and reliable.
"""
from __future__ import annotations

import logging
from typing import List

from app.engines.base import BaseEngine, Candidate, EngineMeta, SearchContext

logger = logging.getLogger(__name__)

DEFAULT_BOARDS = ["pol", "b", "soc", "r9k", "gif"]
CDN = "https://i.4cdn.org"


class FourChanEngine(BaseEngine):
    meta = EngineMeta(
        key="fourchan",
        label="4chan Feed",
        category="feed",
        requires="http",
        description="Scans recent public image posts on selected boards",
        homepage="https://a.4cdn.org",
    )

    def __init__(self):
        super().__init__()
        self.boards = DEFAULT_BOARDS

    async def search(self, ctx: SearchContext) -> List[Candidate]:
        import asyncio as _asyncio

        import aiohttp

        out: List[Candidate] = []
        headers = {"User-Agent": self.random_ua(), "Accept": "application/json"}
        per_board = max(5, ctx.max_results // max(1, len(self.boards)))

        async def fetch(board: str):
            url = f"https://a.4cdn.org/{board}/catalog.json"
            try:
                async with ctx.session.get(
                    url, headers=headers,
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if resp.status != 200:
                        return
                    pages = await resp.json(content_type=None)
            except Exception as e:  # noqa: BLE001
                logger.debug("[4chan] %s failed: %s", board, e)
                return
            count = 0
            for page in pages:
                for thread in page.get("threads", []):
                    if count >= per_board:
                        return
                    if thread.get("ext") in (".jpg", ".jpeg", ".png", ".webp"):
                        tim = thread.get("tim")
                        if not tim:
                            continue
                        out.append(Candidate(
                            image_url=f"{CDN}/{board}/{tim}{thread['ext']}",
                            source_url=f"https://boards.4chan.org/{board}/thread/{thread.get('no')}",
                            title=(thread.get("sub") or thread.get("com") or "")[:200],
                            engine=self.meta.key,
                        ))
                        count += 1

        await _asyncio.gather(*(fetch(b) for b in self.boards))
        return out[: ctx.max_results]
