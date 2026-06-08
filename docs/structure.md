# Bagheera — Project Structure & Architecture

> A web GUI for orchestrating the **TRIDENT** (feature extraction) and **PANTHER**
> (prototype training) computational-pathology pipelines, plus a per-fold
> visualization layer and a per-slide inference flow on top.
>
> **Audience:** anyone joining the project — to understand *what the system is*,
> *how the pieces fit together*, and *what is and isn't built yet* before reading
> the deeper [backend.md](./backend.md) and [frontend.md](./frontend.md).

---

## 1. What Bagheera is

Two upstream research pipelines from the Mahmood Lab do the heavy lifting:

| Pipeline | Repo | Role |
| --- | --- | --- |
| **TRIDENT** | `github.com/mahmoodlab/TRIDENT` | Segments tissue, tiles whole-slide images (WSIs) into patches, and runs a patch encoder to produce per-slide feature files (`.h5`). |
| **PANTHER** | `github.com/mahmoodlab/PANTHER` | Learns a set of *prototypes* (representative tissue patterns) over those features via an unsupervised mixture model, with K-fold cross-validation. |

Both are command-line tools. **Bagheera wraps them in a browser UI** so a pathology
researcher can run the full pipeline, inspect the prototypes a model learned, label
them, take notes, and run a trained model on new slides — without touching a terminal.

**Operating assumptions baked into the design:**

- **Single user, single GPU.** Async work runs in *one* background worker thread that
  processes *one* job at a time. No concurrency, no auth, no multi-tenancy.
- The backend, the two ML repos, and the GPU all live on **one machine** (a workstation
  or remote desktop). The browser talks to the local FastAPI server.

---

## 2. The domain model (conceptual)

Understanding these five nouns is enough to read the whole codebase:

```
TRIDENT run ──produces──▶ features dir (.h5 files, one per slide)
                                │
   CSV manifest ──split──▶ K-fold Split (train/val/test CSVs per fold)
                                │
                                ▼
        one PANTHER form submission = one  Model Group  (K folds)
                                │
                 ┌──────────────┼──────────────┐
              Model k=0      Model k=1   …   Model k=(K-1)
            (trained prototypes + per-fold visualizations)
                                │
                                ▼
                    Inference (run a fold model on a NEW slide)
```

- **TRIDENT run** — one feature-extraction job over a directory of WSIs.
- **Split** — a K-fold partition of a dataset's slides, written to disk as
  `train.csv` / `val.csv` / `test.csv` per fold. Every slide lands in `test` exactly
  once across the K folds.
- **Model Group** — the result of one PANTHER training submission. Owns **K Models**,
  one per fold.
- **Model** — a single trained PANTHER fold: its prototypes (`.pkl`), hyperparameters,
  training status, and pre-rendered visualization artifacts (preview heatmaps, a
  top-K representative-patch grid, a UMAP).
- **Inference** — running one trained fold Model against one new WSI: TRIDENT extracts
  that slide's features, then PANTHER-based renderers produce per-slide visualizations.
  Cached by a hash of the slide so the same (model, slide) pair is never recomputed.

---

## 3. End-to-end workflow

```
┌─ /training/trident ─────────────────────────────────────────────┐
│ Pick WSI dir + dataset name + patch encoder.                    │
│ POST /api/trident/run  →  runs TRIDENT *synchronously*          │
│ (the HTTP request blocks for the whole run).                    │
│ Output: a features dir of .h5 files.                            │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─ /training/panther ─────────────────────────────────────────────┐
│ Point at the features dir → server resolves the dataset.        │
│ Create a new K-fold split (from a CSV) OR pick an existing one. │
│ Set PANTHER hyperparameters.                                    │
│ POST /api/panther/runs  →  creates a Model Group + K Models,    │
│ enqueues ONE async `panther_train` job, returns immediately,    │
│ and the UI navigates to the group's detail page.                │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─ background worker thread (polls the `jobs` table every 2 s) ───┐
│ panther_train:  runs K PANTHER subprocesses sequentially.       │
│                 On each fold's success → enqueues a             │
│                 `post_train_viz` job for that fold.             │
│ post_train_viz: renders 3 preview heatmaps + a top-K grid +     │
│                 a UMAP for one fold Model.                       │
│ inference:      runs TRIDENT on a new slide, then renders        │
│                 heatmap / mixture / example patches / t-SNE.    │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─ /models  +  /models/:groupId ──────────────────────────────────┐
│ Browse groups (cards w/ status pills). Open a group to inspect  │
│ each fold: previews, prototype labels, notes, parameters,       │
│ shuffle previews, and a link into inference.                    │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─ /models/:modelId/inference ────────────────────────────────────┐
│ Pick one or many new WSIs. Cache pre-check shows which are      │
│ already computed. Run → poll → view per-slide visualizations.   │
└─────────────────────────────────────────────────────────────────┘
```

**Why two execution styles?** The *initial* TRIDENT dataset build is synchronous (one
user → one run, blocking is acceptable and simplest). PANTHER training and inference are
*async* through the worker thread because they run K subprocesses / heavy GPU work and
must not block the request.

---

## 4. Repository layout

```
Bagheera/
├── README.md                     Top-level setup + quickstart
├── .gitignore
├── docs/                         ← these documents
│   ├── structure.md
│   ├── backend.md
│   └── frontend.md
│
├── backend/                      FastAPI service
│   ├── README.md                 Backend-specific ops guide (env, gotchas)
│   ├── requirements.txt          fastapi, uvicorn, pydantic, sqlalchemy, python-multipart
│   ├── .env.example              All configurable env vars
│   ├── app/
│   │   ├── main.py               App factory: routers, CORS, lifespan, worker start
│   │   ├── config.py             Settings dataclass loaded from env
│   │   ├── db/
│   │   │   ├── database.py        SQLAlchemy engine + session + init_db()
│   │   │   └── models.py          All ORM tables (no migrations; create_all)
│   │   ├── models/
│   │   │   └── schemas.py         Pydantic request/response models
│   │   ├── routes/               One router per resource (see backend.md §API)
│   │   │   ├── fs.py  trident.py  runs.py  splits.py  panther.py
│   │   │   ├── models.py  labels.py  notes.py  inference.py  jobs.py  viz.py
│   │   └── services/             Business logic (the interesting part)
│   │       ├── fs.py              Sandboxed filesystem access
│   │       ├── runner.py          TRIDENT subprocess (sync)
│   │       ├── splitter.py        K-fold CV split generation
│   │       ├── panther_runner.py  PANTHER subprocess + path helpers
│   │       ├── worker.py          Background job worker thread + job log files
│   │       ├── job_handlers.py    Stub handlers (overwritten by real ones)
│   │       ├── panther_train.py   Real `panther_train` job handler
│   │       ├── post_train_viz.py  Real `post_train_viz` job handler
│   │       ├── inference.py        Inference helpers (hash, cache, TRIDENT cmd)
│   │       ├── inference_job.py    Real `inference` job handler
│   │       ├── visualization.py    The 6 PANTHER renderers (heatmap/umap/…)
│   │       └── preview.py          Deterministic preview-slide picking
│   └── scripts/
│       ├── run_trident.sh         Thin wrapper → TRIDENT's run_batch_of_slides.py
│       ├── run_panther.sh         Thin wrapper → PANTHER's training.main_prototype
│       ├── seed_demo.py           Idempotent demo-data seeder ([SEED] rows)
│       └── prototype_visualizer_reference.py   Upstream notebook the renderers derive from
│
└── frontend/                     Vite + React + TS + Tailwind
    ├── package.json  vite.config.ts  tailwind.config.js  tsconfig*.json
    ├── index.html
    └── src/
        ├── main.tsx              React root
        ├── App.tsx              Router + top nav
        ├── index.css           Tailwind entry
        ├── lib/api.ts          Typed API client (the FE↔BE contract)
        ├── pages/              One component per route
        │   ├── TridentTrainingPage.tsx   PantherTrainingPage.tsx
        │   ├── ModelsBrowserPage.tsx      GroupDetailPage.tsx
        │   └── InferencePage.tsx
        └── components/         Reusable UI
            ├── DirectoryBrowser.tsx   EncoderSelect.tsx
            ├── TridentForm.tsx        PantherForm.tsx
            ├── JobStatusPoller.tsx    JobLogViewer.tsx
            ├── NotesThread.tsx        PrototypeLabels.tsx
```

---

## 5. Data model (database tables)

SQLite, created via `Base.metadata.create_all()` — **there are no migrations**. After a
schema change you delete `bagheera.db` and let it recreate.

| Table | One row per… | Key relationships |
| --- | --- | --- |
| `trident_runs` | TRIDENT feature-extraction run | — |
| `splits` | K-fold split on disk (unique `split_name`) | — |
| `model_groups` | one PANTHER form submission | → `splits`, → `trident_runs` (nullable) |
| `models` | one trained fold | → `model_groups` (via `group_id`), → `splits`, → `trident_runs`; unique `(group_id, fold_index)` |
| `panther_runs` | one fold's subprocess attempt (exec log) | → `models` |
| `prototype_labels` | one label on one prototype | → `models`; unique `(model_id, prototype_index)` |
| `model_notes` | a free-text note on a model | → `models` |
| `inference_batches` | a group of inferences submitted together | → `models` |
| `inferences` | one (fold model, WSI) run | → `models`, → `inference_batches`; unique `(model_id, wsi_hash)` |
| `inference_notes` | a free-text note on an inference | → `inferences` |
| `jobs` | one async unit of work | polymorphic `(ref_table, ref_id)` pointer |

```
trident_runs ──┐
               ├──< model_groups ──< models ──< panther_runs
splits ────────┘                       │  │  │
                                       │  │  └──< prototype_labels
                                       │  └─────< model_notes
                                       └─────────< inferences ──< inference_notes
                                                       │
                                          inference_batches ──┘
jobs  (ref_table, ref_id) → any of: model_groups | models | inferences
```

See [backend.md](./backend.md) for every column.

---

## 6. The async job system

A deliberately simple design that a future PR is expected to replace with a real queue:

- `jobs` is a SQLite table. Each row has a `job_type`
  (`panther_train` | `post_train_viz` | `inference`) and a polymorphic
  `(ref_table, ref_id)` pointer to the row it operates on.
- **One daemon thread** (`services/worker.py`) polls every 2 s, claims the oldest
  `queued` job, marks it `running`, dispatches to the registered handler, then marks it
  `succeeded`/`failed`. It never crashes the process — every handler exception is caught,
  logged, and recorded on the row.
- Every job streams a **log file** to `${VIZ_CACHE_ROOT}/job_logs/{job_id}.log`. The last
  ~8 000 chars are exposed via `GET /api/jobs/{id}` and shown in the UI's log viewer.
- **No cancellation.** There is no way to interrupt a running subprocess cleanly with a
  single thread; this is an explicit, documented limitation.

---

## 7. Configuration & deployment

All configuration is environment variables (see `backend/.env.example`):

| Var | Required | Purpose |
| --- | --- | --- |
| `TRIDENT_ALLOWED_ROOTS` | **yes (prod)** | Colon-separated absolute dirs the file browser may traverse. Defaults to `$HOME` in dev — a security boundary that **must** be set explicitly in production. |
| `TRIDENT_REPO_PATH` | yes | Local checkout of TRIDENT. |
| `TRIDENT_PYTHON` | no | Python interpreter with TRIDENT's deps (default `python`). |
| `PANTHER_REPO_PATH` | yes | Local checkout of PANTHER. `src/` is added to `sys.path` for the renderers; `src/datasets_splits/` must be writable. |
| `BAGHEERA_DB_PATH` | no | SQLite file (default `./bagheera.db`). |
| `DATASETS_SPLITS_ROOT` | no | Override for split output root. |
| `VIZ_CACHE_ROOT` | no | Where post-training viz + job logs land (default `./viz_cache`). **Use an absolute path in prod.** |
| `INFERENCE_ROOT` | no | Where per-inference outputs land (default `./inference_outputs`). **Use an absolute path in prod.** |

**Runtime layout:**

```
${VIZ_CACHE_ROOT}/
├── job_logs/{job_id}.log              one log per async job
└── {model_id}/                        post-training viz for a fold
    ├── heatmap_{slide}.png
    ├── topk_grid.png
    └── umap.png
${INFERENCE_ROOT}/
└── {model_id}/{inference_id}/         per-inference artifacts
    ├── custom_list.csv
    ├── trident_output/…/{slide}.h5
    ├── heatmap_{slide}.png  mixture_{slide}.png  tsne_{slide}.png
    └── example_patches_{slide}/prototype_{NN}/patch_{NN}.png
```

Both `viz_cache/` and `inference_outputs/` **grow unbounded** today — pruning is manual.

**Dev run:** `uvicorn app.main:app --reload --port 8000` in one terminal,
`npm run dev` (port 5173) in another. Vite proxies `/api/*` to the backend.

---

## 8. Security model

Bagheera has **no authentication**; its only trust boundary is path sandboxing:

- Every user-supplied path (`/api/fs/*`, `/api/trident/run`, `/api/splits`,
  `/api/inferences`) is resolved with `Path.resolve()` (which collapses `..` and follows
  symlinks) and **rejected unless it lands inside `TRIDENT_ALLOWED_ROOTS`**. This blocks
  traversal and symlink-escape even when a raw path is pasted into a form.
- Served visualization files (`/api/viz/{path}`) are constrained the same way to
  `VIZ_CACHE_ROOT` + `INFERENCE_ROOT`. Out-of-root absolute paths → 403; in-root but
  missing → 404.
- Dataset / model names are validated against `^[A-Za-z0-9_-]+$` and re-validated before
  being interpolated into any shell command (defense in depth).

---

## 9. Status: what's built vs. deferred

**Built and wired end-to-end:**

- TRIDENT sync run + run listing/resolution.
- K-fold split creation/listing.
- PANTHER K-fold async training (Model Group + K Models + job).
- Background worker with three real handlers (`panther_train`, `post_train_viz`,
  `inference`) and per-job log files.
- Models browser, group detail (favorites, prototype labels, notes, parameter panels,
  shuffle previews), and the full inference page (single + batch, caching, rerun).
- The six PANTHER renderers and per-inference visualizers.
- An idempotent demo seeder covering the UI's status matrix.

**Explicitly deferred / not built (candidate next work):**

- Job **cancellation** and migration to a real queue (Redis/RQ, Celery, …).
- **Multi-user** concurrency (today: one worker thread).
- **Auto-cleanup** of `viz_cache/` and `inference_outputs/` (grow unbounded).
- **WSI upload** through the browser (paths must already exist on the server).
- **MPP override** for slides without embedded resolution (PNG/JPEG inputs).
- "**Test on training-set slides**" mode on the inference page.
- **Cross-group** model comparison views.
- **Export** of labels / notes / inferences.
- **Authentication** / access control.

> ⚠️ **Validation caveat.** The visualization (`services/visualization.py`) and inference
> (`services/inference.py`) modules each open with a numbered list of assumptions about
> PANTHER's `.pkl` structure, TRIDENT's output paths, h5 conventions, GPU flags, etc.
> They were inferred from upstream source + a reference notebook but **never exercised on
> a real GPU**. The code is written to fail gracefully (clean job-log tracebacks,
> `status='failed'`), but each assumption should be verified on the first real run. See
> the module docstrings and [backend.md §Assumptions](./backend.md).
