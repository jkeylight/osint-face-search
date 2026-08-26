"""API integration tests with FastAPI TestClient (in-process, no server)."""
from __future__ import annotations

import io
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _upload_file(data: bytes, name="test.jpg"):
    return (name, io.BytesIO(data), "image/jpeg")


class TestSystemEndpoints:
    def test_root_serves_ui(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "OSINT Face Search" in r.text

    def test_system_info(self, client):
        r = client.get("/api/system")
        assert r.status_code == 200
        body = r.json()
        assert body["app"]["version"] == "2.1.0"
        assert isinstance(body["engines"], list) and body["engines"]
        assert "face" in body and "models" in body

    def test_stats(self, client):
        r = client.get("/api/stats")
        assert r.status_code == 200
        assert set(["jobs", "results", "matches"]) <= set(r.json())


class TestValidation:
    def test_rejects_non_image(self, client):
        r = client.post("/api/jobs", files={"file": ("x.txt", io.BytesIO(b"hello"), "text/plain")})
        assert r.status_code == 400

    def test_rejects_bad_options_json(self, client, demo_images):
        r = client.post(
            "/api/jobs",
            files={"file": _upload_file(demo_images["subject_a_base.jpg"])},
            data={"options": "{invalid"},
        )
        assert r.status_code == 400

    def test_rejects_garbage_image(self, client):
        r = client.post("/api/jobs", files={"file": ("x.jpg", io.BytesIO(b"\xff\xd8\xff" + b"x" * 200), "image/jpeg")})
        assert r.status_code == 400

    def test_analyze_rejects_text(self, client):
        r = client.post("/api/analyze", files={"file": ("x.txt", io.BytesIO(b"nope"), "text/plain")})
        assert r.status_code == 400


class TestAnalyze:
    def test_analyze_demo_image(self, client, demo_images):
        r = client.post("/api/analyze", files={"file": _upload_file(demo_images["subject_a_base.jpg"])})
        assert r.status_code == 200
        body = r.json()
        assert body["face_count"] >= 1
        assert body["thumb"].startswith("/media/cache/")
        # annotated thumb should be servable
        thumb = client.get(body["thumb"])
        assert thumb.status_code == 200


class TestJobLifecycle:
    def test_full_job_with_gallery(self, client, demo_images):
        """End-to-end: seed a gallery identity, then search with zero remote engines."""
        # seed gallery with a variant of Subject A
        r = client.post("/api/gallery", data={"name": "Lifecycle Subject", "notes": ""})
        gid = r.json()["id"]
        r = client.post(
            f"/api/gallery/{gid}/images",
            files={"file": _upload_file(demo_images["subject_a_variant_1.jpg"])},
        )
        assert r.status_code == 200 and r.json()["face_found"]

        # run the search
        r = client.post(
            "/api/jobs",
            files={"file": _upload_file(demo_images["subject_a_base.jpg"])},
            data={"options": json.dumps({"engines": [], "include_gallery": True})},
        )
        assert r.status_code == 200
        job_id = r.json()["job_id"]

        # poll until terminal
        import time
        for _ in range(60):
            j = client.get(f"/api/jobs/{job_id}").json()
            if j["status"] in ("done", "error", "cancelled"):
                break
            time.sleep(0.5)
        assert j["status"] == "done", j.get("error")

        assert j["face_count"] >= 1
        assert len(j["results"]) >= 1
        gal = [r for r in j["results"] if "gallery" in r["engines"]]
        assert gal, "expected gallery matches"
        assert gal[0]["verdict"] in ("strong", "possible")

        # cleanup so other tests see a clean gallery
        client.delete(f"/api/gallery/{gid}")
        client.delete(f"/api/jobs/{job_id}")

    def test_job_not_found(self, client):
        assert client.get("/api/jobs/nonexistent123").status_code == 404

    def test_delete_missing_job(self, client):
        assert client.delete("/api/jobs/nonexistent123").status_code == 404


class TestVerify:
    def test_verify_same_person(self, client, demo_images):
        r = client.post(
            "/api/verify",
            files={
                "file1": _upload_file(demo_images["subject_a_base.jpg"]),
                "file2": _upload_file(demo_images["subject_a_variant_2.jpg"]),
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["verdict"] == "strong"
        assert body["similarity"] > 0.5

    def test_verify_different_people(self, client, demo_images):
        r = client.post(
            "/api/verify",
            files={
                "file1": _upload_file(demo_images["subject_a_base.jpg"]),
                "file2": _upload_file(demo_images["subject_d_1.jpg"]),
            },
        )
        assert r.status_code == 200
        body = r.json()
        assert body["verdict"] in ("none", "weak")

    def test_verify_bad_input(self, client):
        r = client.post("/api/verify", files={
            "file1": ("a.txt", io.BytesIO(b"x"), "text/plain"),
            "file2": ("b.txt", io.BytesIO(b"y"), "text/plain"),
        })
        assert r.status_code == 400


class TestGalleryCrud:
    def test_gallery_flow(self, client, demo_images):
        # create identity
        r = client.post("/api/gallery", data={"name": "Test Person", "notes": "unit test"})
        assert r.status_code == 200
        gid = r.json()["id"]

        # add image
        r = client.post(
            f"/api/gallery/{gid}/images",
            files={"file": _upload_file(demo_images["subject_c_1.jpg"])},
        )
        assert r.status_code == 200
        assert r.json()["face_found"] is True

        # listed
        items = client.get("/api/gallery").json()["gallery"]
        mine = [g for g in items if g["id"] == gid]
        assert mine and len(mine[0]["images"]) == 1
        assert mine[0]["images"][0]["thumb"].startswith("/media/gallery/")

        # thumb serves
        assert client.get(mine[0]["images"][0]["thumb"]).status_code == 200

        # delete image, then identity
        img_id = mine[0]["images"][0]["id"]
        assert client.delete(f"/api/gallery/images/{img_id}").status_code == 200
        assert client.delete(f"/api/gallery/{gid}").status_code == 200
        items = client.get("/api/gallery").json()["gallery"]
        assert not [g for g in items if g["id"] == gid]

    def test_gallery_add_image_missing_identity(self, client, demo_images):
        r = client.post(
            "/api/gallery/nope/images",
            files={"file": _upload_file(demo_images["subject_b_1.jpg"])},
        )
        assert r.status_code == 404


class TestFeedback:
    def test_feedback_roundtrip(self, client, demo_images):
        r = client.post("/api/jobs", files={
            "file": _upload_file(demo_images["subject_e_1.jpg"])
        }, data={"options": json.dumps({"engines": [], "include_gallery": False})})
        job_id = r.json()["job_id"]
        import time
        for _ in range(40):
            j = client.get(f"/api/jobs/{job_id}").json()
            if j["status"] in ("done", "error"):
                break
            time.sleep(0.3)
        r = client.post("/api/feedback", data={
            "job_id": job_id, "result_url": "https://example.com/x.jpg",
            "is_correct": "true", "comment": "test",
        })
        assert r.status_code == 200
        # cleanup
        client.delete(f"/api/jobs/{job_id}")


class TestHistoryAndExport:
    def test_list_jobs(self, client):
        r = client.get("/api/jobs")
        assert r.status_code == 200
        assert isinstance(r.json()["jobs"], list)

    def test_export_missing_job(self, client):
        assert client.get("/api/jobs/zzz/export?fmt=json").status_code == 404
