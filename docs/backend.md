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
`fs, datasets, trident, panther, runs, splits, models, labels, notes, inference,
jobs, queue, viz, thumbnails`.
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
(`queued|running|succeeded|failed|canceled`, idx), `error_message`, `log_path`,
`queue_position` (int|null), `params` (TEXT|null — per-job JSON parameter blob,
e.g. `{"slide_id": ...}` for `render_slide`; read by handlers via
`json.loads(job.params or "{}")`). Both trailing columns are additive (`ALTER
TABLE` guards in `init_db()`).

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
- **`enqueue_job(db, *, job_type, ref_table, ref_id, params: dict | None = None) -> Job`** —
  inserts a `queued` row; the worker picks it up. Used by the route layer and by
  handlers that fan out (`panther_train` enqueues `post_train_viz`). `params` is
  JSON-serialized into the `jobs.params` column (`None` → NULL); the handler reads
  it back via `json.loads(job.params or "{}")` (e.g. `render_slide` passes
  `{"slide_id": ...}`).
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
| `panther_train` | `panther_train.py` | Branches on `job.ref_table`. `"model_groups"` (legacy K-fold): loads the Model Group, runs K PANTHER subprocesses sequentially (one `PantherRun` row each), sets each Model `ready`/`failed`, enqueues a `post_train_viz` per successful fold. `"models"` (standalone single run): loads ONE Model + its Split, runs `_train_one_fold` once (fold 0), sets the Model `ready`/`failed`, and on success enqueues a single `post_train_viz` (`ref_table="models"`). The `PantherRun` row it writes carries `group_id = model.group_id` (== `model.id` for single runs). |
| `post_train_viz` | `post_train_viz.py` | For one Model: renders ≤3 preview heatmaps, the **Section D** prototype dictionary (supersedes the top-K grid — `topk_grid_path` is no longer set), the UMAP, and the **Section A** panel (thumbnail + hi-res assignment map + π_c bars + index-0 ROI, for one deterministic slide via `pick_preview_slides(count=1)`), the **Section C** on-tissue 2D-embedding map (`render_umap_on_tissue` for that same slide), and the **Section B** validation-consistency charts (`render_validation_consistency` — encoder over the fold's val + sampled train slides; skipped if no val slides), and the **per-slide violin** (`render_slide_violin` for the same preview slide, stored under the distinct `section_b_violin` key); merges all into `model.viz_artifacts={"section_a":{...},"section_b":{...},"section_b_violin":{...},"section_c":{...},"section_d":{...}}` (load-merge-dump, never clobbering a sibling section) + a repick `.npz` cache; sets `viz_status`. Per-step `try/except` → partial output still publishes. |
| `inference` | `inference_job.py` | For one Inference: hash slide → run TRIDENT → locate `.h5` → render heatmap/mixture/example-patches/t-SNE → `ready` if ≥1 render succeeded. |
| `render_slide` | `render_slide.py` | On-demand per-slide render for the Model Comparison page. `ref_table="models"`, `ref_id=model_id`, `params={"slide_id": ...}`. Resolves the slide's h5 + WSI (graceful fail if missing), then renders the **PER-SLIDE** panels into `viz_cache/{model_id}/compare/{slide_id}/` via one memoized encoder pass (`get_assignments`): the Section A panel (`render_section_a_for_slide` → thumbnail/assignment_map/π_c/ROI), Section C `on_tissue` (`render_umap_on_tissue`), and the per-slide violin (`render_slide_violin`). Per-step `try/except` (partial success still publishes). Writes a `manifest.json` capturing the per-slide artifact absolute paths + `slide_id` + `roi_bbox`/`roi_index` + `on_tissue` + `violin` — the manifest is how the API reports readiness. Section D + Section C `scatter` are GLOBAL (rendered once at train time) and are **not** recomputed here. |

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

### `assignment_cache.py` — per-slide encoder memoization
A process-local, thread-safe LRU (module-level `OrderedDict`, `MAX_ENTRIES=32`,
`threading.Lock`) keyed by `(model_id, slide_stem)` → the record
`(coords, cluster_labels, qq, mixture_probs, patch_size)`. No heavy imports (the
numpy arrays pass through as opaque objects), no persistence across restarts.
API: `get`, `put`, `clear_model(model_id)`, `clear()`, and
`get_or_compute(model_id, slide_stem, compute_fn)` (per-key lock so a miss on one
key never blocks other keys, and two concurrent renders of the *same* key compute
once). The key is **model-scoped on purpose**: each model has its own prototypes,
so assignments are never shared across models. `visualization.get_assignments`
wraps this; the per-slide renderers (assignment heatmap, mixture plot, example
patches, per-slide t-SNE, ROI) go through it so several panels for one
(model, slide) — including the upcoming Compare view — reuse one encoder pass.
The dataset-wide streamers (`render_topk_grid`, `render_prototype_dictionary`,
`render_umap`, `render_validation_consistency`) deliberately **do not** use it —
they stream many h5s and would blow the cache. `post_train_viz._render_section_a`
`put`s the assignments it already computes so later Section C / B / ROI renders
for that slide in the same process hit the cache.

### `thumbnails.py` — WSI picker thumbnails (heavy imports lazy)
- `trident_job_dir(features_dir)` — `Path(features_dir).parent.parent` (pure path math;
  the TRIDENT job dir is two levels above the features dir).
- `find_trident_thumbnail(features_dir, slide_stem)` — probes
  `{job_dir}/thumbnails/{slide_stem}.{jpg|jpeg|png}` (in that order), `resolve_within_roots`
  the first hit, else `None`. **F3 CAVEAT:** the TRIDENT subpath/extension is unverified.
- `slide_thumb_cache_key(resolved_path, mtime, size, max_px=512)` — deterministic
  `sha256(...)[:32]` cache key.
- `generate_slide_thumbnail(resolved_path, max_px=512)` — lazy `openslide`; renders a plain
  small RGB JPEG (no scale bar), caches under `{VIZ_CACHE_ROOT}/slide_thumbs/{key}.jpg`
  (temp-write + atomic replace); raises `ThumbnailError` on any openslide failure.
  Powers `GET /api/slide-thumbnail` (see §7).

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
| `render_topk_grid(model, feats_dir, wsi_dir, per_proto=3)` | dataset-wide | `topk_grid.png` (superseded by `render_prototype_dictionary`; left in place but no longer called by `post_train_viz`) |
| `render_prototype_dictionary(model, feats_dir, wsi_dir, per_proto=3)` | dataset-wide | per-patch PNGs under `section_d/proto_{c:02d}/patch_{rank:02d}.png` + a `dict` (Section D) |
| `render_umap(model, feats_dir)` | dataset-wide | `umap.png` (abstract scatter; sets `model.umap_path`) |
| `render_umap_on_tissue(model, h5, wsi, *, downsample_target=SECTION_C_DOWNSAMPLE=24, out_path=None)` | per-slide | `section_c/umap_on_tissue_{stem}.png` (Section C — on-tissue 2D-embedding map) |
| `render_validation_consistency(model, feats_dir)` | fold val + sampled train | `section_b/violin.png` + `section_b/usage.png` + a `dict` (Section B). Heaviest render — runs the encoder over every val slide and ≤`TRAIN_USAGE_SAMPLE_CAP`=50 train slides. Per prototype: violin of val-patch cosine-sim to the trained center (+ counts) and train-vs-val π_c usage bars. Raises `VisualizationError` (graceful skip) when the fold has no val slides. |

**`render_prototype_dictionary` (Section D — prototype dictionary).** Selects the
top `per_proto` patches **per prototype** across the dataset with the *same*
per-prototype heap + soft-assignment scoring as `render_topk_grid`, but writes
each patch as its own PNG (instead of one composite grid) so the UI can render a
column per prototype. Each prototype's color comes from the same
`get_default_cmap(model.n_proto)` the assignment map and π_c bars use, converted
to a `#rrggbb` hex string so columns/labels match the heatmap. Returns:

```json
{ "per_proto": 3,
  "prototypes": [
    { "index": 0, "color": "#rrggbb", "patches": ["<abs viz path>", "..."] },
    "...  one entry for EVERY c in range(n_proto); prototypes with no patches"
    "     get an empty `patches` list so every column still renders"
  ] }
```

Heavy imports (h5py/openslide/PIL) stay lazy. Stored under the `section_d` key of
`model.viz_artifacts` (see §7).

Cost caps: UMAP samples ≤500 patches/slide, ≤50 000 total; top-K streams every h5 once
keeping a per-prototype heap.

**`render_umap_on_tissue` (Section C — on-tissue 2D-embedding map).** The per-slide
companion to the abstract scatter `render_umap` produces. For one slide it fits a
**2D UMAP** of that slide's patch features (lazy `import umap`), robustly normalizes the
two embedding axes to [0,1] (2nd/98th-percentile clip), and colors each patch via a
**bivariate (2D) colormap** — a Stevens-style bilinear choropleth: `u` (UMAP-1) drives a
muted red, `v` (UMAP-2) a muted teal, the (1,1) corner darkens to violet, low/low is light
grey. Those per-patch colors are painted at each patch's `coords`/`patch_size` location over
the downsampled slide by **reusing the assignment-map overlay** (`visualize_categorical_heatmap`
with one unique label per patch + a per-label color dict; same `alpha=0.4` / `vis_level`
conventions, so it's zoomable). A small 2D-colormap legend (color square with `UMAP-1`/`UMAP-2`
axes) is composited into the bottom-right corner so the colors are interpretable. Output lands
under `viz_cache/{model_id}/section_c/`. Heavy imports (umap/h5py/openslide/PIL) stay lazy.
Stored under the `section_c` key of `model.viz_artifacts` (see §7).

**Section A (Analysis page per-slide panel).** Mirrors the PANTHER paper figure; all
artifacts land under `viz_cache/{model_id}/section_a/`.

| Function | Output | Notes |
| --- | --- | --- |
| `render_wsi_thumbnail(model, wsi)` | `section_a/thumbnail_{stem}.png` | Downscaled H&E (longest side ≤ `THUMB_MAX_PX=2048`) with a physical scale bar from openslide `MPP_X`. **If MPP is missing, the thumbnail renders without a scale bar — never fails.** |
| `render_pi_c_barplot(model, mixture_probs)` | `section_a/pi_c.png` | One bar per prototype, **each bar colored by `get_default_cmap(n_proto)`** (same cmap as the assignment map). X labels `C1..Cn`, y label `Proportion π_c`. Takes the GMM `mixture_probs` directly (the third return of `_compute_assignments`). |
| `render_assignment_heatmap_from_assignments(..., downsample_target=SECTION_A_DOWNSAMPLE=24, out_path=section_a/assignment_map_{stem}.png)` | `section_a/assignment_map_{stem}.png` | Hi-res (zoomable) reuse of the existing heatmap renderer with a smaller downsample target. |
| `render_roi_from_assignments(model, coords, labels, ps, wsi, roi_index)` → `(raw, colored, [x,y,w,h], used_idx, n_windows)` | `section_a/roi_raw_{stem}_{idx}.png`, `section_a/roi_colored_{stem}_{idx}.png` | Deterministically picks a `ROI_GRID×ROI_GRID` (7×7) tile of patches by ranking non-overlapping windows (**diversity then density**); `roi_index` selects the i-th (wraps via modulo, so the UI can "repick"). Delegates the actual raw/colored render to `_render_roi_window`. `raw` = openslide `read_region` of the window + scale bar; `colored` = the window tiled as its patches, each blended with its prototype color. |
| `render_roi_at_point(model, coords, labels, ps, wsi, fx, fy, *, out_dir=None)` → `(raw, colored, [x,y,w,h], used_idx, n_windows)` | same as above | **Manual click pick.** `fx,fy` in `[0,1]` over the natural assignment-map image (spanning the coords bbox); maps to a level-0 point `tx=xmin+fx·(xmax-xmin)`, `ty=ymin+fy·(ymax-ymin)` (with `xmax,ymax` = coords max **+ patch_size**). Ranks the same `_select_roi_windows`, picks the window that **contains** `(tx,ty)`; if none contains it (gap tile), picks the window whose **center is nearest**. `used_idx` = that window's rank. Clamps `fx,fy` defensively. Powers `POST /select-roi`. |
| `_render_roi_window(model, coords, labels, ps, wsi, window, idx, n, out_dir)` → `(raw, colored, [x,y,w,h], idx, n)` | same as above | Private shared body factored out of `render_roi_from_assignments`: renders one chosen `(x0,y0,w,h,member_idxs)` window (raw H&E crop + scale bar, colored patch tiling). Used by both `render_roi_from_assignments` (index pick) and `render_roi_at_point` (click pick). |
| `render_roi(model, h5, wsi, roi_index=0)` → `(raw, colored, [x,y,w,h])` | same as above | Convenience wrapper that runs the encoder, then calls `render_roi_from_assignments`. |

**Repick cache.** `save_section_a_cache(model, slide_id, coords, labels, patch_size, *, out_dir=None)`
writes `roi_cache.npz` (coords + cluster_labels) and `roi_cache.json` (slide_id +
patch_size) into `out_dir` (default `section_a/`); `load_section_a_cache(model, *, out_dir=None)`
reads them back. This lets the repick-ROI endpoint re-tile **without re-running the
encoder**. Both are per-slide: the Compare page passes `out_dir=compare/{slide_id}/` so an
arbitrary slide's ROI can be re-tiled.

**Per-slide render generalization (Model Comparison).** The Section A + Section C
`on_tissue` + violin renderers all accept an arbitrary output dir so the same code
serves both the train-time preview slide and the on-demand Compare slide:

| Function | Output |
| --- | --- |
| `compare_slide_dir(model, slide_id)` | Returns `viz_cache/{model_id}/compare/{slide_id}/` (does **not** mkdir — a GET probing for a manifest shouldn't leave empty dirs). |
| `render_section_a_for_slide(model, slide_id, h5_path, wsi_path, *, out_dir=None, log=None)` | Renders the whole Section A panel (thumbnail/assignment_map/π_c/ROI) into `out_dir` (default `section_a_dir`). One encoder pass via `get_assignments`; per-render `try/except`; writes the repick cache into `out_dir`. Used by BOTH `post_train_viz` and `render_slide`. Returns the `section_a` dict. |
| `render_slide_violin(model, feats, cluster_labels, *, out_dir=None)` | Per-slide violin (F4): per prototype c, the cosine similarity of each patch assigned to c to prototype c's trained center, colored by `get_default_cmap(n_proto)`. Output `{out_dir}/violin.png` (default `section_b_violin/`). Returns `{"violin", "counts"}`. Distinct from the val-based Section B. |

`render_wsi_thumbnail`, `render_pi_c_barplot`, and `render_roi_from_assignments` each also
gained an optional `out_dir` param (default `section_a_dir`); the train-time paths are
unchanged.

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

### Datasets — `routes/datasets.py` (Model Comparison page)

There is **no** Dataset/Slide table: `dataset_name` is a denormalized string on
`Model`, and "slides" are just the per-slide `.h5` files under a model's TRIDENT
`features_dir`. Only **non-legacy** models participate — standalone runs carry
`run_kind="single"`, legacy K-fold folds have `run_kind IS NULL`. A dataset whose
only models are legacy folds is invisible here. All three endpoints derive
everything from `Model` rows; no ML imports.

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/datasets` | Distinct `dataset_name`s with ≥1 `run_kind="single"` model. |
| GET | `/api/datasets/{dataset_name}/slides` | Slides (`.h5` stems) under a representative model's `features_dir`, each with a WSI/thumbnail link. |
| GET | `/api/datasets/{dataset_name}/models` | The `run_kind="single"` `ModelInfo`s for the dataset (Add-model dropdown; UI caps at 4). |

**`GET /api/datasets`** → `list[DatasetSummary]`. One row per distinct
`dataset_name` that has at least one single model (legacy-only datasets are
excluded), sorted by name. `model_count` counts single models only; `slide_count`
is deferred to the slides endpoint (left `null` — enumerating h5s isn't free).

```json
[ { "dataset_name": "TCGA_BRCA", "model_count": 3, "slide_count": null } ]
```

**`GET /api/datasets/{dataset_name}/slides`** → `DatasetSlidesResponse`. Picks the
**newest** `run_kind="single"` model for the dataset as the representative (source
of `features_dir` + `wsi_dir` via `visualization.resolve_dataset_wsi_dir`).
**404** if the dataset has no non-legacy model. A missing / out-of-roots /
unreadable `features_dir` degrades gracefully (empty `slides` + a `note`, never a
500). Slide enumeration = `.h5` files **directly** under `features_dir` (not
recursive), `slide_id = stem`, sorted. For each slide `resolve_wsi_path(slide_id,
wsi_dir)` finds the WSI (may be `None`); when resolved (and inside roots) a
`thumbnail_url` is built pointing at `GET /api/slide-thumbnail` with the
url-encoded `path` + `features_dir` params. `resolve_within_roots` gates both the
`features_dir` and every WSI path.

```json
{ "dataset_name": "TCGA_BRCA",
  "features_dir": "<abs features dir>",
  "wsi_dir": "<abs wsi dir | null>",
  "slides": [
    { "slide_id": "slideA",
      "wsi_path": "<abs wsi path | null>",
      "has_wsi": true,
      "thumbnail_url": "/api/slide-thumbnail?path=<enc>&features_dir=<enc>" } ],
  "slide_count": 1,
  "thumbnails_found": 1,
  "note": null }
```

**F3 diagnostic — `thumbnails_found`.** An early-signal count of how many of the
enumerated slides already have a TRIDENT-written thumbnail on disk at
`{job_dir}/thumbnails/{stem}.{jpg|jpeg|png}` (`job_dir = features_dir.parent.parent`),
probed via `thumbnails.find_trident_thumbnail` (same **UNVERIFIED** subpath/extension
guess as `GET /api/slide-thumbnail` step 2 — see §7 F3 CAVEAT). If this comes back
0 on the real GPU data dir while thumbnails clearly exist, TRIDENT is using a
different subdir/extension and `_TRIDENT_THUMB_EXTS` / `find_trident_thumbnail`
need updating.

**`GET /api/datasets/{dataset_name}/models`** → `list[ModelInfo]` — the
`run_kind="single"` models for the dataset, `created_at` desc, built with the same
`_model_to_info` as `routes/panther.py`.

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
| POST | `/api/splits` | Create a split from a source CSV. Body `CreateSplitRequest` carries `kind: "kfold" \| "single"` (default `"kfold"`). `kind="kfold"` → `create_kfold_split` (needs `k>=2`); `kind="single"` → `create_single_split` (a single "100% train" fold, `k=1`, `k` ignored). Same `SplitInfo` shape either way. |
| GET | `/api/splits[?dataset_name=]` | List splits. |
| GET | `/api/splits/{id}` | One split. |

**`create_single_split` (single "100% train" split).** Writes one fold dir
`{split_name}/k=0/` where `train.csv` holds the header + **all** data rows
(same slide-id detection + `.tif`/`.tiff` stripping as K-fold), plus header-only
`val.csv`/`test.csv` so any downstream glob still finds them. `split_name =
alltrain_seed_{seed}_{rand8}`. `metadata.json` mirrors the K-fold fields with
`k=1`, `per_fold_counts=[{train:N,val:0,test:0}]`, and a `kind: "single"` marker.
Returns the same `KFoldSplitInfo` shape (`k==1`). PANTHER only ever reads
`train.csv`, so this trains on every slide.

### PANTHER training — `routes/panther.py`
| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/panther/runs` | **(legacy K-fold)** Create Model Group + K Models, enqueue `panther_train` (`ref_table="model_groups"`), return `{group_id, job_id, k, split_id, split_name, model_ids}`. |
| POST | `/api/panther/single-runs` | **(standalone)** Train ONE model — no `ModelGroup`. Creates one `Model` with `group_id==model_id`, `fold_index=0`, `fold_k=1`, `run_kind="single"`, `model_name={name}_{rand8}`; enqueues `panther_train` (`ref_table="models"`). Body `PantherSingleRunRequest`; returns `{model_id, job_id, split_id, split_name}`. Requires a single ("100% train") split. |
| GET | `/api/panther/runs[?group_id=]` | List per-fold execution logs (`PantherRun`). |
| GET | `/api/panther/models[?group_id=&dataset_name=&run_kind=]` | List Models. `run_kind="single"` filters to standalone runs; `"kfold"`/omitted for legacy folds. |

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
| POST | `/api/models/{id}/select-roi` | **Manual point-based ROI pick.** Body `{slide_id: str\|null, fx: float, fy: float}` — `fx,fy` in `[0,1]` over the natural assignment-map image (clamped server-side). Renders the ROI window **containing** the click (or the nearest-center window if the click hit a gap tile) and persists it. Two modes: `slide_id=null` → the Section A **preview** slide (loads `load_section_a_cache` from `section_a_dir`; updates `viz_artifacts.section_a.roi_*`/`roi_bbox`/`roi_index`; returns the updated `ModelInfo`). `slide_id` given → the **compare** slide (loads the cache from `compare/{slide_id}/`; rewrites that `manifest.json`'s `roi_*`; returns `{status:"ready", artifacts}` like `/slide-viz`). **Synchronous** (uses cached coords/labels — no encoder run). 404 missing model; **409** if the targeted panel/cache/WSI is unavailable (no `section_a` for preview, no compare manifest for a slide); 422 if the slide has no tissue window. |
| POST | `/api/models/{id}/render-slide` | On-demand per-slide render for the Model Comparison page. Body `{slide_id}`. Validates the model (404), the `slide_id` format (422 — `^[A-Za-z0-9._-]+$`, no traversal), and `{features_dir}/{slide_id}.h5` presence (422). **Cache-aware:** if `compare/{slide_id}/manifest.json` exists → `{status:"ready", artifacts}` (no job). Else enqueues a `render_slide` job (`params={"slide_id"}`) → `{status:"rendering", job_id}`; poll `/api/jobs?ref_table=models` for progress, then GET `/slide-viz`. |
| GET | `/api/models/{id}/slide-viz?slide_id=` | Read the per-slide render manifest. `{status:"ready", artifacts}` when `compare/{slide_id}/manifest.json` exists, else `{status:"missing"}`. 404 missing model; 422 bad `slide_id`. |
| GET | `/api/models/{id}/trident-params` | The encoder/mag/patch_size/gpus a model inherits, + expected features dir name. |

`ModelInfo.run_kind` is `"single"` for standalone runs (created via
`/api/panther/single-runs`) and `null` for legacy K-fold folds; the frontend uses it to
separate the two browsers.

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

The Section D (prototype dictionary) shape rides alongside under the `section_d` key:

```json
{ "section_d": {
    "per_proto": 3,
    "prototypes": [
      { "index": 0, "color": "#rrggbb", "patches": ["<abs viz path>", "..."] }
    ]
} }
```

The Section B (validation consistency) shape under the `section_b` key (absent when
the fold has no validation slides):

```json
{ "section_b": {
    "violin": "<abs viz path>",
    "usage": "<abs viz path>",
    "n_val_slides": 12,
    "n_train_slides": 40
} }
```

The Section C (on-tissue 2D-embedding map) shape rides alongside under the `section_c` key:

```json
{ "section_c": {
    "slide_id": "<same deterministic slide as section_a>",
    "scatter": "<model.umap_path — abstract UMAP scatter, may be null if it failed>",
    "on_tissue": "<abs viz path — section_c/umap_on_tissue_{stem}.png>"
} }
```

`slide_id` is the same deterministic slide Section A uses (`pick_preview_slides(count=1)`),
so the abstract scatter and the on-tissue map describe the same example. `scatter` points
at the abstract UMAP this handler renders (`model.umap_path`); if that render failed it is
`null` but `section_c` is still emitted with `on_tissue`. All three sections (`section_a`,
`section_c`, `section_d`) are written with a load-merge-dump so rendering one never clobbers
the others.

The per-slide violin (F4) rides alongside under the distinct `section_b_violin` key
(separate from the val-based `section_b`):

```json
{ "section_b_violin": {
    "violin": "<abs viz path — section_b_violin/violin.png>",
    "counts": [n_c for c in range(n_proto)],
    "slide_id": "<same deterministic slide as section_a>"
} }
```

**Per-slide render manifest (Model Comparison).** The `render_slide` handler writes
`viz_cache/{model_id}/compare/{slide_id}/manifest.json`. Its shape mirrors `section_a`
plus `on_tissue` + `violin` (all absolute `viz_cache` paths). `POST /render-slide` (cache
hit) and `GET /slide-viz` return it verbatim as `artifacts`:

```json
{ "slide_id": "<stem>",
  "thumbnail": "<abs viz path>",
  "assignment_map": "<abs viz path>",
  "pi_c": "<abs viz path>",
  "roi_raw": "<abs viz path>",
  "roi_colored": "<abs viz path>",
  "roi_bbox": [x, y, w, h],
  "roi_index": 0,
  "on_tissue": "<abs viz path>",
  "violin": "<abs viz path>",
  "violin_counts": [n_c, ...] }
```

Any individual render that fails is simply absent from the manifest (partial success still
publishes). Section D (prototype dictionary) and Section C `scatter` (`model.umap_path`) are
**global** — rendered once per model at train time — and are **not** recomputed per slide.

`prototypes` has one entry for **every** `c in range(n_proto)` (prototypes with no
representative patches carry an empty `patches` list, so the UI always shows a
column). `color` is the prototype's `get_default_cmap(n_proto)` color as `#rrggbb`,
matching the assignment map and π_c bars. PNGs live under
`viz_cache/{model_id}/section_d/proto_{c:02d}/patch_{rank:02d}.png`.

All paths are absolute `viz_cache` paths served by `GET /api/viz/{path}`. Any individual
render that fails is simply absent from the dict (partial success still publishes). The
two sections are written with a load-merge-dump so rendering one never clobbers the other.

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

### Slide thumbnails — `routes/thumbnails.py`
| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/slide-thumbnail?path=&features_dir=&max_px=` | Small WSI thumbnail for the slide pickers. Returns a **binary image** (FileResponse), not JSON. |

`GET /api/slide-thumbnail` (mounted at `/api`, not under `/api/viz`, so it doesn't
collide with the `/api/viz/{file_path:path}` catch-all):

1. `resolve_within_roots(path)` (security boundary → **403** outside roots), then
   requires the resolved path to be an existing file (**404** if not).
2. **TRIDENT thumbnail first** (only if `features_dir` is supplied). TRIDENT writes
   per-slide thumbnails under `{job_dir}/thumbnails/{slide_stem}.{jpg|jpeg|png}`, where
   the features layout is `{job_dir}/{mag}x_{ps}px_0px_overlap/features_{encoder}` (see
   `runner.output_dir_for`) — so `job_dir = Path(features_dir).parent.parent`
   (`thumbnails.trident_job_dir`). We probe those three extensions in order; the first hit
   is run through `resolve_within_roots` and served directly with header
   `X-Thumbnail-Source: trident`. If none match, fall through to generation.
   **F3 CAVEAT — UNVERIFIED:** the exact TRIDENT thumbnail subpath/extension is a guess
   (the TRIDENT README was not vendored). Confirm on the real GPU data dir; if TRIDENT
   uses a different subdir/extension, update `_TRIDENT_THUMB_EXTS` /
   `find_trident_thumbnail` in `services/thumbnails.py`.
3. **Fallback — generate.** Open the WSI with openslide (**lazy** import), render a plain
   small RGB JPEG (longest side ≤ `max_px`, default 512, no scale bar / coords overlay),
   and cache it under `{VIZ_CACHE_ROOT}/slide_thumbs/{key}.jpg` where
   `key = sha256(resolved_path | mtime | size | max_px)[:32]`
   (`thumbnails.slide_thumb_cache_key`, deterministic → cheap on repeat). Served with
   `X-Thumbnail-Source: generated`. Any openslide failure → **422** (`ThumbnailError`);
   the picker falls back to a placeholder icon client-side.

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
