"""Per-WSI inference pipeline glue for trained PANTHER fold models.

Pure helpers — no class state, no I/O at module import. Used by the
`inference` job handler in `services/inference_job.py` and by the
`/api/inferences` route layer.

Public surface (per plan §5d):

    compute_wsi_hash(wsi_path)                            -> str (sha256 hex)
    lookup_cached_inference(db, model_id, wsi_path)       -> Inference | None
    build_trident_command(model, wsi_path, output_dir,
                          custom_csv_path, gpus="0")      -> list[str]
    locate_features_file(model, output_dir, wsi_stem)     -> Path
    generate_custom_wsi_csv(wsi_path, csv_target_path)    -> None

------------------------------------------------------------------------
ASSUMPTIONS — VALIDATE ON FIRST DEPLOY
------------------------------------------------------------------------

These were inferred by reading TRIDENT source + the
`prototypical_assignment_map_visualization.ipynb` notebook + my PR 3
visualization module. Each is the most plausible interpretation but
couldn't be exercised end-to-end locally (no GPU, deps not installed,
TRIDENT/PANTHER subprocesses can't run on my Mac). If any of these turn
out wrong on the first real run, the failing step will land in the job
log; the fix is usually a one-line change here.

1. TRIDENT --custom_list_of_wsis CSV format
   Confirmed by grepping TRIDENT source + docs:
     - docs/api.rst:62          "the CSV must have a `wsi` column"
     - docs/quickstart.rst:127  "column `wsi` with paths"
     - README.md:206            "Provide a list of WSI names in a CSV (with slide extension, `wsi`)"
   We write a single-row CSV with header `wsi` and value = WSI BASENAME
   (not absolute path — TRIDENT joins basename against --wsi_dir).
   If a real run reveals it wants the full path, change the value in
   `generate_custom_wsi_csv` below.

2. TRIDENT --gpus shape
   Confirmed: parser.add_argument('--gpus', type=int, nargs='+'),
   default=None. -1 indicates CPU. We accept a string like "0" or "0 1"
   and split into individual args. Default "0" since we don't currently
   persist per-run GPU config on TridentRun.

3. TridentRun does NOT store gpus
   The Bagheera schema's TridentRun has no `gpus` column. We default to
   "0" for inference. If you want per-run GPU customization in the
   future, add the column + plumb through TridentForm. The trident-params
   endpoint and `build_trident_command` both treat gpus as a sane default
   today.

4. TRIDENT output path pattern
   Confirmed by reading PR 3's assumption #5 + TRIDENT's own conventions:
     {job_dir}/{mag}x_{patch_size}px_0px_overlap/features_{patch_encoder}/{wsi_stem}.h5
   `mag` and `patch_size` in the path are the *requested* values passed
   on the CLI, not encoder-derived. Phikon uses patch_size=224, UNI uses
   256 — but the path uses whatever you pass. We pass the model's
   inherited patch_size to keep path + content consistent.

5. WSI stem == file basename without extension
   We use `Path(wsi_path).stem` to derive the expected h5 filename.
   TRIDENT preserves the input filename stem in the output h5. If a real
   run produces h5s with a different naming convention (e.g. uuid-based),
   `locate_features_file` will raise FileNotFoundError with the expected
   path — easy to spot.

6. --custom_list_of_wsis constrains a multi-file --wsi_dir to one slide
   The plan calls this out as something to verify. Per TRIDENT docs:
   "process a CSV subset" — yes, the CSV filters which slides under
   --wsi_dir get processed. If this turns out wrong (i.e. TRIDENT
   processes everything in --wsi_dir regardless), fallback is to symlink
   or copy the single WSI into an isolated temp dir and point --wsi_dir
   at that. We do NOT preemptively isolate; we trust TRIDENT's documented
   behavior first.

7. run_batch_of_slides.py is invocable from cwd=$TRIDENT_REPO_PATH
   The backend's existing PANTHER subprocess (services/panther_runner.py)
   sets cwd, and the TRIDENT one (services/runner.py) goes through a
   bash wrapper that uses absolute paths. For inference we run TRIDENT
   directly with cwd=$TRIDENT_REPO_PATH so its relative imports resolve.

8. Hash computation
   SHA-256 streamed in 1 MB chunks (see HASH_CHUNK_BYTES). On NVMe ~5 s/GB.
   For 50 GB slides this is ~4 minutes — acceptable, runs once per
   (model, slide). If it becomes a bottleneck in practice, downgrade to
   mtime+size only and document the rare-false-cache-hit caveat.

9. Cache invalidation
   `lookup_cached_inference` returns a row only when mtime + size AND
   sha256 all match. If a WSI is replaced in place with the same mtime
   and size (extremely unlikely without a deliberate `touch`), the hash
   confirms. If the row's hash doesn't match, the function returns None
   and the caller treats it as a cache miss.

10. The TRIDENT subprocess may not be invocable on this developer's
    machine (no GPU deps). The `inference` job handler is designed so
    `subprocess.run` of TRIDENT failing produces a clean job-log
    traceback and status='failed' on the inference row — same graceful
    degradation pattern as PR 3.

------------------------------------------------------------------------
"""
from __future__ import annotations

import csv
import hashlib
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Inference, Model, TridentRun

logger = logging.getLogger(__name__)

HASH_CHUNK_BYTES = 1024 * 1024  # 1 MB — see assumption #8
DEFAULT_GPUS = "0"


class InferenceServiceError(RuntimeError):
    """Inference setup / wiring problem (logged into the job log)."""


# ---------------------------------------------------------------------------
# Hashing + cache lookup
# ---------------------------------------------------------------------------


def compute_wsi_hash(wsi_path: Path | str) -> str:
    """SHA-256 of the file at `wsi_path`, streamed in 1 MB chunks.

    Returns the hex digest. Raises InferenceServiceError if the file is
    missing or unreadable.
    """
    p = Path(wsi_path)
    if not p.is_file():
        raise InferenceServiceError(f"WSI file not found: {p}")
    h = hashlib.sha256()
    try:
        with p.open("rb") as f:
            while True:
                chunk = f.read(HASH_CHUNK_BYTES)
                if not chunk:
                    break
                h.update(chunk)
    except OSError as exc:
        raise InferenceServiceError(f"Failed to read WSI for hashing: {p}: {exc}")
    return h.hexdigest()


def lookup_cached_inference(
    db: Session, model_id: str, wsi_path: Path | str
) -> Optional[Inference]:
    """Return an existing inference row if the cache hit is *verified*.

    Pre-check: stat the file for mtime + size; query for any row matching
    (model_id, wsi_path, mtime, size). If the pre-check passes, compute
    the sha256 and confirm it matches the stored wsi_hash. The hash is the
    source of truth — pre-check is just the optimization that avoids
    hashing on every page load.

    Returns None on:
      - file missing on disk
      - no row matches the pre-check
      - row matches pre-check but stored hash differs from actual hash
        (rare — file replaced in place)
    """
    p = Path(wsi_path)
    if not p.is_file():
        return None
    try:
        stat = p.stat()
    except OSError:
        return None

    candidates = (
        db.query(Inference)
        .filter(
            Inference.model_id == model_id,
            Inference.wsi_path == str(p),
            Inference.wsi_mtime == stat.st_mtime,
            Inference.wsi_size == stat.st_size,
        )
        .all()
    )
    if not candidates:
        return None

    try:
        actual_hash = compute_wsi_hash(p)
    except InferenceServiceError:
        return None

    for row in candidates:
        if row.wsi_hash == actual_hash:
            return row
    return None


# ---------------------------------------------------------------------------
# TRIDENT subprocess plumbing
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InheritedTridentParams:
    """The TRIDENT settings a fold model was originally trained against."""

    trident_run_id: Optional[str]
    patch_encoder: Optional[str]
    mag: Optional[int]
    patch_size: Optional[int]
    gpus: str = DEFAULT_GPUS


def inherited_trident_params(model: Model, db: Session) -> InheritedTridentParams:
    """Resolve the model's inherited TRIDENT params (encoder, mag, patch_size, gpus).

    Used by both `build_trident_command` and the /api/models/{id}/trident-params
    endpoint, so they always return the same numbers.
    """
    if not model.trident_run_id:
        return InheritedTridentParams(
            trident_run_id=None,
            patch_encoder=None,
            mag=None,
            patch_size=None,
            gpus=DEFAULT_GPUS,
        )
    run = db.get(TridentRun, model.trident_run_id)
    if run is None:
        return InheritedTridentParams(
            trident_run_id=model.trident_run_id,
            patch_encoder=None,
            mag=None,
            patch_size=None,
            gpus=DEFAULT_GPUS,
        )
    return InheritedTridentParams(
        trident_run_id=run.id,
        patch_encoder=run.patch_encoder,
        mag=run.mag,
        patch_size=run.patch_size,
        gpus=DEFAULT_GPUS,
    )


def expected_features_dir_name(mag: int, patch_size: int) -> str:
    """E.g. '20x_256px_0px_overlap'. See assumption #4."""
    return f"{mag}x_{patch_size}px_0px_overlap"


def trident_output_root(output_dir: Path | str) -> Path:
    return Path(output_dir) / "trident_output"


def locate_features_file(
    output_dir: Path | str,
    wsi_stem: str,
    *,
    mag: int,
    patch_size: int,
    patch_encoder: str,
) -> Path:
    """Build + return the path TRIDENT writes to. See assumption #4."""
    feats_dir = (
        trident_output_root(output_dir)
        / expected_features_dir_name(mag, patch_size)
        / f"features_{patch_encoder}"
    )
    target = feats_dir / f"{wsi_stem}.h5"
    if not target.is_file():
        raise FileNotFoundError(
            f"TRIDENT features file not found at expected path: {target}. "
            "If TRIDENT actually wrote it somewhere else, update the path "
            "convention in services/inference.py (assumption #4)."
        )
    return target


def generate_custom_wsi_csv(wsi_path: Path | str, csv_target_path: Path | str) -> None:
    """Write a one-row CSV with header `wsi` and value = basename.

    See assumption #1.

    TODO: surface an MPP override for slides without embedded resolution.
    Per TRIDENT's docs/faq.rst:63, PNG/JPEG inputs require an `mpp` column
    in the custom_list CSV. We currently only emit `wsi`. When the
    Inference page wants to accept such inputs, add an optional `mpp`
    arg here and a corresponding UI field, then write both columns.
    """
    wsi = Path(wsi_path)
    target = Path(csv_target_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["wsi"])
        writer.writerow([wsi.name])


def _parse_gpus(gpus: str | None) -> list[str]:
    """Split a 'gpus' string like '0' / '0 1 2' / '-1' into individual CLI tokens."""
    if gpus is None or not gpus.strip():
        return [DEFAULT_GPUS]
    parts = [p for p in gpus.replace(",", " ").split() if p]
    return parts or [DEFAULT_GPUS]


def build_trident_command(
    model: Model,
    db: Session,
    wsi_path: Path | str,
    output_dir: Path | str,
    custom_csv_path: Path | str,
) -> list[str]:
    """Construct the argv for run_batch_of_slides.py for one WSI.

    Caller is responsible for invoking with cwd=$TRIDENT_REPO_PATH (per
    assumption #7) and for having already written the single-row CSV at
    `custom_csv_path` (via `generate_custom_wsi_csv`).
    """
    params = inherited_trident_params(model, db)
    if not params.patch_encoder or params.mag is None or params.patch_size is None:
        raise InferenceServiceError(
            f"Cannot build TRIDENT command for model {model.id!r}: "
            "missing inherited TRIDENT params (no trident_run_id or run row deleted)."
        )

    python = settings.trident_python or "python"
    script = "run_batch_of_slides.py"  # relative to cwd=$TRIDENT_REPO_PATH

    wsi = Path(wsi_path)
    cmd: list[str] = [
        python,
        script,
        "--task",
        "all",
        "--wsi_dir",
        str(wsi.parent),
        "--custom_list_of_wsis",
        str(custom_csv_path),
        "--job_dir",
        str(trident_output_root(output_dir)),
        "--patch_encoder",
        params.patch_encoder,
        "--mag",
        str(params.mag),
        "--patch_size",
        str(params.patch_size),
        "--gpus",
        *_parse_gpus(params.gpus),
    ]
    return cmd


def render_command(cmd: list[str]) -> str:
    """Shell-safe single-line rendering for logs / UI command previews."""
    return " ".join(shlex.quote(part) for part in cmd)


# ---------------------------------------------------------------------------
# Output directory layout
# ---------------------------------------------------------------------------


def inference_output_dir(model_id: str, inference_id: str) -> Path:
    """{INFERENCE_ROOT}/{model_id}/{inference_id}/ — created on demand."""
    out = settings.inference_root / model_id / inference_id
    out.mkdir(parents=True, exist_ok=True)
    return out
