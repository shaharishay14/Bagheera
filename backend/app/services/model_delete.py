"""Delete a Model Group and all of its dependent rows + on-disk artifacts.

Kept thin and called from `routes/models.py` so the route stays a thin shell.

There are NO `ON DELETE CASCADE` constraints in the schema, so every dependent
row is deleted manually in FK-safe order. Shared rows (`Split`, `TridentRun`)
are intentionally left intact — they may back other groups.

On-disk cleanup runs *after* the DB commit. Every directory removed is guarded
so a half-cleaned state can never crash the request and we never `rmtree` outside
an allowed location.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import (
    Inference,
    InferenceBatch,
    InferenceNote,
    Job,
    Model,
    ModelGroup,
    ModelNote,
    PantherRun,
    PrototypeLabel,
)
from app.services.fs import resolve_within_roots

# Job statuses that block deletion (an active job still references the group/models).
_ACTIVE_JOB_STATUSES = ("queued", "running")


@dataclass
class DeleteSummary:
    group_id: str
    models_deleted: int = 0
    inferences_deleted: int = 0
    inference_notes_deleted: int = 0
    inference_batches_deleted: int = 0
    prototype_labels_deleted: int = 0
    model_notes_deleted: int = 0
    panther_runs_deleted: int = 0
    dirs_removed: list[str] = field(default_factory=list)


def _child_within(root: Path, name: str) -> Path | None:
    """Resolve ``root/name`` and require it to stay inside ``root``.

    ``name`` is a model_id (uuid) in practice, but we still verify the resolved
    child does not escape the cache root before handing it to ``rmtree``.
    """
    try:
        candidate = (root / name).resolve()
        candidate.relative_to(root.resolve())
    except (OSError, ValueError, RuntimeError):
        return None
    return candidate


def _rm_dir(path: Path, summary: DeleteSummary) -> None:
    try:
        if path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
            summary.dirs_removed.append(str(path))
    except OSError:
        # A half-cleaned state must never crash the request.
        pass


def delete_model_group(db: Session, group_id: str) -> DeleteSummary:
    """Delete a group, its fold models, and all dependent rows + artifacts.

    Raises ``HTTPException`` 404 if the group is missing, 409 if any fold model
    is running or an active job still references the group/models.
    """
    group = db.get(ModelGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")

    models = db.query(Model).filter(Model.group_id == group_id).all()
    model_ids = [m.id for m in models]

    # --- Refuse if anything is still in flight --------------------------
    if any(m.status == "running" for m in models):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete: one or more fold models are still running.",
        )

    ref_ids = [group_id, *model_ids]
    active_job = (
        db.query(Job)
        .filter(
            Job.ref_table.in_(("model_groups", "models")),
            Job.ref_id.in_(ref_ids),
            Job.status.in_(_ACTIVE_JOB_STATUSES),
        )
        .first()
    )
    if active_job is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot delete: an active (queued/running) job still references this group.",
        )

    summary = DeleteSummary(group_id=group_id)

    # Capture what the post-commit disk cleanup needs BEFORE the rows are
    # deleted — accessing an expired ORM instance after delete raises.
    model_artifacts = [(m.id, m.prototypes_dir) for m in models]

    # --- Delete dependent rows in FK-safe order (single transaction) ----
    if model_ids:
        inferences = db.query(Inference).filter(Inference.model_id.in_(model_ids)).all()
        inference_ids = [inf.id for inf in inferences]

        if inference_ids:
            summary.inference_notes_deleted = (
                db.query(InferenceNote)
                .filter(InferenceNote.inference_id.in_(inference_ids))
                .delete(synchronize_session=False)
            )

        summary.inferences_deleted = (
            db.query(Inference)
            .filter(Inference.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        summary.inference_batches_deleted = (
            db.query(InferenceBatch)
            .filter(InferenceBatch.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        summary.prototype_labels_deleted = (
            db.query(PrototypeLabel)
            .filter(PrototypeLabel.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        summary.model_notes_deleted = (
            db.query(ModelNote)
            .filter(ModelNote.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        summary.panther_runs_deleted = (
            db.query(PantherRun)
            .filter(PantherRun.model_id.in_(model_ids))
            .delete(synchronize_session=False)
        )
        summary.models_deleted = (
            db.query(Model)
            .filter(Model.id.in_(model_ids))
            .delete(synchronize_session=False)
        )

    db.query(ModelGroup).filter(ModelGroup.id == group_id).delete(synchronize_session=False)
    db.commit()

    # --- On-disk cleanup (post-commit, fully guarded) -------------------
    viz_root = Path(settings.viz_cache_root)
    inf_root = Path(settings.inference_root)
    for model_id, prototypes_dir in model_artifacts:
        viz_dir = _child_within(viz_root, model_id)
        if viz_dir is not None:
            _rm_dir(viz_dir, summary)
        inf_dir = _child_within(inf_root, model_id)
        if inf_dir is not None:
            _rm_dir(inf_dir, summary)

        # prototypes_dir lives under PANTHER's tree; remove only if it resolves
        # inside an allowed root. split_dir_abs is shared (Split-managed) — never touched.
        if prototypes_dir:
            try:
                proto_dir = resolve_within_roots(prototypes_dir)
            except HTTPException:
                continue
            _rm_dir(proto_dir, summary)

    return summary
