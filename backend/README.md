# Bagheera backend

FastAPI service that drives the TRIDENT (and eventually PANTHER) pipelines.

## Setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # then edit
```

### Required environment variables

| Var | Purpose |
| --- | --- |
| `TRIDENT_ALLOWED_ROOTS` | Colon-separated absolute paths the filesystem browser may traverse. Defaults to the user's home dir for local dev; **production must set this explicitly.** |
| `TRIDENT_REPO_PATH` | Absolute path to a checkout of [TRIDENT](https://github.com/mahmoodlab/TRIDENT). The wrapper script invokes `${TRIDENT_REPO_PATH}/run_batch_of_slides.py`. |
| `TRIDENT_PYTHON` | Python interpreter with TRIDENT's deps installed. Defaults to `python`. |
| `PANTHER_REPO_PATH` | Absolute path to a checkout of [PANTHER](https://github.com/mahmoodlab/PANTHER). The backend runs `python -m training.main_prototype` with cwd `${PANTHER_REPO_PATH}/src` and `CUDA_VISIBLE_DEVICES=0`. `${PANTHER_REPO_PATH}/src/splits/` must be writable. |
| `BAGHEERA_DB_PATH` | SQLite file path (default `./bagheera.db`). |

Load the env (`set -a; source .env; set +a`) or export the vars before starting uvicorn.

## Run

```bash
uvicorn app.main:app --reload --port 8000
```

Health check: `GET http://localhost:8000/api/health`.
OpenAPI docs: `http://localhost:8000/docs`.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/fs/roots` | Configured allowed roots. |
| `GET` | `/api/fs/list?path=&filter=dirs_only&show_hidden=` | Sandboxed directory listing. |
| `GET` | `/api/fs/csv-count?path=` | Row count (excluding header) for a CSV inside an allowed root. |
| `POST` | `/api/trident/run` | Synchronously run TRIDENT feature extraction. |
| `GET` | `/api/trident/runs` | List runs (most recent first). |
| `GET` | `/api/trident/runs/{id}` | Single run. |
| `POST` | `/api/panther/run` | Generate splits + run PANTHER prototype training. |
| `GET` | `/api/panther/runs` | List PANTHER runs. |
| `GET` | `/api/panther/runs/{id}` | Single PANTHER run. |

## Security notes

`/api/fs/list` and `/api/trident/run` both resolve their path argument with
`Path.resolve()` and reject anything that isn't inside an allowed root, so `../`
traversal and symlink escapes are blocked even when the user types a raw path
into the form.
