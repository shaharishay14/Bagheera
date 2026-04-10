from app.db.database import SessionLocal
from app.db.models import Annotation


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
