"""Real `render_slide` job handler — on-demand per-slide visualization.

Powers the Model Comparison page: renders a single arbitrary slide's per-slide
panels for one model, into a slide-scoped cache dir, and writes a manifest the
API reads to report readiness/paths.

Job shape:  job_type="render_slide", ref_table="models", ref_id=<model_id>,
            params={"slide_id": <stem>}.

What it renders (PER-SLIDE only — recomputed for the chosen slide):
  - Section A panel: thumbnail, hi-res assignment map, π_c bars, index-0 ROI.
  - Section C `on_tissue`: the on-tissue 2D-embedding (UMAP) map.
  - The per-slide violin (F4): cosine-sim of each patch to its assigned
    prototype center.

GLOBAL artifacts are deliberately NOT recomputed here: Section D (the prototype
dictionary) and Section C `scatter` (`model.umap_path`) are rendered once per
model at train time and shared across all slides.

One encoder pass serves every panel: `get_assignments(model, slide_id, h5)`
memoizes per (model, slide), so Section A + the violin reuse it.

Every step is wrapped in its own try/except so a partial render still publishes
whatever succeeded; the manifest is always written (with whatever keys landed),
and the worker marks the job succeeded. A missing WSI/h5 fails the job
gracefully (logged; no crash — the worker loop survives).
"""
from __future__ import annotations

import json
import traceback
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Job, Model
from app.services import visualization
from app.services.worker import JobLog, register_handler


def handle_render_slide(*, db: Session, job: Job, log: JobLog) -> None:
    model = db.get(Model, job.ref_id)
    if model is None:
        raise RuntimeError(f"Model {job.ref_id!r} not found.")

    params = json.loads(job.params or "{}")
    slide_id = params.get("slide_id")
    if not slide_id:
        raise RuntimeError("render_slide job is missing the required 'slide_id' param.")

    log.write(
        f"Rendering per-slide viz for model {model.model_name} slide={slide_id} "
        f"(n_proto={model.n_proto})"
    )

    h5_path = Path(model.features_dir) / f"{slide_id}.h5"
    if not h5_path.is_file():
        raise RuntimeError(f"features h5 not found for slide {slide_id!r} at {h5_path}")

    wsi_dir = visualization.resolve_dataset_wsi_dir(model, db)
    wsi_path = visualization.resolve_wsi_path(slide_id, wsi_dir) if wsi_dir else None
    if wsi_path is None:
        raise RuntimeError(
            f"no WSI file with stem {slide_id!r} found under the dataset WSI dir ({wsi_dir})."
        )

    out_dir = visualization.compare_slide_dir(model, slide_id)
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: dict = {"slide_id": slide_id}

    # --- Section A panel (thumbnail / assignment_map / pi_c / roi) -----------
    try:
        section_a = visualization.render_section_a_for_slide(
            model, slide_id, h5_path, wsi_path, out_dir=out_dir, log=log
        )
        # Merge the section_a fields (slide_id, thumbnail, assignment_map, pi_c,
        # roi_raw, roi_colored, roi_bbox, roi_index) up into the manifest.
        manifest.update(section_a)
    except Exception as exc:  # noqa: BLE001 — one panel must not abort the rest
        log.write(f"  FAILED section_a: {exc}\n{traceback.format_exc()}")

    # --- Section C on-tissue 2D-embedding map -------------------------------
    try:
        out = visualization.render_umap_on_tissue(
            model,
            h5_path,
            wsi_path,
            out_path=out_dir / f"umap_on_tissue_{slide_id}.png",
        )
        manifest["on_tissue"] = str(out)
        log.write(f"  on_tissue: {out}")
    except Exception as exc:  # noqa: BLE001
        log.write(f"  FAILED on_tissue: {exc}\n{traceback.format_exc()}")

    # --- Per-slide violin (F4) ----------------------------------------------
    try:
        _coords, feats, _ps = visualization._load_h5(h5_path)
        _c, cluster_labels, _qq, _mix, _psz = visualization.get_assignments(
            model, slide_id, h5_path
        )
        vres = visualization.render_slide_violin(
            model, feats, cluster_labels, out_dir=out_dir
        )
        manifest["violin"] = vres["violin"]
        manifest["violin_counts"] = vres.get("counts")
        log.write(f"  violin: {vres['violin']}")
    except Exception as exc:  # noqa: BLE001
        log.write(f"  FAILED violin: {exc}\n{traceback.format_exc()}")

    # --- Publish the manifest (readiness signal for the API) ----------------
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))
    log.write(f"Wrote manifest: {manifest_path}")


def register() -> None:
    register_handler("render_slide", handle_render_slide)


__all__ = ["handle_render_slide", "register"]
