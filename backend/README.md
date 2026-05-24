# Bagheera backend

FastAPI service that drives the TRIDENT feature-extraction and PANTHER
prototype-training pipelines, with a per-fold visualization layer and a
per-slide inference flow on top.

Single-user, single-GPU assumption. Async work runs in one background
worker thread that polls a SQLite-backed `jobs` table.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit (see below)
```

You also need local checkouts of:

- [TRIDENT](https://github.com/mahmoodlab/TRIDENT) — runs feature extraction.
- [PANTHER](https://github.com/mahmoodlab/PANTHER) — runs prototype training
  and provides the renderers `services/visualization.py` imports.

Install **their** dependencies into the same venv (torch, openslide,
h5py, scikit-learn, umap-learn, matplotlib, opencv-python, seaborn,
pandas, etc.) so the worker can import them at runtime. Heavy deps are
imported lazily — the API will boot without them, but `panther_train` /
`post_train_viz` / `inference` jobs will fail at the first import in the
job log.

## Environment variables

| Var | Required | Purpose |
| --- | --- | --- |
| `TRIDENT_ALLOWED_ROOTS` | yes | Colon-separated absolute paths the filesystem browser may traverse. Production **must** set this; defaults to `$HOME` for local dev. |
| `TRIDENT_REPO_PATH` | yes | Absolute path to the local TRIDENT checkout. `services/runner.py` and `services/inference_job.py` shell out into it. |
| `TRIDENT_PYTHON` | no | Python interpreter with TRIDENT's deps installed. Defaults to `python`. |
| `PANTHER_REPO_PATH` | yes | Absolute path to the local PANTHER checkout. `services/visualization.py` adds `${PANTHER_REPO_PATH}/src` to `sys.path` lazily. `${PANTHER_REPO_PATH}/src/datasets_splits/` must be writable. |
| `BAGHEERA_DB_PATH` | no | SQLite file path. Default `./bagheera.db`. |
| `DATASETS_SPLITS_ROOT` | no | Override for K-fold split folder root. Defaults to `${PANTHER_REPO_PATH}/src/datasets_splits` when `PANTHER_REPO_PATH` is set. |
| `VIZ_CACHE_ROOT` | no | Where pre-rendered viz files land. Default `./viz_cache`. Subdir `job_logs/` holds one log file per async job. |
| `INFERENCE_ROOT` | no | Where per-inference TRIDENT output + viz files land. Default `./inference_outputs`. |

`VIZ_CACHE_ROOT` and `INFERENCE_ROOT` should be **absolute paths** in
production — relative paths resolve from uvicorn's cwd, which is usually
`backend/` but isn't guaranteed.

Load the env (`set -a; source .env; set +a`) or export the vars before
starting uvicorn. If `source .env` doesn't survive backgrounding cleanly
in your shell, use `env $(grep -v '^#' .env | grep -v '^$' | xargs)
uvicorn ...` instead.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Health: `GET /api/health` · OpenAPI: `http://localhost:8000/docs`.

The frontend dev server (`cd frontend && npm run dev`) proxies `/api/*`
to port 8000.

## Endpoints (high level)

| Group | Endpoints |
| --- | --- |
| Filesystem | `GET /api/fs/roots`, `GET /api/fs/list`, `GET /api/fs/csv-count` |
| TRIDENT runs | `POST /api/trident/run`, `GET /api/trident/runs[/{id}]`, `GET /api/runs/resolve?features_dir=...` |
| Splits | `POST /api/splits`, `GET /api/splits[?dataset_name]`, `GET /api/splits/{id}` |
| PANTHER training | `POST /api/panther/runs`, `GET /api/panther/runs[?group_id]`, `GET /api/panther/models[?group_id]` |
| Model groups | `GET /api/model-groups[?...]`, `GET/PATCH /api/model-groups/{group_id}` |
| Models | `GET/PATCH /api/models/{id}`, `POST /api/models/{id}/shuffle-preview`, `GET /api/models/{id}/trident-params` |
| Labels | `GET/POST /api/prototype-labels`, `DELETE /api/prototype-labels/{id}` |
| Notes | `GET/POST /api/model-notes`, `PATCH/DELETE /api/model-notes/{id}` |
| Inferences | `POST /api/inferences`, `GET /api/inferences[?...]`, `GET /api/inferences/{id}`, `POST /api/inferences/{id}/rerun`, `GET /api/inferences/lookup?...`, `GET /api/inferences/{id}/example-patches`, `GET /api/inference-batches/{id}` |
| Inference notes | `GET/POST /api/inference-notes`, `PATCH/DELETE /api/inference-notes/{id}` |
| Jobs | `GET /api/jobs[?...]`, `GET /api/jobs/{id}` (includes `log_tail`), `POST /api/jobs/{id}/retry` |
| Visualizations | `GET /api/viz/{file_path:path}` (real files), `GET /api/viz/placeholder/{kind}` (SVG placeholders) |

Full schemas in `/docs`.

## Seed demo data

```bash
.venv/bin/python scripts/seed_demo.py            # idempotent
.venv/bin/python scripts/seed_demo.py --reset    # wipe only
```

Inserts 4 model groups across 2 datasets covering the full UI matrix
(K=3 rendering, K=5 all-ready, K=5 mixed-failure, K=10 all-ready) plus
3 demo inferences against `[SEED] BRCA Pilot v1` fold 0 (2 ready, 1
failed). Every row carries a `[SEED]` prefix on `display_name` /
`dataset_name` / `split_name` so it's never confused with real runs;
the seed wipe filters on those prefixes.

## Job logs

Every async job writes a log file to `${VIZ_CACHE_ROOT}/job_logs/{job_id}.log`.
The most recent ~8000 chars are exposed via `GET /api/jobs/{id}` as
`log_tail` and rendered in the frontend's job-log viewer modal (the
"log" link next to each job's status pill).

When a TRIDENT or PANTHER subprocess fails, its full stdout + stderr
land in the log file; `error_message` on the relevant row (Model,
Inference, or Job) gets the first ~2000 chars of the failure summary.

## First-deploy gotchas

Each major service module's top docstring is the authoritative list:

- `app/services/visualization.py` — 11 assumptions about PANTHER's
  `.pkl` structure, `PrototypeTokenizer` quirks, the `get_panther_encoder`
  hardcoded `n_proto`, h5 conventions, WSI file discovery, sys.path
  injection, and UMAP/top-K cost caps.
- `app/services/inference.py` — 10 assumptions about TRIDENT's CSV
  column name, `--gpus` shape, the output path pattern, WSI stem
  conventions, and cache invalidation semantics.
- `app/routes/viz.py` — deploy-day verification checklist for the
  `/api/viz/{file}` route (absolute roots, readability, content-type).

Most first-deploy issues fall into one of these buckets:

1. **`X is not set on the server`** — your `.env` isn't loaded into
   uvicorn's process env. Use the `env $(...)` pattern above.
2. **`ModuleNotFoundError: No module named 'torch'`** — PANTHER's deps
   aren't installed in the venv that runs uvicorn. Install them.
3. **`No such file or directory: '.../config.json'`** — `PANTHER_REPO_PATH`
   points at the wrong checkout or its `src/configs/{model_config}/`
   subdir is missing.
4. **`TRIDENT features file not found at expected path: ...`** —
   TRIDENT actually wrote the h5 somewhere else. Adjust the path
   pattern in `services/inference.py:locate_features_file` (assumption
   #4) to match what TRIDENT does on your version.
5. **404 from `/api/viz/{absolute_path}`** — either the file doesn't
   exist on disk (the renderer failed silently — check the job log) or
   `VIZ_CACHE_ROOT` / `INFERENCE_ROOT` is set to a different path than
   the renderer wrote to.

## Out of scope (deferred to later PRs)

- Job cancellation / real queue migration
- Multi-user concurrency (single worker thread)
- Auto-cleanup of `viz_cache/` and `inference_outputs/` (grow unbounded;
  manual pruning for now — see TODO in `app/config.py`)
- WSI upload through the browser
- MPP override for slides without embedded resolution (TODO in
  `services/inference.py`)
- "Test on training-set slides" mode on Inference page
- Cross-group model comparison views
- Export of labels / notes / inferences

## Security notes

`/api/fs/list`, `/api/trident/run`, `/api/inferences` (POST), and
`/api/viz/{file}` all resolve their path arguments with `Path.resolve()`
and reject anything outside `TRIDENT_ALLOWED_ROOTS` (for user-supplied
inputs) or `VIZ_CACHE_ROOT` + `INFERENCE_ROOT` (for served viz files).
Symlinks pointing outside the allowed roots are rejected after resolve.
