"""Real `inference` job handler.

Replaces the stub from PR 1. Per the plan §13:

  1. status='running_trident', hash WSI if not already
  2. Build + run TRIDENT subprocess (cwd=$TRIDENT_REPO_PATH), capture
     stdout/stderr into the job log
  3. On non-zero exit: status='failed', error_message=stderr tail, return
  4. Locate features h5 → set inferences.features_h5_path
  5. status='running_viz'
  6. Render heatmap / mixture / example patches / t-SNE (per-step
     try/except — partial output is better than none)
  7. status='ready' if at least one render succeeded, else 'failed'
"""
from __future__ import annotations

import os
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Inference, Job, Model
from app.services import inference as inference_service
from app.services import visualization
from app.services.worker import JobLog, register_handler


def handle_inference(*, db: Session, job: Job, log: JobLog) -> None:
    inference = db.get(Inference, job.ref_id)
    if inference is None:
        raise RuntimeError(f"Inference {job.ref_id!r} not found.")

    model = db.get(Model, inference.model_id)
    if model is None:
        raise RuntimeError(
            f"Inference {inference.id!r} references missing model {inference.model_id!r}."
        )

    wsi_path = Path(inference.wsi_path)
    log.write(
        f"Inference for slide {wsi_path.name} using fold model {model.model_name} "
        f"(group={model.group_id}, fold={model.fold_index})"
    )

    # --- Phase 1: TRIDENT --------------------------------------------------
    inference.status = "running_trident"
    db.add(inference)
    db.commit()

    if not inference.wsi_hash:
        try:
            inference.wsi_hash = inference_service.compute_wsi_hash(wsi_path)
            db.add(inference)
            db.commit()
            log.write(f"  wsi_hash: {inference.wsi_hash[:16]}…")
        except inference_service.InferenceServiceError as exc:
            _mark_failed(db, log, inference, f"hash: {exc}")
            return

    if not settings.trident_repo_path:
        _mark_failed(
            db,
            log,
            inference,
            "TRIDENT_REPO_PATH is not set on the server. Cannot run inference subprocess.",
        )
        return

    output_dir = Path(inference.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "custom_list.csv"
    try:
        inference_service.generate_custom_wsi_csv(wsi_path, csv_path)
    except OSError as exc:
        _mark_failed(db, log, inference, f"write custom_list.csv failed: {exc}")
        return

    try:
        cmd = inference_service.build_trident_command(
            model=model,
            db=db,
            wsi_path=wsi_path,
            output_dir=output_dir,
            custom_csv_path=csv_path,
        )
    except inference_service.InferenceServiceError as exc:
        _mark_failed(db, log, inference, str(exc))
        return

    log.write(f"$ (cd {settings.trident_repo_path} && {inference_service.render_command(cmd)})")

    try:
        result = subprocess.run(
            cmd,
            cwd=settings.trident_repo_path,
            env={**os.environ, "CUDA_VISIBLE_DEVICES": _cuda_visible_devices(model, db)},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
    except OSError as exc:
        _mark_failed(db, log, inference, f"subprocess.run failed: {exc}")
        return

    if result.stdout:
        log.write("--- TRIDENT stdout ---")
        log.write(result.stdout.rstrip())
    if result.stderr:
        log.write("--- TRIDENT stderr ---")
        log.write(result.stderr.rstrip())
    log.write(f"--- TRIDENT exited rc={result.returncode} ---")

    if result.returncode != 0:
        _mark_failed(
            db,
            log,
            inference,
            f"TRIDENT exited with code {result.returncode}: {_tail(result.stderr, 800)}",
        )
        return

    # --- Phase 2: locate features ------------------------------------------
    params = inference_service.inherited_trident_params(model, db)
    if not params.patch_encoder or params.mag is None or params.patch_size is None:
        _mark_failed(
            db,
            log,
            inference,
            "model has no inherited TRIDENT params (trident_run_id missing or stale).",
        )
        return

    try:
        features_h5 = inference_service.locate_features_file(
            output_dir,
            wsi_path.stem,
            mag=params.mag,
            patch_size=params.patch_size,
            patch_encoder=params.patch_encoder,
        )
    except FileNotFoundError as exc:
        _mark_failed(db, log, inference, str(exc))
        return

    inference.features_h5_path = str(features_h5)
    db.add(inference)
    db.commit()
    log.write(f"  features: {features_h5}")

    # --- Phase 3: visualization --------------------------------------------
    inference.status = "running_viz"
    db.add(inference)
    db.commit()

    successes = 0
    failures: list[str] = []

    # Heatmap (the primary, most informative one — runs first).
    inference.heatmap_path = _render_or_log(
        log,
        failures,
        lambda: visualization.render_assignment_heatmap(model, features_h5, wsi_path),
        label="heatmap",
    )
    if inference.heatmap_path:
        successes += 1

    inference.mixture_plot_path = _render_or_log(
        log,
        failures,
        lambda: visualization.render_mixture_plot(model, features_h5),
        label="mixture",
    )
    if inference.mixture_plot_path:
        successes += 1

    inference.example_patches_dir = _render_or_log(
        log,
        failures,
        lambda: visualization.render_example_patches(model, features_h5, wsi_path),
        label="example_patches",
    )
    if inference.example_patches_dir:
        successes += 1

    inference.tsne_path = _render_or_log(
        log,
        failures,
        lambda: visualization.render_tsne_per_slide(model, features_h5, wsi_path),
        label="tsne",
    )
    if inference.tsne_path:
        successes += 1

    inference.status = "ready" if successes > 0 else "failed"
    inference.finished_at = datetime.utcnow()
    if successes == 0:
        inference.error_message = "All visualization steps failed; see job log."
    db.add(inference)
    db.commit()

    log.write(
        f"Done: status={inference.status}, successes={successes}, failures={len(failures)}"
    )
    if failures:
        for f in failures:
            log.write(f"  - {f}")


def _render_or_log(
    log: JobLog,
    failures: list[str],
    fn,
    *,
    label: str,
) -> str | None:
    try:
        out = fn()
        log.write(f"  {label}: {out}")
        return str(out)
    except Exception as exc:  # noqa: BLE001 — one render failing shouldn't abort the rest
        failures.append(f"{label}: {exc}")
        log.write(f"  FAILED {label}: {exc}\n{traceback.format_exc()}")
        return None


def _cuda_visible_devices(model: Model, db: Session) -> str:
    """Map TRIDENT's --gpus list into the CUDA_VISIBLE_DEVICES env var.

    -1 means CPU; we leave CUDA_VISIBLE_DEVICES empty in that case.
    """
    params = inference_service.inherited_trident_params(model, db)
    parts = inference_service._parse_gpus(params.gpus)  # noqa: SLF001 — internal helper
    if parts == ["-1"]:
        return ""
    return ",".join(parts)


def _mark_failed(db: Session, log: JobLog, inference: Inference, message: str) -> None:
    log.write(f"FAILED: {message}")
    inference.status = "failed"
    inference.error_message = message[:2000]
    inference.finished_at = datetime.utcnow()
    db.add(inference)
    db.commit()


def _tail(text: str, max_chars: int) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return "…" + text[-max_chars:]


def register() -> None:
    register_handler("inference", handle_inference)
