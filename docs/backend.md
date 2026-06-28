# Bagheera — Backend Reference

> FastAPI service that drives the TRIDENT feature-extraction and PANTHER
> prototype-training pipelines, with a per-fold visualization layer and a
> per-slide inference flow on top.
>
> Read [structure.md](./structure.md) first for the big picture. This document is
> the working reference for the backend: stack, request flow, every module, the full
> HTTP API, the job system, the database, and the deploy-day assumptions.

---

## 1. Stack & conventions

| Concern | Choice |
| --- | --- |
| Language | Python 3.10+ (`from __future__ import annotations` everywhere) |
| Web framework | FastAPI `0.115` |
| Server | Uvicorn `0.32` (`uvicorn[standard]`) |
| ORM | SQLAlchemy `2.0` (typed `Mapped[...]` models) |
| DB | SQLite (`check_same_thread=False`, shared across the request threads + worker thread) |
| Validation | Pydantic `2.10` (`model_config = {"from_attributes": True}` for ORM→schema) |
| Multipart | `python-multipart` (declared; uploads not yet used) |

**Conventions worth knowing before editing:**

- **No migrations.** Schema is `Base.metadata.create_all()`. After any column change,
  delete `bagheera.db` and restart.
- **Heavy ML deps are imported lazily** *inside* functions (torch, openslide, h5py,
  sklearn, umap, matplotlib, PIL, cv2). The API boots fine without them; only the actual
  render/inference jobs need them. This is deliberate so the server runs on a dev laptop.
- **The worker must never crash the process.** Every handler runs inside a broad
  `try/except` that records the failure and keeps the loop alive.
- **Paths are a security boundary.** Any user-supplied path goes through
  `resolve_within_roots()` before use.

---

## 2. Application bootstrap (`app/main.py`)

```python
app = FastAPI(title="Bagheera", version="0.1.0", lifespan=lifespan)
```

On startup (`lifespan`):

1. `init_db()` — `create_all()` registers/creates every table.
2. `ensure_storage_dirs()` — creates `viz_cache/`, `inference_outputs/`,
   `viz_cache/job_logs/`.
3. `_register_handlers()` — registers the three **stub** handlers first, then lets the
   three **real** handlers (`panther_train`, `post_train_viz`, `inference`) overwrite
   their slots. (Pattern lets new job types be stubbed before they're implemented.)
4. `worker.start_worker()` — starts the background daemon thread.

On shutdown: `worker.stop_worker()`.

CORS is enabled for `http://localhost:5173` (dev). Routers are mounted in `main.py`:
`fs, trident, panther, runs, splits, models, labels, notes, inference, jobs, viz`.
Health check: `GET /api/health` → `{"status": "ok"}`.

---

## 3. Configuration (`app/config.py`)

A frozen `Settings` dataclass built from environment variables by `load_settings()`,
exposed as the module-level singleton `settings`.

| Field | Env var | Notes |
| --- | --- | --- |
| `allowed_roots: list[Path]` | `TRIDENT_ALLOWED_ROOTS` | Colon-separated; resolved+expanded. Defaults to `[$HOME]` (dev only). |
| `trident_repo_path` | `TRIDENT_REPO_PATH` | |
| `trident_python` | `TRIDENT_PYTHON` | Default `python`. |
| `panther_repo_path` | `PANTHER_REPO_PATH` | |
| `db_path` | `BAGHEERA_DB_PATH` | Default `./bagheera.db`. |
| `cors_origins` | (hardcoded) | `["http://localhost:5173"]`. |
| `datasets_splits_root` | `DATASETS_SPLITS_ROOT` | Defaults to `${PANTHER_REPO_PATH}/src/datasets_splits`. |
| `viz_cache_root` | `VIZ_CACHE_ROOT` | Default `./viz_cache`. Use an **absolute** path in prod. |
| `inference_root` | `INFERENCE_ROOT` | Default `./inference_outputs`. Use an **absolute** path in prod. |

> There's a `TODO` in `config.py` for an `/api/admin/cleanup` endpoint — the cache dirs
> grow unbounded today.

---

## 4. Database (`app/db/`)

`database.py` builds the engine (`sqlite:///{db_path}`), a `sessionmaker`
(`SessionLocal`), the declarative `Base`, and the `get_db()` FastAPI dependency.

`models.py` defines all tables. Full column reference:

### `TridentRun`
`id` (uuid), `created_at`, `dataset_name`, `wsi_dir`, `patch_encoder`, `mag`,
`patch_size`, `command`, `status` (`pending|running|succeeded|failed`), `stdout`,
`stderr`, `output_dir` (canonical features dir), `return_code`.

### `Split`
`id`, `created_at`, `dataset_name` (idx), `split_name` (unique), `abs_path`,
`source_csv`, `k`, `seed`, `total_rows`, `per_fold_counts` (JSON
`list[{train,val,test}]`).

### `ModelGroup`
`id` (== `group_id`), `created_at`, `display_name`, `dataset_name` (idx),
`trident_run_id` (FK, nullable), `k`, `split_id` (FK).

### `Model`
The central row. `id`, `created_at`; naming (`base_name`, `model_name` (unique),
`display_name`); grouping (`group_id` (idx), `fold_index`, `fold_k`); inputs
(`dataset_name`, `features_dir`, `trident_run_id`, `split_id`, `split_name`,
`split_dir_abs`); PANTHER hyperparams (`mode`, `in_dim`, `n_proto_patches`, `n_proto`,
`n_init`, `seed`, `num_workers`); outcome (`status` `pending|running|ready|failed`,
`prototypes_dir`, `prototype_files` JSON); `is_favorite`; and viz artifacts (`viz_status`
`pending|rendering|ready|failed`, `preview_slide_ids` JSON, `preview_heatmap_paths` JSON,
`topk_grid_path`, `topk_per_proto`, `umap_path`). Unique `(group_id, fold_index)`.

### `PantherRun`
Per-fold execution log: `id`, `created_at`, `group_id` (idx), `fold_index`, `model_id`
(FK), the inputs + hyperparams (denormalized), `command`, `status`, `stdout`, `stderr`,
`return_code`, `started_at`, `finished_at`.

### `PrototypeLabel`
`id`, `created_at`, `updated_at`, `model_id` (FK), `prototype_index`, `label`. Unique
`(model_id, prototype_index)`.

### `ModelNote`
`id`, `created_at`, `updated_at`, `model_id` (FK, idx), `body`.

### `InferenceBatch`
`id`, `created_at`, `model_id` (FK, idx), `user_label`, `total_count`.

### `Inference`
`id`, `created_at`, `finished_at`, `model_id` (FK, idx), `batch_id` (FK, nullable);
slide identity (`wsi_path`, `wsi_filename`, `wsi_mtime`, `wsi_size`, `wsi_hash`);
outputs (`output_dir`, `features_h5_path`, `heatmap_path`, `mixture_plot_path`,
`example_patches_dir`, `tsne_path`); `status`
(`queued|running_trident|running_viz|ready|failed`), `error_message`. Unique
`(model_id, wsi_hash)` — the cache key.

### `InferenceNote`
`id`, `created_at`, `updated_at`, `inference_id` (FK, idx), `body`.

### `Job`
`id`, `created_at` (idx), `started_at`, `finished_at`, `job_type` (idx),
`ref_table`, `ref_id` (the polymorphic pointer), `status`
(`queued|running|succeeded|failed`, idx), `error_message`, `log_path`.

---

## 5. The async job system (`services/worker.py`)

The heart of all long-running work.

```
start_worker() → daemon thread → _worker_loop()
   every 2 s:  _claim_next_job(db)         # oldest queued → running
               _run_one_job(job)           # dispatch to handler, mark done/failed
```

- **`register_handler(job_type, fn)` / `get_handler(job_type)`** — a `dict` registry.
  Handlers conform to `JobHandler`: `(*, db, job, log) -> None`.
- **`enqueue_job(db, *, job_type, ref_table, ref_id) -> Job`** — inserts a `queued` row;
  the worker picks it up. Used by the route layer and by handlers that fan out
  (`panther_train` enqueues `post_train_viz`).
- **`JobLog`** — a line-buffered append-only file at
  `${VIZ_CACHE_ROOT}/job_logs/{job_id}.log`, always flushed.
- **`tail_log(job, max_chars=8000)`** — returns the trailing slice for the API/UI.
- **Failure handling** — any handler exception is caught in `_run_one_job`: the log gets
  the traceback, the `jobs` row gets `status='failed'` + `error_message` (first 2000
  chars). The loop survives.
- **No cancellation, no priorities.** Documented as out of scope until a real queue
  replaces the single thread.
- **Retry** — `POST /api/jobs/{id}/retry` re-queues a `failed`/`succeeded` job by
  resetting its status and bumping `created_at` (so it sorts after current queue).

The three real handlers:

| Handler | File | Does |
| --- | --- | --- |
| `panther_train` | `panther_train.py` | For a Model Group, runs K PANTHER subprocesses sequentially (one `PantherRun` row each); sets each Model `ready`/`failed`; enqueues a `post_train_viz` per successful fold. |
| `post_train_viz` | `post_train_viz.py` | For one Model: renders ≤3 preview heatmaps, the top-K grid, the UMAP, and the **Section A** panel (thumbnail + hi-res assignment map + π_c bars + index-0 ROI, for one deterministic slide via `pick_preview_slides(count=1)`); writes `model.viz_artifacts={"section_a":{...}}` + a repick `.npz` cache; sets `viz_status`. Per-step `try/except` → partial output still publishes. |
| `inference` | `inference_job.py` | For one Inference: hash slide → run TRIDENT → locate `.h5` → render heatmap/mixture/example-patches/t-SNE → `ready` if ≥1 render succeeded. |

---

## 6. Services layer (module by module)

### `fs.py` — sandboxed filesystem
- `resolve_within_roots(raw)` — the security primitive. Resolves the path and raises
  403 unless it sits inside `settings.allowed_roots`. Used by **every** route that
  accepts a path.
- `list_directory(...)` — returns `(target, parent, entries, is_root)` with hidden-file
  and dirs-only filtering; sorts dirs first.

### `runner.py` — TRIDENT subprocess (synchronous)
- Encoder→patch-size map (`uni_*`→256, `phikon*`→224); `MAGNIFICATION=20`; `TASK=all`.
- `build_command(...)` → argv for `bash run_trident.sh ...`; `output_dir_for(...)` builds
  the canonical `{job_dir}/{mag}x_{ps}px_0px_overlap/features_{encoder}` path.
- `execute(cmd)` — `subprocess.Popen(...).communicate()`, **blocking**. Used only for the
  initial dataset build.

### `splitter.py` — K-fold CV
- `create_kfold_split(...)` — shuffles rows with `Random(seed)`, chunks into K, writes
  `k=i/{train,val,test}.csv` where `test=chunk[i]`, `val=chunk[(i+1)%K]`, `train=rest`.
  Writes a `metadata.json`. Invariant: every row is in `test` exactly once.
- **slide_id validation + .tif auto-fix:** detects the slide-id column case-insensitively
  against the shared `SLIDE_ID_COLUMNS` (from `preview.py`). If none is present, raises
  `SplitterError` → HTTP 400 (PANTHER never gets an unusable CSV). Otherwise strips a
  trailing `.tif`/`.tiff` from that column's values before writing the generated CSVs
  (the source CSV on the read-only `/data` mount is never modified). `metadata.json`
  records `slide_id_column` and `slide_id_normalized`.

### `panther_runner.py` — PANTHER subprocess + paths
- Path helpers: `datasets_splits_root_abs`, `fold_dir_abs`, `fold_dir_rel` (relative path
  passed to PANTHER, whose cwd is `${PANTHER_REPO_PATH}/src`).
- `build_command(PantherFoldArgs)` → argv for `bash run_panther.sh ...`.
- `execute(cmd, *, cwd)` — runs with `CUDA_VISIBLE_DEVICES=0`, blocking (called from the
  worker thread, so it doesn't block HTTP).
- `scan_prototype_files(dir)` — lists `.pkl`/`.pt` outputs to decide success.

### `preview.py` — deterministic preview-slide picking
- `read_slide_ids_from_train_csv(...)` — tolerant slide-id column detection
  (`slide_id|case_id|slide|id`, else first column).
- `pick_preview_slides(model, count=3)` — seeded by `model.id:seed:fold_index`, so the
  same model always previews the same slides. Shared by the shuffle route and the viz
  handler.

### `inference.py` — per-WSI inference helpers (pure functions)
- `compute_wsi_hash(path)` — streamed sha256 (1 MB chunks).
- `lookup_cached_inference(db, model_id, path)` — pre-checks `(mtime, size)` then confirms
  by hash; the hash is the source of truth.
- `inherited_trident_params(model, db)` — resolves the encoder/mag/patch_size a fold was
  trained against (from its `TridentRun`). Drives both the inference command and the
  `/trident-params` endpoint so they always agree.
- `build_trident_command(...)`, `generate_custom_wsi_csv(...)`, `locate_features_file(...)`,
  `inference_output_dir(model_id, inference_id)` — TRIDENT plumbing for one slide.

### `visualization.py` — the renderers
Lazy PANTHER bootstrap (`_ensure_panther_on_syspath` prepends `${PANTHER_REPO_PATH}/src`),
a local `_load_panther_encoder` that works around an upstream `get_panther_encoder`
hardcoded-`n_proto` bug, and:

| Function | Scope | Output |
| --- | --- | --- |
| `render_assignment_heatmap(model, h5, wsi, *, downsample_target=128, out_path=None)` | per-slide | `heatmap_{stem}.png` |
| `render_assignment_heatmap_from_assignments(model, coords, labels, ps, wsi, *, downsample_target=128, out_path=None)` | per-slide | painted heatmap from precomputed assignments (no encoder run) |
| `render_mixture_plot(model, h5)` | per-slide | `mixture_{stem}.png` |
| `render_example_patches(model, h5, wsi, k=4)` | per-slide | dir of `prototype_NN/patch_NN.png` |
| `render_tsne_per_slide(model, h5, wsi)` | per-slide | `tsne_{stem}.png` |
| `render_topk_grid(model, feats_dir, wsi_dir, per_proto=3)` | dataset-wide | `topk_grid.png` |
| `render_umap(model, feats_dir)` | dataset-wide | `umap.png` |

Cost caps: UMAP samples ≤500 patches/slide, ≤50 000 total; top-K streams every h5 once
keeping a per-prototype heap.

**Section A (Analysis page per-slide panel).** Mirrors the PANTHER paper figure; all
artifacts land under `viz_cache/{model_id}/section_a/`.

| Function | Output | Notes |
| --- | --- | --- |
| `render_wsi_thumbnail(model, wsi)` | `section_a/thumbnail_{stem}.png` | Downscaled H&E (longest side ≤ `THUMB_MAX_PX=2048`) with a physical scale bar from openslide `MPP_X`. **If MPP is missing, the thumbnail renders without a scale bar — never fails.** |
| `render_pi_c_barplot(model, mixture_probs)` | `section_a/pi_c.png` | One bar per prototype, **each bar colored by `get_default_cmap(n_proto)`** (same cmap as the assignment map). X labels `C1..Cn`, y label `Proportion π_c`. Takes the GMM `mixture_probs` directly (the third return of `_compute_assignments`). |
| `render_assignment_heatmap_from_assignments(..., downsample_target=SECTION_A_DOWNSAMPLE=24, out_path=section_a/assignment_map_{stem}.png)` | `section_a/assignment_map_{stem}.png` | Hi-res (zoomable) reuse of the existing heatmap renderer with a smaller downsample target. |
| `render_roi_from_assignments(model, coords, labels, ps, wsi, roi_index)` → `(raw, colored, [x,y,w,h], used_idx, n_windows)` | `section_a/roi_raw_{stem}_{idx}.png`, `section_a/roi_colored_{stem}_{idx}.png` | Deterministically picks a `ROI_GRID×ROI_GRID` (7×7) tile of patches by ranking non-overlapping windows (**diversity then density**); `roi_index` selects the i-th (wraps via modulo, so the UI can "repick"). `raw` = openslide `read_region` of the window + scale bar; `colored` = the window tiled as its patches, each blended with its prototype color. |
| `render_roi(model, h5, wsi, roi_index=0)` → `(raw, colored, [x,y,w,h])` | same as above | Convenience wrapper that runs the encoder, then calls `render_roi_from_assignments`. |

**Repick cache.** `save_section_a_cache(model, slide_id, coords, labels, patch_size)` writes
`section_a/roi_cache.npz` (coords + cluster_labels) and `section_a/roi_cache.json`
(slide_id + patch_size); `load_section_a_cache(model)` reads them back. This lets the
repick-ROI endpoint re-tile **without re-running the encoder**.

---

## 7. HTTP API reference

All under `/api`. Schemas live in `app/models/schemas.py`; the interactive spec is at
`http://localhost:8000/docs`.

### Filesystem — `routes/fs.py`
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/fs/roots` | Configured allowed roots. |
| GET | `/api/fs/list?path=&filter=dirs_only&show_hidden=` | Sandboxed directory listing. |
| GET | `/api/fs/csv-count?path=` | Row count of a CSV (header skipped). |
| GET | `/api/fs/csv-inspect?path=` | CSV diagnostics: `{rows, columns[], has_slide_id, slide_id_column, tif_count, sample_ids[]}`. Detects the slide-id column case-insensitively (shared `SLIDE_ID_COLUMNS`); `tif_count` = values ending in `.tif`/`.tiff`. Lazy `pandas` import. |

### TRIDENT — `routes/trident.py` + `routes/runs.py`
| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/trident/run` | Run feature extraction **synchronously** (blocks). |
| GET | `/api/trident/runs` | List runs. |
| GET | `/api/trident/runs/{id}` | One run. |
| GET | `/api/runs/resolve?features_dir=` | Map a features dir back to its `TridentRun` (400 on miss, 409 if ambiguous). |

### Splits — `routes/splits.py`
| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/splits` | Create a K-fold split from a source CSV. |
| GET | `/api/splits[?dataset_name=]` | List splits. |
| GET | `/api/splits/{id}` | One split. |

### PANTHER training — `routes/panther.py`
| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/panther/runs` | Create Model Group + K Models, enqueue `panther_train`, return `{group_id, job_id, k, split_id, split_name, model_ids}`. |
| GET | `/api/panther/runs[?group_id=]` | List per-fold execution logs (`PantherRun`). |
| GET | `/api/panther/models[?group_id=&dataset_name=]` | List fold Models. |

### Model groups & models — `routes/models.py`
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/model-groups[?favorite_only=&dataset_name=&q=&sort=]` | List groups with aggregated fold summary. |
| GET | `/api/model-groups/{id}` | Group + its models + the split. |
| PATCH | `/api/model-groups/{id}` | Rename (cascades `display_name` to fold models). |
| DELETE | `/api/model-groups/{id}` | Delete the group, all fold models, and dependent rows (`InferenceNote → Inference → InferenceBatch → PrototypeLabel → ModelNote → PantherRun → Model`, then `ModelGroup`) in one transaction, plus on-disk `viz_cache/{model_id}`, `inference_outputs/{model_id}`, and each `prototypes_dir`. Shared `Split`/`TridentRun` untouched. 404 if missing; **409** if a fold is `running` or an active (`queued`/`running`) job references the group/models. Returns a delete summary. Logic in `services/model_delete.py`. |
| GET | `/api/models/{id}` | One model. Response includes `viz_artifacts` (parsed from the JSON column; null until rendered). |
| PATCH | `/api/models/{id}` | Set `is_favorite` / `display_name`. |
| POST | `/api/models/{id}/shuffle-preview` | Re-pick 3 preview slides + enqueue a `post_train_viz` re-render. |
| POST | `/api/models/{id}/repick-roi` | Re-render the Section A ROI at the **next** window (wraps around), update `viz_artifacts.section_a.roi_*`/`roi_bbox`/`roi_index`, return the updated `ModelInfo`. **Synchronous** (uses the cached coords/labels — no encoder run). 404 missing model; **409** if Section A isn't rendered yet (no `section_a` / no repick cache / WSI gone); 422 if the slide has no tissue window. |
| GET | `/api/models/{id}/trident-params` | The encoder/mag/patch_size/gpus a model inherits, + expected features dir name. |

`ModelInfo.viz_artifacts` is the parsed `Model.viz_artifacts` JSON column (null-safe), also
included in the group-detail response (`/api/model-groups/{id}` reuses `_model_to_info`).
The Section A shape:

```json
{ "section_a": {
    "slide_id": "<deterministic preview slide stem>",
    "thumbnail": "<abs viz path>",
    "assignment_map": "<abs viz path>",
    "pi_c": "<abs viz path>",
    "roi_raw": "<abs viz path>",
    "roi_colored": "<abs viz path>",
    "roi_bbox": [x, y, w, h],
    "roi_index": 0
} }
```

All paths are absolute `viz_cache` paths served by `GET /api/viz/{path}`. Any individual
render that fails is simply absent from the dict (partial success still publishes).

### Prototype labels — `routes/labels.py`
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/prototype-labels?model_id=` | List. |
| POST | `/api/prototype-labels` | Upsert one label (validates `index < n_proto`). |
| DELETE | `/api/prototype-labels/{id}` | Delete. |

### Model notes — `routes/notes.py`
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/model-notes?model_id=` | List. |
| POST | `/api/model-notes` | Create. |
| PATCH | `/api/model-notes/{id}` | Edit. |
| DELETE | `/api/model-notes/{id}` | Delete. |

### Inferences — `routes/inference.py`
| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/inferences` | Single/batch dispatch. Validates every path; cache-hits short-circuit unless `rerun`; creates a batch when >1 valid; returns `207` on partial validation failure. |
| GET | `/api/inferences/lookup?model_id=&wsi_path=` | Cache check (404 = no hit). |
| GET | `/api/inferences[?model_id=&batch_id=&status=&limit=]` | List. |
| GET | `/api/inferences/{id}` | One inference. |
| GET | `/api/inferences/{id}/example-patches` | Walk `example_patches_dir` → groups of `/api/viz/` URLs per prototype (with labels). |
| POST | `/api/inferences/{id}/rerun` | Delete the cached row (+ its notes) and queue a fresh run. |
| GET | `/api/inference-batches/{id}` | Batch metadata. |
| GET/POST | `/api/inference-notes[?inference_id=]` | List / create. |
| PATCH/DELETE | `/api/inference-notes/{id}` | Edit / delete. |

### Jobs — `routes/jobs.py`
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/jobs[?status=&ref_table=&ref_id=&job_type=&limit=]` | List jobs. |
| GET | `/api/jobs/{id}` | Job + `log_tail`. |
| POST | `/api/jobs/{id}/retry` | Re-queue a terminal job. |

### Visualization — `routes/viz.py`
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/viz/placeholder/{kind}?label=&width=&height=` | Synthesized SVG placeholder (`heatmap|mixture|patches|tsne|topk|umap`). |
| GET | `/api/viz/{file_path:path}` | Serve a real rendered file from `VIZ_CACHE_ROOT` or `INFERENCE_ROOT`. Absolute or root-relative; out-of-root → 403, missing → 404. |

---

## 8. Bash wrappers (`backend/scripts/`)

Intentionally thin so the exact upstream invocations stay visible:

- **`run_trident.sh`** — checks `TRIDENT_REPO_PATH`, then
  `exec $TRIDENT_PYTHON $TRIDENT_REPO_PATH/run_batch_of_slides.py "$@"`.
- **`run_panther.sh`** — `exec python -m training.main_prototype "$@"` (the backend sets
  cwd + `CUDA_VISIBLE_DEVICES` before calling).

---

## 9. Deploy-day assumptions to validate

The renderers and inference plumbing were written by reading upstream source + a reference
notebook, **without a GPU to run them end-to-end**. Each risky inference is documented as a
numbered assumption in the module docstring. Verify these on the first real run:

- **`services/visualization.py`** — 11 assumptions: prototype `.pkl` structure
  (`{'prototypes': ndarray}`), `PrototypeTokenizer(out_type='allcat')`, the
  `get_panther_encoder` hardcoded-`n_proto` workaround, `representation()` return shape,
  h5 keys (`features`/`coords`/`coords.attrs['patch_size']`), WSI file discovery by stem,
  `configs/` dir, `sys.path` injection, lazy heavy imports, and UMAP/top-K cost caps.
- **`services/inference.py`** — 10 assumptions: the `--custom_list_of_wsis` CSV format
  (header `wsi`, value = basename), `--gpus` shape, that `TridentRun` stores no GPU config
  (defaults `"0"`), the TRIDENT output path pattern, WSI stem == basename, single-slide
  filtering, cwd, hashing cost, cache invalidation, and graceful subprocess failure.
- **`routes/viz.py`** — its docstring is a deploy-day checklist (absolute roots,
  readability, content-type inference).

Most first-deploy failures fall into: env not loaded into uvicorn's process; PANTHER's
deps missing from the venv; wrong `PANTHER_REPO_PATH`; TRIDENT writing the h5 to a
different path than `locate_features_file` expects; or `VIZ_CACHE_ROOT`/`INFERENCE_ROOT`
mismatching where renderers wrote. See `backend/README.md` for the symptom→fix table.

For containerized GPU deployment (one shared venv with TRIDENT/PANTHER baked in, all
paths as in-container volume mounts), see [`docs/docker.md`](docker.md).

---

## 10. Seeding demo data (`scripts/seed_demo.py`)

```bash
.venv/bin/python scripts/seed_demo.py            # idempotent: wipe [SEED] + recreate
.venv/bin/python scripts/seed_demo.py --reset    # wipe [SEED] only
```

Inserts 4 model groups across 2 datasets covering the UI's status matrix (K=3 rendering,
K=5 all-ready, K=5 mixed-failure, K=10 all-ready) plus 3 demo inferences. Every seed row
carries a `[SEED]` prefix so it's never confused with real data, and viz path columns
point at the `placeholder` endpoint so the UI renders without files on disk.

---

## 11. Known limitations

- Single worker thread → no concurrency, **no job cancellation**.
- `viz_cache/` and `inference_outputs/` **grow unbounded** (manual pruning for now).
- TRIDENT's initial run is **synchronous** — the HTTP request blocks for the full run.
- **No auth.**
- No WSI upload, no MPP override, no cross-group comparison, no export — see
  [structure.md §9](./structure.md).
