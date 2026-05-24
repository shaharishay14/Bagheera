"""Real `post_train_viz` job handler.

Runs after a fold model finishes training. For one Model row:
  1. Pick (or reuse) the 3 preview slide IDs from the fold's train.csv.
  2. For each preview slide, render an assignment heatmap → store paths in
     Model.preview_heatmap_paths (JSON list).
  3. Render the dataset-wide top-K representative-patches grid →
     Model.topk_grid_path.
  4. Render the dataset-wide UMAP → Model.umap_path.
  5. Flip Model.viz_status to 'ready' (or 'failed' if every render blew up).

Per-step failures are caught and logged into the job log; the handler keeps
going so a partial render still publishes whatever succeeded. If at least
one heatmap renders, viz_status='ready' — the UI's resolveVizUrl helper
falls back to placeholder SVGs for any null columns, so partial output is
strictly better than nothing.

Mixture / example-patches / t-SNE renderers exist in visualization.py for
PR 5's inference flow but aren't called here — Model schema has no columns
for them, those are stored per-Inference.
"""
from __future__ import annotations

import json
import traceback
from datetime import datetime

from sqlalchemy.orm import Session

from app.db.models import Job, Model
from app.services import visualization
from app.services.preview import pick_preview_slides
from app.services.worker import JobLog, register_handler


def handle_post_train_viz(*, db: Session, job: Job, log: JobLog) -> None:
    model = db.get(Model, job.ref_id)
    if model is None:
        raise RuntimeError(f"Model {job.ref_id!r} not found.")

    log.write(
        f"Rendering viz for fold model {model.model_name} "
        f"(group={model.group_id}, fold={model.fold_index}, n_proto={model.n_proto})"
    )
    model.viz_status = "rendering"
    db.add(model)
    db.commit()

    successes = 0
    failures: list[str] = []

    # --- Preview heatmaps (per-slide) ---------------------------------------
    preview_ids = _resolve_preview_slide_ids(model)
    if preview_ids:
        log.write(f"Preview slides: {preview_ids}")
        model.preview_slide_ids = json.dumps(preview_ids)
        db.add(model)
        db.commit()
    else:
        log.write("No preview slides resolved (train.csv missing or empty).")

    wsi_dir = visualization.resolve_dataset_wsi_dir(model, db)
    if wsi_dir is None:
        log.write(
            "WARNING: no WSI directory could be resolved for this model "
            "(model.trident_run_id is null or TridentRun.wsi_dir not found). "
            "Per-slide heatmaps and the top-K grid will be skipped."
        )

    heatmap_paths: list[str] = []
    if wsi_dir is not None:
        from pathlib import Path  # local import keeps the top imports tidy

        features_dir = Path(model.features_dir)
        for slide_id in preview_ids:
            h5_path = features_dir / f"{slide_id}.h5"
            wsi_path = visualization.resolve_wsi_path(slide_id, wsi_dir)
            if not h5_path.is_file():
                log.write(f"  skip {slide_id}: h5 not found at {h5_path}")
                continue
            if wsi_path is None:
                log.write(f"  skip {slide_id}: no WSI file with that stem under {wsi_dir}")
                continue
            try:
                out = visualization.render_assignment_heatmap(model, h5_path, wsi_path)
                heatmap_paths.append(str(out))
                successes += 1
                log.write(f"  heatmap: {out}")
            except Exception as exc:  # noqa: BLE001 — one failure shouldn't abort the rest
                failures.append(f"heatmap[{slide_id}]: {exc}")
                log.write(f"  FAILED heatmap for {slide_id}: {exc}\n{traceback.format_exc()}")

    # --- Top-K grid (dataset-wide) ------------------------------------------
    topk_grid_path: str | None = None
    if wsi_dir is not None:
        try:
            from pathlib import Path

            out = visualization.render_topk_grid(
                model,
                Path(model.features_dir),
                wsi_dir,
                per_proto=model.topk_per_proto or 3,
            )
            topk_grid_path = str(out)
            successes += 1
            log.write(f"  topk_grid: {out}")
        except Exception as exc:  # noqa: BLE001
            failures.append(f"topk_grid: {exc}")
            log.write(f"  FAILED topk_grid: {exc}\n{traceback.format_exc()}")

    # --- UMAP (dataset-wide, no WSI needed) ---------------------------------
    umap_path: str | None = None
    try:
        from pathlib import Path

        out = visualization.render_umap(model, Path(model.features_dir))
        umap_path = str(out)
        successes += 1
        log.write(f"  umap: {out}")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"umap: {exc}")
        log.write(f"  FAILED umap: {exc}\n{traceback.format_exc()}")

    # --- Commit results -----------------------------------------------------
    model.preview_heatmap_paths = json.dumps(heatmap_paths) if heatmap_paths else None
    model.topk_grid_path = topk_grid_path
    model.umap_path = umap_path
    model.viz_status = "ready" if successes > 0 else "failed"
    db.add(model)
    db.commit()

    log.write(
        f"Done: viz_status={model.viz_status} successes={successes} failures={len(failures)}"
    )
    if failures:
        log.write("Failures detail:")
        for f in failures:
            log.write(f"  - {f}")


def _resolve_preview_slide_ids(model: Model) -> list[str]:
    """Use the IDs already on the row if the user picked them via shuffle;
    otherwise pick deterministically now."""
    if model.preview_slide_ids:
        try:
            ids = json.loads(model.preview_slide_ids)
            if isinstance(ids, list) and ids:
                return [str(s) for s in ids]
        except json.JSONDecodeError:
            pass
    return pick_preview_slides(model)


def register() -> None:
    register_handler("post_train_viz", handle_post_train_viz)


# Avoid "imported but unused" on `datetime` — kept available for handlers that
# want to stamp render times into the log without re-importing.
__all__ = ["handle_post_train_viz", "register", "datetime"]
