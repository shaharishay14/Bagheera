def test_post_inference_valid(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/inference",
        json={"dataset_id": "/data/slide.tiff", "num_clusters": 5},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "Queued"
    assert isinstance(body["job_id"], str) and len(body["job_id"]) == 32


def test_post_inference_missing_field(client_no_worker):
    res = client_no_worker.post("/api/v1/inference", json={"num_clusters": 3})
    assert res.status_code == 422


def test_post_inference_clusters_out_of_range(client_no_worker):
    too_low = client_no_worker.post(
        "/api/v1/inference", json={"dataset_id": "x", "num_clusters": 1}
    )
    too_high = client_no_worker.post(
        "/api/v1/inference", json={"dataset_id": "x", "num_clusters": 99}
    )
    assert too_low.status_code == 422
    assert too_high.status_code == 422


def test_post_inference_empty_dataset_id(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/inference", json={"dataset_id": "", "num_clusters": 5}
    )
    assert res.status_code == 422
