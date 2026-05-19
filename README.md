# Bagheera

Web GUI for orchestrating the [TRIDENT](https://github.com/mahmoodlab/TRIDENT)
and [PANTHER](https://github.com/mahmoodlab/PANTHER) computational-pathology
pipelines. Two training pages: `/training/trident` (feature extraction) and
`/training/panther` (split + prototype training). Annotations, embedding
construction, downstream tasks, and visualization are out of scope for this
iteration.

## Stack

- **Backend:** Python 3.10+, FastAPI, Uvicorn, SQLAlchemy (SQLite), Pydantic v2
- **Frontend:** React 18 + TypeScript, Vite, TailwindCSS
- **Process execution:** the backend invokes `backend/scripts/run_trident.sh`
  via `subprocess` (synchronously, for now)

## Layout

```
backend/   FastAPI app, services, bash wrapper, SQLite migrations
frontend/  Vite + React + Tailwind app
```

## First-time setup

### 1. Configure the backend environment

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env`:

| Var | Notes |
| --- | --- |
| `TRIDENT_ALLOWED_ROOTS` | Colon-separated absolute paths the directory browser may traverse. Defaults to your home directory for local dev — **production must set this explicitly.** Example: `/data/wsis:/home/researcher`. |
| `TRIDENT_REPO_PATH` | Absolute path to a checkout of TRIDENT. The wrapper runs `${TRIDENT_REPO_PATH}/run_batch_of_slides.py`. |
| `TRIDENT_PYTHON` | Python interpreter with TRIDENT's deps installed. Defaults to `python`. |
| `PANTHER_REPO_PATH` | Absolute path to a checkout of [PANTHER](https://github.com/mahmoodlab/PANTHER). Set up its conda env per `${PANTHER_REPO_PATH}/env.yaml`. The backend runs `python -m training.main_prototype` with cwd `${PANTHER_REPO_PATH}/src` and `CUDA_VISIBLE_DEVICES=0`. `${PANTHER_REPO_PATH}/src/splits/` must be writable by the backend process. |
| `BAGHEERA_DB_PATH` | SQLite file path. Defaults to `./bagheera.db`. |

### 2. Install frontend deps

```bash
cd frontend
npm install
```

## Run locally

In one terminal:

```bash
cd backend
source .venv/bin/activate
set -a; source .env; set +a   # or export the vars yourself
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm run dev
```

Open <http://localhost:5173>. The Vite dev server proxies `/api/*` to
`http://localhost:8000`, so no CORS round-trip is needed during dev — CORS is
also enabled on the backend for completeness.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| `GET` | `/api/health` | liveness check |
| `GET` | `/api/fs/roots` | configured allowed roots |
| `GET` | `/api/fs/list?path=&filter=dirs_only&show_hidden=` | sandboxed directory listing |
| `GET` | `/api/fs/csv-count?path=` | row count for a CSV inside an allowed root |
| `POST` | `/api/trident/run` | run TRIDENT feature extraction synchronously |
| `GET` | `/api/trident/runs` | list TRIDENT runs |
| `GET` | `/api/trident/runs/{id}` | single TRIDENT run |
| `POST` | `/api/panther/run` | generate splits + run PANTHER prototype training synchronously |
| `GET` | `/api/panther/runs` | list PANTHER runs |
| `GET` | `/api/panther/runs/{id}` | single PANTHER run |

OpenAPI: <http://localhost:8000/docs>.

## Security model for the directory browser

`/api/fs/list` and `/api/trident/run` both resolve their path argument with
`Path.resolve()` and require the result to live inside one of the configured
`TRIDENT_ALLOWED_ROOTS`. That blocks `../` traversal and symlink escapes even
when the user pastes a raw path into the form, so the run endpoint cannot
serve as a backdoor around the browser's restrictions.

## Known limitations / TODOs

- `subprocess.Popen(...).communicate()` is synchronous — the HTTP request
  blocks for the full TRIDENT run. Real deployments need to switch to a
  background task queue with status polling and (later) log streaming.
- No auth.
- No PANTHER, annotation, or visualization pages yet.
