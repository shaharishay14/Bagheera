from app.db.database import SessionLocal
from app.db.models import Annotation


def _post(client, target_id="slide_42", target_type="slide", note="high grade dysplasia"):
    res = client.post(
        "/api/v1/annotations",
        json={"target_id": target_id, "target_type": target_type, "note": note},
    )
    assert res.status_code == 201
    return res.json()["annotation_id"]


def test_post_annotation_persists(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/annotations",
        json={"target_id": "slide_42", "target_type": "slide", "note": "high grade dysplasia"},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["message"] == "Saved"
    aid = body["annotation_id"]

    db = SessionLocal()
    try:
        row = db.get(Annotation, aid)
        assert row is not None
        assert row.target_id == "slide_42"
        assert row.target_type == "slide"
        assert row.note == "high grade dysplasia"
    finally:
        db.close()


def test_post_annotation_invalid_target_type(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/annotations",
        json={"target_id": "x", "target_type": "patient", "note": "n"},
    )
    assert res.status_code == 422


def test_post_annotation_empty_note(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/annotations",
        json={"target_id": "x", "target_type": "cluster", "note": ""},
    )
    assert res.status_code == 422


def test_list_annotations_returns_all(client_no_worker):
    _post(client_no_worker, target_id="s1")
    _post(client_no_worker, target_id="s2")
    _post(client_no_worker, target_id="s3")

    res = client_no_worker.get("/api/v1/annotations")
    assert res.status_code == 200
    assert len(res.json()) == 3


def test_list_annotations_filter_by_target_id(client_no_worker):
    _post(client_no_worker, target_id="slide_a", target_type="slide")
    _post(client_no_worker, target_id="slide_a", target_type="slide")
    _post(client_no_worker, target_id="cluster_b", target_type="cluster")

    res = client_no_worker.get("/api/v1/annotations", params={"target_id": "slide_a"})
    assert res.status_code == 200
    assert len(res.json()) == 2


def test_list_annotations_filter_by_target_type(client_no_worker):
    _post(client_no_worker, target_id="s1", target_type="slide")
    _post(client_no_worker, target_id="s2", target_type="slide")
    _post(client_no_worker, target_id="c1", target_type="cluster")

    res = client_no_worker.get("/api/v1/annotations", params={"target_type": "cluster"})
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["target_type"] == "cluster"


def test_delete_annotation_removes_row(client_no_worker):
    aid = _post(client_no_worker)

    res = client_no_worker.delete(f"/api/v1/annotations/{aid}")
    assert res.status_code == 204

    db = SessionLocal()
    try:
        assert db.get(Annotation, aid) is None
    finally:
        db.close()


def test_delete_annotation_unknown_id_returns_404(client_no_worker):
    res = client_no_worker.delete("/api/v1/annotations/doesnotexist")
    assert res.status_code == 404
