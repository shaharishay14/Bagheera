# Bagheera — Project Structure & Architecture

> A web GUI for orchestrating the **TRIDENT** (feature extraction) and **PANTHER**
> (prototype training) computational-pathology pipelines, plus a per-model
> visualization layer, a side-by-side model-comparison view, and a per-slide inference
> flow on top.
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
| **PANTHER** | `github.com/mahmoodlab/PANTHER` | Learns a set of *prototypes* (representative tissue patterns) over those features via an unsupervised mixture model. New runs train one model on all slides; legacy K-fold data is still supported. |

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
   CSV manifest ──split──▶ Split  (single "100% train" fold, or legacy K-fold)
                                │
                                ▼
        one PANTHER submission = one standalone  Model  (trained on all slides)
                                │
                                ▼
                    Inference (run a Model on a NEW slide)
```

- **TRIDENT run** — one feature-extraction job over a directory of WSIs.
- **Split** — a partition of a dataset's slides written to disk as
  `train.csv` / `val.csv` / `test.csv` per fold. New runs use a **single** fold that is
  **100% train / 0% val / 0% test** (`create_single_split`, `k=1`, split name
  `alltrain_seed_{seed}_{rand8}`). The legacy **K-fold** shape (every slide in `test`
  exactly once across K folds) is still supported for existing data.
- **Model** — a single trained PANTHER model: its prototypes (`.pkl`), hyperparameters,
  training status, and pre-rendered visualization artifacts (Section A/B/C/D panels, a
  UMAP, per-slide renders). A standalone model carries `run_kind="single"`,
  `group_id == model.id`, `fold_index=0`, `fold_k=1`, and no `ModelGroup` row.
- **Model Group** *(legacy, read-only)* — the result of one *old* K-fold PANTHER
  submission; owns **K Models** (one per fold, `run_kind IS NULL`). No new groups are
  created — existing ones stay viewable but are excluded from every "create new" flow.
- **Inference** — running one trained Model against one new WSI: TRIDENT extracts
  that slide's features, then PANTHER-based renderers produce per-slide visualizations.
  Cached by a hash of the slide so the same (model, slide) pair is never recomputed.

> **Why the shift?** PANTHER's unsupervised prototype fit has no held-out label to
> validate against, so K-fold added complexity without a payoff for this UI. A new run
> now trains **one** model on **all** slides; cross-model inspection moved to the
> **Model Comparison** page (§3). The five nouns are unchanged — "Model Group" simply
> became a legacy container.

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
│ Create a new single "100% train" split (from a CSV) OR pick an  │
│ existing one. Set PANTHER hyperparameters.                      │
│ POST /api/panther/single-runs  →  creates ONE standalone Model  │
│ (no Model Group), enqueues ONE async `panther_train` job        │
│ (`ref_table="models"`), returns immediately, and the UI         │
│ navigates to the model's detail page (/models/:modelId).        │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─ background worker thread (polls the `jobs` table every 2 s) ───┐
│ panther_train:  branches on `job.ref_table`.                    │
│                 "models" (new): trains one Model on the single  │
│                   split → enqueues one `post_train_viz`.        │
│                 "model_groups" (legacy): K subprocesses in      │
│                   sequence → a `post_train_viz` per fold.       │
│ post_train_viz: renders Section A (per-slide panel) + B (val    │
│                 consistency, skipped for single runs) + C       │
│                 (on-tissue UMAP + scatter) + D (prototype       │
│                 dictionary) + per-slide violin for one Model.   │
│ render_slide:   on-demand per-slide render for the Compare page │
│                 (Section A + on-tissue + violin, memoized).     │
│ inference:      runs TRIDENT on a new slide, then renders        │
│                 heatmap / mixture / example patches / t-SNE.    │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─ /models  (+ /models/:modelId, /models/group/:groupId) ─────────┐
│ Browse standalone models (flat cards) + legacy K-fold groups    │
│ (chip-tagged). Open a model to inspect its analysis panels,     │
│ prototype labels, notes, parameters, ROI controls, and a link   │
│ into inference. Legacy groups open the per-fold group view.     │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─ /training/panther/compare ─────────────────────────────────────┐
│ Pick a dataset → a WSI (thumbnail grid) → add up to 4 non-      │
│ legacy models. Each panel renders that slide's Section A +      │
│ per-slide violin + Section C + Section D side by side (1–3 = a  │
│ row, 4 = 2×2), with an optional Sync-zoom/pan toggle. Compute   │
│ goes through the SAME single worker via `render_slide` jobs.    │
└─────────────────────────────────────────────────────────────────┘
                            │
┌─ /models/:modelId/inference ────────────────────────────────────┐
│ Pick one or many new WSIs. Cache pre-check shows which are      │
│ already computed. Run → poll → view per-slide visualizations.   │
└─────────────────────────────────────────────────────────────────┘
```

**Why two execution styles?** The *initial* TRIDENT dataset build is synchronous (one
user → one run, blocking is acceptable and simplest). PANTHER training, per-slide
rendering, and inference are *async* through the worker thread because they run heavy GPU
subprocesses (legacy K-fold training runs K of them sequentially) and must not block the
request.

---

## 4. Repository layout

```
Bagheera/
├── README.md                     Top-level setup + quickstart
├── .gitignore
├── docs/                         ← these documents
│   ├── structure.md
│   ├── backend.md
│   ├── frontend.md
│   ├── database.md
│   ├── queue-design.md
│   ├── tests.md
│   └── docker.md
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
│   │   │   ├── datasets.py        Model Comparison dataset/slide/model lookups
│   │   │   ├── thumbnails.py      WSI slide-picker thumbnails
│   │   │   └── queue.py           Queue listing / reorder
│   │   └── services/             Business logic (the interesting part)
│   │       ├── fs.py              Sandboxed filesystem access
│   │       ├── runner.py          TRIDENT subprocess (sync)
│   │       ├── splitter.py        Split generation (single "100% train" + legacy K-fold)
│   │       ├── panther_runner.py  PANTHER subprocess + path helpers
│   │       ├── worker.py          Background job worker thread + job log files
│   │       ├── job_handlers.py    Stub handlers (overwritten by real ones)
│   │       ├── panther_train.py   Real `panther_train` handler (single + legacy K-fold)
│   │       ├── post_train_viz.py  Real `post_train_viz` job handler
│   │       ├── render_slide.py    Real `render_slide` handler (Compare per-slide render)
│   │       ├── inference.py        Inference helpers (hash, cache, TRIDENT cmd)
│   │       ├── inference_job.py    Real `inference` job handler
│   │       ├── visualization.py    The PANTHER renderers (Section A–D, heatmap/umap/…)
│   │       ├── assignment_cache.py In-memory per-(model,slide) encoder-pass memoizer
│   │       ├── thumbnails.py       TRIDENT/openslide slide-picker thumbnails
│   │       ├── model_delete.py     Cascading group/model delete
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
        │   ├── PantherComparePage.tsx     Model Comparison (dataset→slide→models)
        │   ├── ModelsBrowserPage.tsx      ModelDetailPage.tsx   GroupDetailPage.tsx
        │   └── InferencePage.tsx
        └── components/         Reusable UI
            ├── DirectoryBrowser.tsx   EncoderSelect.tsx   ZoomPanImage.tsx
            ├── TridentForm.tsx        PantherForm.tsx
            ├── JobStatusPoller.tsx    JobLogViewer.tsx
            ├── NotesThread.tsx        PrototypeLabels.tsx
            ├── SectionAPanel.tsx      SectionBPanel.tsx   SectionCPanel.tsx
            ├── SectionDPanel.tsx      ViolinPanel.tsx     CompareModelPanel.tsx
```

---

## 5. Data model (database tables)

SQLite, created via `Base.metadata.create_all()` — **there are no migrations**. After a
schema change you delete `bagheera.db` and let it recreate.

| Table | One row per… | Key relationships |
| --- | --- | --- |
| `trident_runs` | TRIDENT feature-extraction run | — |
| `splits` | split on disk (unique `split_name`); single "100% train" (`k=1`) or legacy K-fold | — |
| `model_groups` | *(legacy only)* one old K-fold submission | → `splits`, → `trident_runs` (nullable). **No new rows** — single runs skip this table. |
| `models` | one trained model (standalone `run_kind="single"`, or a legacy fold) | → `model_groups` (via `group_id`; == `model.id` for single runs), → `splits`, → `trident_runs`; unique `(group_id, fold_index)` |
| `panther_runs` | one training subprocess attempt (exec log) | → `models` |
| `prototype_labels` | one label on one prototype | → `models`; unique `(model_id, prototype_index)` |
| `model_notes` | a free-text note on a model | → `models` |
| `inference_batches` | a group of inferences submitted together | → `models` |
| `inferences` | one (model, WSI) run | → `models`, → `inference_batches`; unique `(model_id, wsi_hash)` |
| `inference_notes` | a free-text note on an inference | → `inferences` |
| `jobs` | one async unit of work | polymorphic `(ref_table, ref_id)`; optional `params` JSON (carries `slide_id` for `render_slide`) |

**Additive schema notes (no wipe):** `models.run_kind` (`"single"` for standalone runs,
`NULL` for legacy folds) and `jobs.params` (per-job JSON, e.g. `{"slide_id": ...}`) were
both added via `ALTER TABLE` guards in `init_db()`. New single runs create a `Model` +
`Split` but **no `model_groups` row**.

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
  (`panther_train` | `post_train_viz` | `render_slide` | `inference`), an optional
  `params` JSON blob (e.g. `{"slide_id": ...}` for `render_slide`), and a polymorphic
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
├── slide_thumbs/{key}.jpg             generated WSI-picker thumbnails (cached)
└── {model_id}/                        post-training viz for a model
    ├── heatmap_{slide}.png  umap.png
    ├── section_a/ … section_b/ … section_c/ … section_d/   Analysis-page panels
    └── compare/{slide_id}/            on-demand per-slide render + manifest.json
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
- Split creation/listing: **single "100% train"** (`kind="single"`, the default for new
  runs) and legacy **K-fold**.
- PANTHER async training: **single standalone Model** (`POST /api/panther/single-runs`,
  no Model Group) for new runs; legacy K-fold (`POST /api/panther/runs`) still works.
- Background worker with four real handlers (`panther_train` — branches single vs.
  legacy K-fold —, `post_train_viz`, `render_slide`, `inference`) and per-job log files.
- Models browser (flat standalone models + chip-tagged legacy groups), a standalone
  `ModelDetailPage` and the legacy `GroupDetailPage` (favorites, prototype labels, notes,
  parameter panels, shuffle previews, Section A ROI **Repick** + manual **Select**), and
  the full inference page (single + batch, caching, rerun).
- **Model Comparison page** (`/training/panther/compare`): dataset → WSI (thumbnail
  grid) → up to 4 non-legacy models rendered side by side for one slide, with an optional
  synced zoom/pan. Compute reuses the single worker via `render_slide` jobs; per-slide
  encoder passes are memoized (`services/assignment_cache.py`).
- The PANTHER renderers (Section A–D + per-slide violin) and per-inference visualizers.
- Slide-picker thumbnails (`GET /api/slide-thumbnail`; TRIDENT thumbnail if present, else
  generated + cached).
- An idempotent demo seeder covering the UI's status matrix.

**Explicitly deferred / not built (candidate next work):**

- Job **cancellation** and migration to a real queue (Redis/RQ, Celery, …).
- **Multi-user** concurrency (today: one worker thread).
- **Auto-cleanup** of `viz_cache/` and `inference_outputs/` (grow unbounded).
- **WSI upload** through the browser (paths must already exist on the server).
- **MPP override** for slides without embedded resolution (PNG/JPEG inputs).
- "**Test on training-set slides**" mode on the inference page.
- **Export** of labels / notes / inferences.
- **Authentication** / access control.
- **Reviving K-fold** as a first-class "create new" flow (currently legacy/read-only).

> ⚠️ **Validation caveat.** The visualization (`services/visualization.py`) and inference
> (`services/inference.py`) modules each open with a numbered list of assumptions about
> PANTHER's `.pkl` structure, TRIDENT's output paths, h5 conventions, GPU flags, etc.
> They were inferred from upstream source + a reference notebook but **never exercised on
> a real GPU**. The code is written to fail gracefully (clean job-log tracebacks,
> `status='failed'`), but each assumption should be verified on the first real run. See
> the module docstrings and [backend.md §Assumptions](./backend.md).
>
> ⚠️ **F3 thumbnail caveat (unverified).** The exact TRIDENT thumbnail subpath/extension
> (`{job_dir}/thumbnails/{slide}.{jpg|jpeg|png}`) that `services/thumbnails.py` probes was
> **not confirmed against a real dataset**. `GET /api/datasets/{name}/slides` returns a
> `thumbnails_found` diagnostic to expose a mismatch on the first real run; if it comes
> back 0 while thumbnails clearly exist on disk, update `_TRIDENT_THUMB_EXTS` /
> `find_trident_thumbnail`. Thumbnail generation falls back to openslide, so the picker
> still works either way.
