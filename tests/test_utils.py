"""Unit tests for domain classification and ranking helpers."""
from __future__ import annotations

from app.config import config
from app.pipeline import Pipeline
from app.utils.domains import classify_domain, domain_of, source_weight
from app.utils.images import clamp_bbox, expand_bbox, media_url


class TestDomains:
    def test_domain_extraction(self):
        assert domain_of("https://www.bbc.co.uk/news/x?a=1") == "www.bbc.co.uk"
        assert domain_of("http://EXAMPLE.com/img.jpg") == "example.com"
        assert domain_of("not a url") == ""

    def test_classification(self):
        assert classify_domain("www.bbc.co.uk") == "news"
        assert classify_domain("cnn.com") == "news"
        assert classify_domain("linkedin.com") == "official"
        assert classify_domain("example.gov") == "official"
        assert classify_domain("i.redd.it") == "social"
        assert classify_domain("boards.4chan.org") == "forum"
        assert classify_domain("example.com") == "unknown"
        assert classify_domain("") == "unknown"

    def test_source_weight_bounds(self):
        for url in ["https://bbc.com/x.jpg", "https://random.org/x.jpg",
                    "https://reddit.com/x.jpg", "https://4chan.org/x.jpg"]:
            w = source_weight(url, config.SOURCE_WEIGHTS)
            assert 0.0 < w <= 1.0


class TestBboxes:
    def test_clamp(self):
        assert clamp_bbox((-5, -5, 50, 50), 100, 100) == (0, 0, 50, 50)
        assert clamp_bbox((90, 90, 150, 150), 100, 100) == (90, 90, 100, 100)

    def test_expand(self):
        assert expand_bbox((40, 40, 60, 60), 100, 100, pad=0.5) == (30, 30, 70, 70)
        # clamped at edges
        assert expand_bbox((0, 0, 10, 10), 100, 100, pad=1.0) == (0, 0, 20, 20)


class TestMediaUrl:
    def test_mounts(self):
        assert media_url("uploads/abc.jpg") == "/media/uploads/abc.jpg"
        assert media_url("data/candidates/j1/x.jpg") == "/media/candidates/j1/x.jpg"
        assert media_url("data/gallery/g1/x.jpg") == "/media/gallery/g1/x.jpg"
        assert media_url("cache/x.jpg") == "/media/cache/x.jpg"
        assert media_url("demo/x.jpg") == "/media/demo/x.jpg"

    def test_empty(self):
        assert media_url("") == ""


class TestRanking:
    def _r(self, **kw):
        base = dict(confidence=80.0, engines=["bing"], source_kind="news",
                    face_count=1, is_query_dup=False, similarity=0.6)
        base.update(kw)
        return base

    def test_confidence_dominates(self):
        strong = Pipeline._rank_score(self._r(confidence=90))
        weak = Pipeline._rank_score(self._r(confidence=10))
        assert strong > weak

    def test_consensus_boosts(self):
        single = Pipeline._rank_score(self._r(engines=["bing"]))
        multi = Pipeline._rank_score(self._r(engines=["bing", "yandex", "tineye"]))
        assert multi > single

    def test_dup_penalty(self):
        clean = Pipeline._rank_score(self._r())
        dup = Pipeline._rank_score(self._r(is_query_dup=True))
        assert dup < clean

    def test_merge_near_duplicates(self):
        rows = [
            self._r(url="a", phash="0" * 256, engines=["bing"], similarity=0.5),
            self._r(url="b", phash="0" * 250 + "1" * 6, engines=["yandex"], similarity=0.7),
            self._r(url="c", phash="1" * 256, engines=["reddit"], similarity=0.2),
        ]
        merged = Pipeline._merge_near_duplicates(rows)
        assert len(merged) == 2
        winner = next(r for r in merged if r["url"] == "b")
        assert set(winner["engines"]) == {"bing", "yandex"}
        assert winner["similarity"] == 0.7
