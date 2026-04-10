# Bagheera

GUI for the **PANTHER** pathology model — built for Sheba Medical Center.
Pathologists submit inference jobs against TIFF datasets, watch them flow
through a FIFO queue (with drag-and-drop reordering), and attach clinical
annotations to slides or clusters.

> PANTHER itself is **mocked** in this MVP. The mock worker sleeps 5–15 s,
> writes fake clusters, and trips a 10 % error to exercise the failure path.
> See `backend/app/workers/mock_panther.py` — it is the only file the real
> model integration needs to replace.

Detailed design lives in [`docs/Detailed Design - submit.docx`](docs/).

---

## Stack

| Layer    | Tech                                                       |
| -------- | ---------------------------------------------------------- |
| Frontend | React 18 + Vite + Tailwind, drag-and-drop via `@dnd-kit`   |
| Backend  | FastAPI + SQLAlchemy 2 + Pydantic v2                       |
| DB       | SQLite (file at `backend/bagheera.db`, auto-created)       |
| Worker   | In-process daemon thread, started in FastAPI `lifespan`    |
| Tests    | pytest + `httpx.TestClient`, results in `tests/results/`   |

API and worker communicate **only** via the database — the API never blocks
on heavy work and the worker has no idea HTTP exists (design §2.2).

---

## Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

API: <http://localhost:8000>  ·  Swagger: <http://localhost:8000/docs>

The worker thread starts automatically on app startup. Set
`WORKER_ENABLED=false` in `.env` to disable it (useful when poking at the
DB by hand).

### Smoke check

```bash
curl -X POST http://localhost:8000/api/v1/inference \
  -H 'content-type: application/json' \
  -d '{"dataset_id":"/data/slide_001.tiff","num_clusters":4}'
# → {"job_id":"<hex>","status":"Queued"}
```

Within ~15 s, `GET /api/v1/jobs/<job_id>/status` will return `Done`
(or `Error` ~10 % of the time).

---

## Run the frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

UI: <http://localhost:5173>. CORS is preconfigured for that origin.

Pages:
- `/inference` — submit a new job (dataset path + cluster count 2–20).
- `/jobs` — polls every 2 s. Drag rows in the **Queued** section to
  reorder; rows in `Processing` show a 🔒 lock and cannot be dragged.
- `/annotations` — POST a slide- or cluster-level note.

---

## Run the tests

```bash
cd backend && source .venv/bin/activate && cd ..
pytest -q
```

- Unit tests cover every endpoint plus the queue invariants TC-01
  (priority reorder) and TC-02 (job lock while processing) from design §8.
- An integration test boots the real worker, enqueues 5 jobs, and asserts
  they finish in FIFO order. A second integration test reorders mid-flight
  and asserts execution follows the new order.
- Each run writes a JSON summary to `tests/results/run-<utc>.json`.
- Lessons-learned and future work live in `tests/LESSONS.md`.

---

## Project layout

```
backend/
  app/
    main.py              # FastAPI app + lifespan that starts the worker
    config.py            # pydantic-settings reading .env
    schemas.py           # request/response models matching design §2.3
    api/
      inference.py       # POST /api/v1/inference
      jobs.py            # GET /jobs, GET /jobs/{id}/status, PUT /jobs/reorder
      annotations.py     # POST /api/v1/annotations
      visualization.py   # GET /api/v1/visualization/{job_id}
    db/
      database.py        # engine + SessionLocal + get_db dependency
      models.py          # Job, Annotation, Cluster
    workers/
      queue_worker.py    # daemon thread: claim → mock_panther.run → Done/Error
      mock_panther.py    # the only file to swap out for real PANTHER
  requirements.txt
  .env.example
frontend/
  src/
    api/                 # axios client + per-resource modules
    components/          # NavBar, JobRow, StatusBadge, Toast
    pages/               # Inference, JobsDashboard, Annotations
  package.json
  tailwind.config.js
tests/
  conftest.py            # fixtures + results recorder
  backend/               # unit tests for every endpoint
  integration/           # end-to-end queue flow tests
  results/               # per-run JSON summaries
  LESSONS.md             # monitoring notes + future work
docs/
  Detailed Design - submit.docx
.claude/
  .CLAUDE.md             # working agreement for Claude Code
  skills/                # backend / frontend / database skill files
```

---

## Out of scope for the MVP

These are intentionally **not** implemented and documented in
`tests/LESSONS.md`:

- Authentication / authorization
- Real PANTHER inference + GPU scheduling
- WSI viewer (OpenSeadragon / DeepZoom)
- File uploads (`POST /api/v1/datasets/upload` from design §2.3)
- H5 / PT feature-vector ingestion
- Semantic-label assignment UI (`PUT /api/v1/labels/{cluster_id}`)
- Alembic migrations (we use `create_all` on startup)
- Split Execution / Result workers (collapsed into one for the mock)
