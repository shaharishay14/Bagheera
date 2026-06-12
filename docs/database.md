# Bagheera — Database Reference

> SQLite + SQLAlchemy 2.0. Read [backend.md](./backend.md) for context.
> Read [structure.md](./structure.md) for the domain model that motivates the schema.

---

## 1. Stack & conventions

| Concern | Choice |
| --- | --- |
| Engine | SQLite (`sqlite:///{BAGHEERA_DB_PATH}`) |
| ORM | SQLAlchemy 2.0 typed `Mapped[…]` models in `app/db/models.py` |
| Session | `SessionLocal` factory in `app/db/database.py`; `get_db()` FastAPI dep |
| Schema lifecycle | **No migrations** — `Base.metadata.create_all()` on startup. After any column change, delete `bagheera.db` and restart. |
| Thread safety | `check_same_thread=False`; SQLite shared across HTTP threads + the worker thread |
| WAL + timeout | `PRAGMA journal_mode=WAL` + `busy_timeout=5000` ms (queue design). Prevents "database is locked" under concurrent readers and the occasional writer. |

**Hard rule:** never add a migration framework. When a new nullable column or index is needed without a DB wipe (e.g., adding `queue_position`), add an `ALTER TABLE … ADD COLUMN IF NOT EXISTS` guard in `init_db()` and document it here.

---

## 2. Entity–relationship overview

```
trident_runs ──┐
               ├──< model_groups ──< models ──< panther_runs
splits ────────┘                       │  │  │
                                       │  │  └──< prototype_labels
                                       │  └─────< model_notes
                                       └─────────< inferences ──< inference_notes
                                                       │
                                          inference_batches ──┘
jobs  (ref_table, ref_id) → polymorphic → any of: model_groups | models | inferences
```

---

## 3. Table reference

### `TridentRun`
`id` (uuid PK), `created_at`, `dataset_name`, `wsi_dir`, `patch_encoder`, `mag`,
`patch_size`, `command`, `status` (`pending|running|succeeded|failed`), `stdout`,
`stderr`, `output_dir` (canonical features dir), `return_code`.

### `Split`
`id`, `created_at`, `dataset_name` (indexed), `split_name` (**unique**), `abs_path`,
`source_csv`, `k`, `seed`, `total_rows`, `per_fold_counts` (JSON
`list[{train,val,test}]`).

### `ModelGroup`
`id` (== `group_id`), `created_at`, `display_name`, `dataset_name` (indexed),
`trident_run_id` (FK → `TridentRun`, **nullable**), `k`, `split_id` (FK → `Split`).

### `Model`
Central row. `id`, `created_at`; naming (`base_name`, `model_name` (**unique**),
`display_name`); grouping (`group_id` (indexed), `fold_index`, `fold_k`); inputs
(`dataset_name`, `features_dir`, `trident_run_id`, `split_id`, `split_name`,
`split_dir_abs`); PANTHER hyperparams (`mode`, `in_dim`, `n_proto_patches`, `n_proto`,
`n_init`, `seed`, `num_workers`); outcome (`status` `pending|running|ready|failed`,
`prototypes_dir`, `prototype_files` JSON); `is_favorite`; viz artifacts (`viz_status`
`pending|rendering|ready|failed`, `preview_slide_ids` JSON, `preview_heatmap_paths` JSON,
`topk_grid_path`, `topk_per_proto`, `umap_path`).
**Unique constraint:** `(group_id, fold_index)`.

### `PantherRun`
Per-fold subprocess execution log: `id`, `created_at`, `group_id` (indexed),
`fold_index`, `model_id` (FK → `Model`), denormalised inputs + hyperparams, `command`,
`status`, `stdout`, `stderr`, `return_code`, `started_at`, `finished_at`.

### `PrototypeLabel`
`id`, `created_at`, `updated_at`, `model_id` (FK → `Model`), `prototype_index`, `label`.
**Unique:** `(model_id, prototype_index)`.

### `ModelNote`
`id`, `created_at`, `updated_at`, `model_id` (FK, indexed), `body`.

### `InferenceBatch`
`id`, `created_at`, `model_id` (FK, indexed), `user_label`, `total_count`.

### `Inference`
`id`, `created_at`, `finished_at`, `model_id` (FK, indexed), `batch_id` (FK, nullable);
slide identity (`wsi_path`, `wsi_filename`, `wsi_mtime`, `wsi_size`, `wsi_hash`);
outputs (`output_dir`, `features_h5_path`, `heatmap_path`, `mixture_plot_path`,
`example_patches_dir`, `tsne_path`); `status`
(`queued|running_trident|running_viz|ready|failed`), `error_message`.
**Unique:** `(model_id, wsi_hash)` — the cache key.

### `InferenceNote`
`id`, `created_at`, `updated_at`, `inference_id` (FK, indexed), `body`.

### `Job`
`id`, `created_at` (indexed), `started_at`, `finished_at`, `job_type` (indexed),
`ref_table`, `ref_id` (polymorphic pointer), `status`
(`queued|running|succeeded|failed|canceled`, indexed), `error_message`, `log_path`,
`queue_position` (int|null, added via `ALTER TABLE` guard — lower = runs sooner;
NULL once a job leaves the queue).

---

## 4. The `jobs` polymorphic pointer

`ref_table` ∈ `{model_groups, models, inferences}`. Combined with `ref_id` it points
back to the row a job operates on. There is **no FK constraint** — the pointer is
resolved in application code (`services/worker.py`, `routes/jobs.py`).

Valid `(ref_table, job_type)` pairings:
| `ref_table` | `job_type` |
| --- | --- |
| `model_groups` | `panther_train` |
| `models` | `post_train_viz` |
| `inferences` | `inference` |

---

## 5. Queue ordering (`queue_position`)

`queue_position` was added post-initial-schema via an `ALTER TABLE` guard in
`init_db()` (backfills existing DBs without a wipe). Rules:
- Set on `enqueue_job()` to `max(current_max) + 1` (FIFO).
- Cleared (`NULL`) when the worker claims the job.
- On cancel: the row stays but position is irrelevant (status = `canceled`).
- On reorder: the server atomically rewrites `queue_position` for the ordered subset.

---

## 6. Maintenance notes

- **DB wipe**: `rm bagheera.db` then `uvicorn app.main:app` recreates it.
- **Seed data**: `python scripts/seed_demo.py` — idempotent; all rows carry `[SEED]`
  prefix and use placeholder viz paths.
- **Adding a column**: add `Mapped[Optional[X]]` to the model class, add an `ALTER
  TABLE … ADD COLUMN … DEFAULT …` guard in `init_db()`, document it in this file.
- **Adding an index**: use `Index(…)` in `models.py` and wipe+recreate (no guard needed
  if index is purely additive — a missing index degrades perf, not correctness).

> Keep this file in sync whenever you change `app/db/models.py`.
