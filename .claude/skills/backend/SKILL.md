# Backend Skill
FastAPI + SQLAlchemy + SQLite. Pydantic models match design exactly.
Layout: app/main.py (lifespan starts worker thread, CORS localhost:5173), app/api/{inference,jobs,annotations,visualization}.py, app/db/{database,models,types}.py, app/workers/{queue_worker,mock_panther}.py, app/schemas.py.

## API endpoints
- POST /api/v1/inference → 201. Fields: dataset_id, num_clusters (2–32), encoder (uni|ctranspath|resnet50), em_iter (1–10), tau (0.01–10.0), out_type (allcat|weight_avg_mean|weight_avg_all).
- GET /api/v1/jobs → list[JobOut] ordered by (priority asc, created_at asc). JobOut includes all inference fields plus encoder, em_iter, tau, out_type.
- GET /api/v1/jobs/{id}/status → JobStatusResponse.
- PUT /api/v1/jobs/reorder → 200. Listed jobs go first (0..N-1); unlisted Queued jobs follow preserving their original FIFO order. 400 if empty, 404 if unknown id, 409 if any listed job is not Queued.
- POST /api/v1/annotations → 201.
- GET /api/v1/annotations → list[AnnotationOut], optional ?target_id= and ?target_type= query params, ordered by created_at desc.
- DELETE /api/v1/annotations/{annotation_id} → 204 (404 if not found).
- GET /api/v1/visualization/{job_id} → VisualizationResponse with job metadata (job_id, dataset_id, num_clusters, encoder, em_iter, tau, out_type, status, started_at, finished_at) and clusters list (cluster_id, label, patches, prototype_index).

## Worker
Worker loop: fetch next Queued (priority ASC, created_at ASC) → Processing → build RunConfig → mock_panther.run(config) → write Cluster rows with prototype_index → Done/Error. Sleep 1s when empty.
RunConfig dataclass: dataset_id, num_clusters, encoder, em_iter, tau, out_type.

## Datetime handling
All datetime columns use UTCDateTime (backend/app/db/types.py) — a TypeDecorator that attaches timezone.utc on every read. All defaults use lambda: datetime.now(timezone.utc).

## Rules
Thin handlers, no compute in api/, uuid4().hex ids, never import workers from api/. AnnotationOut.annotation_id maps from Annotation.id (rename at handler level, not schema alias).
