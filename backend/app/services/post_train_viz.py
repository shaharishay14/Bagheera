"""Real `post_train_viz` job handler.

Runs after a fold model finishes training. For one Model row:
  1. Pick (or reuse) the 3 preview slide IDs from the fold's train.csv.
  2. For each preview slide, render an assignment heatmap → store paths in
     Model.preview_heatmap_paths (JSON list).
  3. Render the dataset-wide prototype dictionary (Section D) → merged into
     Model.viz_artifacts under the `section_d` key (supersedes the old
     top-K grid; `render_topk_grid` is left in place but no longer called).
  4. Render the dataset-wide UMAP → Model.umap_path.
  5. Render the Section A per-slide panel → merged into Model.viz_artifacts
     under the `section_a` key.
  6. Render the Section C on-tissue 2D-embedding map for the SAME deterministic
     Section-A slide → merged into Model.viz_artifacts under the `section_c` key
     ({"slide_id", "scatter": model.umap_path, "on_tissue": <new path>}).
  7. Render Section B validation consistency (encoder over the fold's val + sampled
     train slides) → merged under the `section_b` key. Skipped if no val slides.
  8. Flip Model.viz_status to 'ready' (or 'failed' if every render blew up).

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

    # --- Prototype dictionary / Section D (dataset-wide) --------------------
    # Supersedes the old composite top-K grid: one PNG per representative patch,
    # plus each prototype's assignment-map color, so the UI can render per-column.
    section_d: dict | None = None
    if wsi_dir is not None:
        try:
            from pathlib import Path

            section_d = visualization.render_prototype_dictionary(
                model,
                Path(model.features_dir),
                wsi_dir,
                per_proto=model.topk_per_proto or 3,
            )
            successes += 1
            n_with_patches = sum(1 for p in section_d["prototypes"] if p["patches"])
            log.write(
                f"  section_d: {len(section_d['prototypes'])} prototypes, "
                f"{n_with_patches} with patches, per_proto={section_d['per_proto']}"
            )
        except Exception as exc:  # noqa: BLE001
            failures.append(f"section_d: {exc}")
            log.write(f"  FAILED section_d: {exc}\n{traceback.format_exc()}")

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

    # --- Section A (Analysis page per-slide panel) --------------------------
    section_a: dict | None = None
    try:
        section_a = _render_section_a(model, db, wsi_dir, log)
        if section_a:
            successes += 1
    except Exception as exc:  # noqa: BLE001 — never let Section A abort the rest
        failures.append(f"section_a: {exc}")
        log.write(f"  FAILED section_a: {exc}\n{traceback.format_exc()}")

    # --- Section C (on-tissue 2D-embedding map) -----------------------------
    # Companion to the abstract UMAP scatter: paints each patch by its 2D UMAP
    # coordinate (bivariate colormap) at its slide location, for the SAME
    # deterministic Section-A slide. `scatter` reuses the umap_path rendered
    # above (may be None if that step failed — we still emit on_tissue).
    section_c: dict | None = None
    try:
        section_c = _render_section_c(model, db, wsi_dir, umap_path, log)
        if section_c:
            successes += 1
    except Exception as exc:  # noqa: BLE001 — never let Section C abort the rest
        failures.append(f"section_c: {exc}")
        log.write(f"  FAILED section_c: {exc}\n{traceback.format_exc()}")

    # --- Section B (validation-slide prototype consistency) -----------------
    # Heaviest render — runs the encoder over the fold's val slides (+ sampled
    # train slides). Skipped gracefully when the fold has no validation slides.
    section_b: dict | None = None
    try:
        section_b = _render_section_b(model, log)
        if section_b:
            successes += 1
    except Exception as exc:  # noqa: BLE001 — never let Section B abort the rest
        failures.append(f"section_b: {exc}")
        log.write(f"  FAILED section_b: {exc}\n{traceback.format_exc()}")

    # --- Commit results -----------------------------------------------------
    model.preview_heatmap_paths = json.dumps(heatmap_paths) if heatmap_paths else None
    model.umap_path = umap_path

    # Merge into the existing viz_artifacts JSON so section_a and section_d ride
    # along together — never clobber a previously-rendered section.
    artifacts: dict = {}
    if model.viz_artifacts:
        try:
            loaded = json.loads(model.viz_artifacts)
            if isinstance(loaded, dict):
                artifacts = loaded
        except json.JSONDecodeError:
            artifacts = {}
    if section_a:
        artifacts["section_a"] = section_a
    if section_d:
        artifacts["section_d"] = section_d
    if section_c:
        artifacts["section_c"] = section_c
    if section_b:
        artifacts["section_b"] = section_b
    model.viz_artifacts = json.dumps(artifacts) if artifacts else None

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


def _render_section_a(model: Model, db: Session, wsi_dir, log: JobLog) -> dict | None:
    """Render the Section A per-slide panel for ONE deterministic slide.

    Renders the whole-slide thumbnail, a hi-res (zoomable) assignment map, the
    π_c bar chart, and the index-0 ROI (raw + prototype-colored). Each render
    is wrapped in its own try/except so partial success still publishes. The
    slide's coords/labels are cached to a .npz so the repick-ROI endpoint can
    re-tile without re-running the encoder.

    Returns the `section_a` dict to store under model.viz_artifacts, or None if
    no usable slide could be resolved (missing WSI / h5).
    """
    from pathlib import Path

    if wsi_dir is None:
        log.write("  section_a: no WSI dir resolved — skipping.")
        return None

    ids = pick_preview_slides(model, count=1)
    if not ids:
        log.write("  section_a: no slide could be picked (train.csv missing/empty).")
        return None
    slide_id = ids[0]

    h5_path = Path(model.features_dir) / f"{slide_id}.h5"
    wsi_path = visualization.resolve_wsi_path(slide_id, wsi_dir)
    if not h5_path.is_file():
        log.write(f"  section_a: h5 not found for {slide_id} at {h5_path} — skipping.")
        return None
    if wsi_path is None:
        log.write(f"  section_a: no WSI file with stem {slide_id} under {wsi_dir} — skipping.")
        return None

    log.write(f"  section_a: rendering for slide {slide_id}")

    # Run the encoder ONCE; reuse the assignments for every Section A render.
    encoder = visualization._load_panther_encoder(model)
    coords, feats, patch_size = visualization._load_h5(h5_path)
    cluster_labels, _qq, mixture_probs = visualization._compute_assignments(encoder, feats)

    section: dict = {"slide_id": slide_id, "roi_index": 0}

    try:
        out = visualization.render_wsi_thumbnail(model, wsi_path)
        section["thumbnail"] = str(out)
        log.write(f"    thumbnail: {out}")
    except Exception as exc:  # noqa: BLE001
        log.write(f"    FAILED thumbnail: {exc}\n{traceback.format_exc()}")

    try:
        out = visualization.render_assignment_heatmap_from_assignments(
            model,
            coords,
            cluster_labels,
            patch_size,
            wsi_path,
            downsample_target=visualization.SECTION_A_DOWNSAMPLE,
            out_path=visualization.section_a_dir(model) / f"assignment_map_{slide_id}.png",
        )
        section["assignment_map"] = str(out)
        log.write(f"    assignment_map: {out}")
    except Exception as exc:  # noqa: BLE001
        log.write(f"    FAILED assignment_map: {exc}\n{traceback.format_exc()}")

    try:
        out = visualization.render_pi_c_barplot(model, mixture_probs)
        section["pi_c"] = str(out)
        log.write(f"    pi_c: {out}")
    except Exception as exc:  # noqa: BLE001
        log.write(f"    FAILED pi_c: {exc}\n{traceback.format_exc()}")

    try:
        raw, colored, bbox, used_idx, n_windows = visualization.render_roi_from_assignments(
            model, coords, cluster_labels, patch_size, wsi_path, roi_index=0
        )
        section["roi_raw"] = str(raw)
        section["roi_colored"] = str(colored)
        section["roi_bbox"] = bbox
        section["roi_index"] = used_idx
        log.write(f"    roi: index {used_idx}/{n_windows} bbox={bbox}")
    except Exception as exc:  # noqa: BLE001
        log.write(f"    FAILED roi: {exc}\n{traceback.format_exc()}")

    # Cache coords/labels so repick-ROI re-tiles without the encoder.
    try:
        visualization.save_section_a_cache(model, slide_id, coords, cluster_labels, patch_size)
    except Exception as exc:  # noqa: BLE001
        log.write(f"    WARNING: failed to write Section A repick cache: {exc}")

    return section


def _render_section_c(model: Model, db: Session, wsi_dir, umap_path, log: JobLog) -> dict | None:
    """Render the Section C on-tissue 2D-embedding map for ONE deterministic slide.

    Uses the SAME slide as Section A (`pick_preview_slides(count=1)`) so the
    on-tissue map and the abstract scatter describe the same example. Returns the
    `section_c` dict to merge under model.viz_artifacts, or None if no usable
    slide could be resolved (missing WSI / h5 / WSI dir).

    `scatter` points at the abstract UMAP this handler renders (`model.umap_path`,
    passed in as `umap_path`); it may legitimately be None if that render failed,
    in which case we still emit `section_c` with the on-tissue map alone.
    """
    from pathlib import Path

    if wsi_dir is None:
        log.write("  section_c: no WSI dir resolved — skipping.")
        return None

    ids = pick_preview_slides(model, count=1)
    if not ids:
        log.write("  section_c: no slide could be picked (train.csv missing/empty).")
        return None
    slide_id = ids[0]

    h5_path = Path(model.features_dir) / f"{slide_id}.h5"
    wsi_path = visualization.resolve_wsi_path(slide_id, wsi_dir)
    if not h5_path.is_file():
        log.write(f"  section_c: h5 not found for {slide_id} at {h5_path} — skipping.")
        return None
    if wsi_path is None:
        log.write(f"  section_c: no WSI file with stem {slide_id} under {wsi_dir} — skipping.")
        return None

    log.write(f"  section_c: rendering on-tissue UMAP for slide {slide_id}")
    out = visualization.render_umap_on_tissue(model, h5_path, wsi_path)
    log.write(f"    on_tissue: {out}")

    return {"slide_id": slide_id, "scatter": umap_path, "on_tissue": str(out)}


def _render_section_b(model: Model, log: JobLog) -> dict | None:
    """Render Section B (validation-slide prototype consistency).

    Returns the `section_b` dict to merge under model.viz_artifacts, or None when
    the fold has no usable validation slides (a graceful skip — not a failure).
    Any other error propagates to the handler's try/except and is logged.
    """
    from pathlib import Path

    try:
        section_b = visualization.render_validation_consistency(
            model, Path(model.features_dir)
        )
    except visualization.VisualizationError as exc:
        log.write(f"  section_b: skipped ({exc})")
        return None

    log.write(
        f"  section_b: violin+usage over {section_b['n_val_slides']} val / "
        f"{section_b['n_train_slides']} train slides"
    )
    return section_b


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
