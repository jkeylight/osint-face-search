"""Integration tests for the face engine (requires bundled models + demo images)."""
from __future__ import annotations

import numpy as np

from app.face_engine import FaceEngine
from app.utils.images import decode_image_bytes, draw_face_overlay


class TestFaceEngine:
    def test_backend_available(self, face_engine):
        assert face_engine.available
        assert face_engine.backend_name in ("opencv", "insightface")

    def test_detects_demo_faces(self, face_engine, demo_images):
        for name, data in demo_images.items():
            img = decode_image_bytes(data)
            faces = face_engine.detect(img)
            assert faces, f"no face detected in {name}"
            assert faces[0].embedding is not None
            assert faces[0].det_score > 0.5
            x1, y1, x2, y2 = faces[0].bbox
            assert 0 <= x1 < x2 and 0 <= y1 < y2

    def test_same_identity_scores_high(self, face_engine, demo_images):
        base = face_engine.best_face(decode_image_bytes(demo_images["subject_a_base.jpg"]))
        variant = face_engine.best_face(decode_image_bytes(demo_images["subject_a_variant_1.jpg"]))
        sim = face_engine.similarity(base.embedding, variant.embedding)
        assert sim >= 0.5, f"same-person similarity too low: {sim}"

    def test_different_identity_scores_low(self, face_engine, demo_images):
        base = face_engine.best_face(decode_image_bytes(demo_images["subject_a_base.jpg"]))
        other = face_engine.best_face(decode_image_bytes(demo_images["subject_b_1.jpg"]))
        sim = face_engine.similarity(base.embedding, other.embedding)
        assert sim < 0.45, f"different-person similarity too high: {sim}"

    def test_verdict_bands(self):
        assert FaceEngine.verdict_for(0.9) == "strong"
        assert FaceEngine.verdict_for(0.5) == "possible"
        assert FaceEngine.verdict_for(0.35) == "weak"
        assert FaceEngine.verdict_for(0.0) == "none"
        assert FaceEngine.verdict_for(None) == "unknown"

    def test_confidence_monotonic(self):
        assert FaceEngine.confidence(0.8) > FaceEngine.confidence(0.5)
        assert FaceEngine.confidence(0.5) > FaceEngine.confidence(0.2)
        assert 0.0 <= FaceEngine.confidence(None) <= 100.0

    def test_no_face_on_blank(self, face_engine):
        img = np.zeros((400, 400, 3), dtype=np.uint8)
        assert face_engine.detect(img) == []

    def test_similarity_none_inputs(self):
        assert FaceEngine.similarity(None, np.ones(4)) is None
        assert FaceEngine.similarity(np.zeros(4), np.zeros(4)) is None

    def test_overlay_drawing(self, demo_images):
        img = decode_image_bytes(demo_images["subject_a_base.jpg"])
        out = draw_face_overlay(img, [(100, 100, 200, 220)], labels=["face 1"])
        assert out.shape == img.shape
        assert not np.array_equal(out, img)
