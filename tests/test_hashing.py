"""Unit tests for hashing utilities (no models needed)."""
from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from app.utils.hashing import (
    is_near_duplicate, phash_distance, phash_from_bytes, phash_from_pil,
    sha256_bytes, sniff_image_format,
)


def _solid_png(color, size=(64, 64)) -> bytes:
    import io
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


class TestSniffing:
    def test_png(self):
        assert sniff_image_format(_solid_png((255, 0, 0))) == "png"

    def test_jpeg_magic(self):
        assert sniff_image_format(b"\xff\xd8\xff\xe0" + b"\x00" * 20) == "jpeg"

    def test_webp(self):
        assert sniff_image_format(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 10) == "webp"

    def test_not_an_image(self):
        assert sniff_image_format(b"hello world this is text!") is None
        assert sniff_image_format(b"") is None
        assert sniff_image_format(b"\x00" * 5) is None


class TestSha256:
    def test_deterministic(self):
        assert sha256_bytes(b"abc") == sha256_bytes(b"abc")
        assert sha256_bytes(b"abc") != sha256_bytes(b"abd")
        assert len(sha256_bytes(b"x")) == 64


class TestPhash:
    def test_identical_images_same_hash(self):
        data = _solid_png((10, 200, 30), (100, 100))
        assert phash_from_bytes(data) == phash_from_bytes(data)

    def test_similar_images_close_hash(self):
        img1 = Image.new("RGB", (120, 120), (0, 0, 0))
        img2 = Image.new("RGB", (120, 120), (0, 0, 0))
        img2.putpixel((5, 5), (255, 255, 255))  # tiny change
        h1, h2 = phash_from_pil(img1), phash_from_pil(img2)
        assert phash_distance(h1, h2) <= 4

    def test_different_images_far_hash(self):
        import io
        buf1, buf2 = io.BytesIO(), io.BytesIO()
        # structured vs inverted noise
        arr1 = (np.indices((64, 64)).sum(axis=0) % 256).astype("uint8")
        arr2 = 255 - arr1
        Image.fromarray(arr1, "L").convert("RGB").save(buf1, format="PNG")
        Image.fromarray(arr2, "L").convert("RGB").save(buf2, format="PNG")
        assert phash_distance(phash_from_bytes(buf1.getvalue()),
                              phash_from_bytes(buf2.getvalue())) > 4

    def test_near_duplicate(self):
        d = phash_distance("0" * 256, "0" * 250 + "1" * 6)
        assert d == 6
        assert is_near_duplicate("0" * 256, "0" * 250 + "1" * 6, threshold=8)
        assert not is_near_duplicate("0" * 256, "1" * 256, threshold=8)
        assert not is_near_duplicate(None, "0101")

    def test_invalid_inputs(self):
        assert phash_from_bytes(b"not an image") is None
        assert phash_distance("0101", "01") is None
