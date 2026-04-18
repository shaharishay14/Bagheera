def test_post_inference_valid(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/inference",
        json={"dataset_id": "/data/slide.tiff", "num_clusters": 5},
    )
    assert res.status_code == 201
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


def test_post_inference_all_params(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/inference",
        json={
            "dataset_id": "/data/slide.tiff",
            "num_clusters": 8,
            "encoder": "ctranspath",
            "em_iter": 3,
            "tau": 2.5,
            "out_type": "weight_avg_mean",
        },
    )
    assert res.status_code == 201
    jid = res.json()["job_id"]

    listed = client_no_worker.get("/api/v1/jobs").json()
    job = next(j for j in listed if j["id"] == jid)
    assert job["num_clusters"] == 8
    assert job["encoder"] == "ctranspath"
    assert job["em_iter"] == 3
    assert abs(job["tau"] - 2.5) < 1e-6
    assert job["out_type"] == "weight_avg_mean"


def test_post_inference_encoder_invalid(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/inference", json={"dataset_id": "x", "num_clusters": 5, "encoder": "gpt4"}
    )
    assert res.status_code == 422


def test_post_inference_tau_out_of_range(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/inference", json={"dataset_id": "x", "num_clusters": 5, "tau": 20.0}
    )
    assert res.status_code == 422


def test_post_inference_em_iter_out_of_range(client_no_worker):
    res = client_no_worker.post(
        "/api/v1/inference", json={"dataset_id": "x", "num_clusters": 5, "em_iter": 11}
    )
    assert res.status_code == 422
