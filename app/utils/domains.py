"""Domain classification and source weighting for ranking."""
from __future__ import annotations

from urllib.parse import urlparse

_NEWS = (
    "bbc.", "cnn.", "reuters.", "apnews.", "nytimes.", "washingtonpost.",
    "theguardian.", "aljazeera.", "bloomberg.", "wsj.", "ft.com", "npr.",
    "news.yahoo.", "cnbc.", "abcnews.", "cbsnews.", "nbcnews.", "dw.com",
    "france24.", "rt.com", "spiegel.", "lemonde.", "asahi.", "scmp.",
)
_OFFICIAL = (
    ".gov", ".edu", ".mil", "linkedin.", "europa.eu",
    "un.org", "who.int",
)
_SOCIAL = (
    "facebook.", "instagram.", "twitter.", "x.com", "tiktok.", "youtube.",
    "reddit.", "redd.it", "pinterest.", "vk.com", "weibo.", "threads.", "t.me",
    "telegram.", "twitch.", "discord.",
)
_FORUM = (
    "forum", "board", "community", "stackexchange.", "stackoverflow.",
    "quora.", "4chan", "8kun", "lobste.rs", "news.ycombinator.",
)


def domain_of(url: str) -> str:
    try:
        host = urlparse(url).hostname or ""
        return host.lower().lstrip(".")
    except Exception:
        return ""


def classify_domain(domain: str) -> str:
    d = (domain or "").lower()
    if not d:
        return "unknown"
    if any(d.startswith(x) or d.endswith(x) or x in d for x in _NEWS):
        return "news"
    if any(d.endswith(x) or d.startswith(x) for x in _OFFICIAL):
        return "official"
    if any(x in d for x in _SOCIAL):
        return "social"
    if any(x in d for x in _FORUM):
        return "forum"
    return "unknown"


def source_weight(url: str, weights: dict) -> float:
    return float(weights.get(classify_domain(domain_of(url)), 0.4))


def favicon_for(domain: str) -> str:
    """External favicon service (best-effort, purely cosmetic in the UI)."""
    if not domain:
        return ""
    return f"https://icons.duckduckgo.com/ip3/{domain}.ico"
