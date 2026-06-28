"""PANTHER training endpoints — async, returns immediately after enqueuing the job.

Read-only listing endpoints for PantherRun (per-fold execution logs) and Model
rows remain here for now; broader Models/Groups CRUD lives in routes/models.py
(PR 4).
"""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import Model, ModelGroup, PantherRun, Split, TridentRun
from app.models.schemas import (
    ModelInfo,
    PantherKFoldRunRequest,
    PantherKFoldStartResponse,
    PantherRunInfo,
)
from app.services import panther_runner
from app.services.fs import resolve_within_roots
from app.services.runner import feature_dim_for
from app.services.worker import enqueue_job

router = APIRouter(prefix="/api/panther", tags=["panther"])


def _model_to_info(row: Model) -> ModelInfo:
    return ModelInfo(
        id=row.id,
        created_at=row.created_at,
        base_name=row.base_name,
        model_name=row.model_name,
        display_name=row.display_name,
        group_id=row.group_id,
        fold_index=row.fold_index,
        fold_k=row.fold_k,
        dataset_name=row.dataset_name,
        features_dir=row.features_dir,
        trident_run_id=row.trident_run_id,
        split_id=row.split_id,
        split_name=row.split_name,
        split_dir_abs=row.split_dir_abs,
        mode=row.mode,
        in_dim=row.in_dim,
        n_proto_patches=row.n_proto_patches,
        n_proto=row.n_proto,
        n_init=row.n_init,
        seed=row.seed,
        num_workers=row.num_workers,
        status=row.status,
        prototypes_dir=row.prototypes_dir,
        prototype_files=json.loads(row.prototype_files or "[]"),
        is_favorite=row.is_favorite,
        viz_status=row.viz_status,
        preview_slide_ids=json.loads(row.preview_slide_ids) if row.preview_slide_ids else None,
        preview_heatmap_paths=(
            json.loads(row.preview_heatmap_paths) if row.preview_heatmap_paths else None
        ),
        topk_grid_path=row.topk_grid_path,
        topk_per_proto=row.topk_per_proto,
        umap_path=row.umap_path,
        viz_artifacts=json.loads(row.viz_artifacts) if row.viz_artifacts else None,
    )


def _run_to_info(row: PantherRun) -> PantherRunInfo:
    return PantherRunInfo(
        id=row.id,
        created_at=row.created_at,
        group_id=row.group_id,
        fold_index=row.fold_index,
        model_id=row.model_id,
        dataset_name=row.dataset_name,
        features_dir=row.features_dir,
        split_name=row.split_name,
        mode=row.mode,
        in_dim=row.in_dim,
        n_proto_patches=row.n_proto_patches,
        n_proto=row.n_proto,
        n_init=row.n_init,
        seed=row.seed,
        num_workers=row.num_workers,
        command=row.command,
        status=row.status,
        stdout=row.stdout,
        stderr=row.stderr,
        return_code=row.return_code,
    )


@router.get("/runs", response_model=list[PantherRunInfo])
def list_runs(
    group_id: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[PantherRunInfo]:
    q = db.query(PantherRun).order_by(PantherRun.created_at.desc(), PantherRun.fold_index.asc())
    if group_id:
        q = q.filter(PantherRun.group_id == group_id)
    return [_run_to_info(r) for r in q.all()]


@router.get("/models", response_model=list[ModelInfo])
def list_models(
    group_id: str | None = Query(None),
    dataset_name: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[ModelInfo]:
    q = db.query(Model).order_by(Model.created_at.desc(), Model.fold_index.asc())
    if group_id:
        q = q.filter(Model.group_id == group_id)
    if dataset_name:
        q = q.filter(Model.dataset_name == dataset_name)
    return [_model_to_info(r) for r in q.all()]


@router.post("/runs", response_model=PantherKFoldStartResponse)
def start_run(
    payload: PantherKFoldRunRequest, db: Session = Depends(get_db)
) -> PantherKFoldStartResponse:
    if not settings.panther_repo_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PANTHER_REPO_PATH is not set on the server.",
        )

    features_dir = resolve_within_roots(payload.features_dir)
    if not features_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="features_dir must be an existing directory.",
        )

    split = db.get(Split, payload.split_id)
    if split is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown split_id: {payload.split_id!r}",
        )
    if split.dataset_name != payload.dataset_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"split_id {payload.split_id!r} belongs to dataset "
                f"{split.dataset_name!r}, not {payload.dataset_name!r}."
            ),
        )

    trident_run_id = _resolve_trident_run_id(db, features_dir)

    # in_dim is a fixed property of the encoder's features, not a tunable knob, so
    # derive it from the resolved TRIDENT run and override whatever the form sent.
    # This guarantees correctness even if a stale client submits the wrong value;
    # fall back to the submitted value only when the encoder is unknown.
    in_dim = payload.in_dim
    if trident_run_id is not None:
        trun = db.get(TridentRun, trident_run_id)
        if trun is not None:
            derived = feature_dim_for(trun.patch_encoder)
            if derived is not None:
                in_dim = derived

    group_id = str(uuid.uuid4())
    db.add(
        ModelGroup(
            id=group_id,
            created_at=datetime.utcnow(),
            display_name=payload.model_name,
            dataset_name=payload.dataset_name,
            trident_run_id=trident_run_id,
            k=split.k,
            split_id=split.id,
        )
    )

    model_ids: list[str] = []
    for i in range(split.k):
        model_id = str(uuid.uuid4())
        rand8 = secrets.token_hex(4)
        model_name = f"{payload.model_name}_k{i}_{rand8}"
        fold_abs = panther_runner.fold_dir_abs(
            settings.panther_repo_path, payload.dataset_name, split.split_name, i
        )
        prototypes_dir = fold_abs / "prototypes"
        db.add(
            Model(
                id=model_id,
                created_at=datetime.utcnow(),
                base_name=payload.model_name,
                model_name=model_name,
                display_name=payload.model_name,
                group_id=group_id,
                fold_index=i,
                fold_k=split.k,
                dataset_name=payload.dataset_name,
                features_dir=str(features_dir),
                trident_run_id=trident_run_id,
                split_id=split.id,
                split_name=split.split_name,
                split_dir_abs=str(fold_abs),
                mode=payload.mode,
                in_dim=in_dim,
                n_proto_patches=payload.n_proto_patches,
                n_proto=payload.n_proto,
                n_init=payload.n_init,
                seed=payload.seed,
                num_workers=payload.num_workers,
                status="running",
                prototypes_dir=str(prototypes_dir),
                viz_status="pending",
            )
        )
        model_ids.append(model_id)
    db.commit()

    job = enqueue_job(db, job_type="panther_train", ref_table="model_groups", ref_id=group_id)

    return PantherKFoldStartResponse(
        group_id=group_id,
        job_id=job.id,
        k=split.k,
        split_id=split.id,
        split_name=split.split_name,
        model_ids=model_ids,
    )


def _resolve_trident_run_id(db: Session, features_dir: Path) -> str | None:
    """Optionally bind the new model_group to its parent TRIDENT run.

    Mirrors /api/runs/resolve but returns None on miss instead of 400, so that
    PANTHER training isn't blocked when features were produced outside Bagheera.
    """
    target = str(features_dir)
    rows = db.query(TridentRun).all()
    matches = []
    for row in rows:
        try:
            candidate = str(Path(row.output_dir).expanduser().resolve())
        except OSError:
            continue
        if candidate == target:
            matches.append(row)
    if len(matches) == 1:
        return matches[0].id
    return None
