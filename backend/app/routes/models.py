"""Model + ModelGroup CRUD for the Models browser and Group detail pages.

These endpoints live under /api/model-groups and /api/models, separate from
/api/panther which only owns the training kick-off.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Model, ModelGroup, Split, TridentRun
from app.models.schemas import (
    ModelGroupDeleteResponse,
    ModelGroupDetail,
    ModelGroupListItem,
    ModelGroupPatch,
    ModelGroupSummary,
    ModelInfo,
    ModelPatch,
    ShufflePreviewResponse,
    SplitInfo,
    TridentParamsResponse,
)
from app.routes.panther import _model_to_info  # reuse the converter
from app.routes.splits import _to_info as _split_to_info
from app.services import inference as inference_service
from app.services.model_delete import delete_model_group
from app.services.preview import pick_preview_slides
from app.services.worker import enqueue_job

router = APIRouter(prefix="/api", tags=["models"])


# --- Helpers --------------------------------------------------------------


def _summarize_models(models: list[Model]) -> ModelGroupSummary:
    ready = sum(1 for m in models if m.status == "ready")
    failed = sum(1 for m in models if m.status == "failed")
    running = sum(1 for m in models if m.status in {"pending", "running"})
    favorited = sum(1 for m in models if m.is_favorite)
    return ModelGroupSummary(
        total=len(models),
        ready=ready,
        failed=failed,
        running=running,
        favorited=favorited,
    )


def _group_to_listitem(group: ModelGroup, models: list[Model], split: Split) -> ModelGroupListItem:
    representative = models[0] if models else None
    return ModelGroupListItem(
        id=group.id,
        created_at=group.created_at,
        display_name=group.display_name,
        dataset_name=group.dataset_name,
        trident_run_id=group.trident_run_id,
        k=group.k,
        split_id=group.split_id,
        split_name=split.split_name,
        mode=representative.mode if representative else "",
        n_proto=representative.n_proto if representative else 0,
        summary=_summarize_models(models),
    )


# --- ModelGroup endpoints -------------------------------------------------


@router.get("/model-groups", response_model=list[ModelGroupListItem])
def list_groups(
    favorite_only: bool = Query(False),
    dataset_name: str | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("created_desc", pattern=r"^(created_desc|created_asc|name)$"),
    db: Session = Depends(get_db),
) -> list[ModelGroupListItem]:
    groups_q = db.query(ModelGroup)
    if dataset_name:
        groups_q = groups_q.filter(ModelGroup.dataset_name == dataset_name)
    if q:
        like = f"%{q}%"
        groups_q = groups_q.filter(ModelGroup.display_name.ilike(like))
    if sort == "created_asc":
        groups_q = groups_q.order_by(ModelGroup.created_at.asc())
    elif sort == "name":
        groups_q = groups_q.order_by(ModelGroup.display_name.asc())
    else:
        groups_q = groups_q.order_by(ModelGroup.created_at.desc())
    groups = groups_q.all()

    if not groups:
        return []

    group_ids = [g.id for g in groups]
    models_by_group: dict[str, list[Model]] = {gid: [] for gid in group_ids}
    for m in (
        db.query(Model)
        .filter(Model.group_id.in_(group_ids))
        .order_by(Model.fold_index.asc())
        .all()
    ):
        models_by_group[m.group_id].append(m)

    splits_by_id = {s.id: s for s in db.query(Split).filter(Split.id.in_({g.split_id for g in groups})).all()}

    out: list[ModelGroupListItem] = []
    for g in groups:
        ms = models_by_group.get(g.id, [])
        split = splits_by_id.get(g.split_id)
        if split is None:
            continue
        item = _group_to_listitem(g, ms, split)
        if favorite_only and item.summary.favorited == 0:
            continue
        out.append(item)
    return out


@router.get("/model-groups/{group_id}", response_model=ModelGroupDetail)
def get_group(group_id: str, db: Session = Depends(get_db)) -> ModelGroupDetail:
    group = db.get(ModelGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    split = db.get(Split, group.split_id)
    if split is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Group references a split that no longer exists.",
        )
    models = (
        db.query(Model)
        .filter(Model.group_id == group_id)
        .order_by(Model.fold_index.asc())
        .all()
    )
    # Sort favorites to the top while preserving fold order within each tier.
    models.sort(key=lambda m: (0 if m.is_favorite else 1, m.fold_index))
    return ModelGroupDetail(
        group=_group_to_listitem(group, models, split),
        models=[_model_to_info(m) for m in models],
        split=SplitInfo(
            id=split.id,
            created_at=split.created_at,
            dataset_name=split.dataset_name,
            split_name=split.split_name,
            abs_path=split.abs_path,
            source_csv=split.source_csv,
            k=split.k,
            seed=split.seed,
            total_rows=split.total_rows,
            per_fold_counts=json.loads(split.per_fold_counts or "[]"),
        ),
    )


@router.patch("/model-groups/{group_id}", response_model=ModelGroupListItem)
def patch_group(
    group_id: str, payload: ModelGroupPatch, db: Session = Depends(get_db)
) -> ModelGroupListItem:
    group = db.get(ModelGroup, group_id)
    if group is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found.")
    if payload.display_name is not None:
        group.display_name = payload.display_name
        # Cascade to denormalized field on fold models so the Models page card
        # title stays in sync without a join.
        for m in db.query(Model).filter(Model.group_id == group_id).all():
            m.display_name = payload.display_name
            db.add(m)
        db.add(group)
        db.commit()
    split = db.get(Split, group.split_id)
    models = db.query(Model).filter(Model.group_id == group_id).order_by(Model.fold_index.asc()).all()
    return _group_to_listitem(group, models, split)


@router.delete("/model-groups/{group_id}", response_model=ModelGroupDeleteResponse)
def delete_group(group_id: str, db: Session = Depends(get_db)) -> ModelGroupDeleteResponse:
    """Delete a group, its fold models, all dependent rows, and on-disk artifacts.

    404 if the group is missing; 409 if a fold model is still running or an
    active (queued/running) job references the group or its models. Shared
    Split / TridentRun rows are left intact.
    """
    summary = delete_model_group(db, group_id)
    return ModelGroupDeleteResponse(
        group_id=summary.group_id,
        models_deleted=summary.models_deleted,
        inferences_deleted=summary.inferences_deleted,
        inference_notes_deleted=summary.inference_notes_deleted,
        inference_batches_deleted=summary.inference_batches_deleted,
        prototype_labels_deleted=summary.prototype_labels_deleted,
        model_notes_deleted=summary.model_notes_deleted,
        panther_runs_deleted=summary.panther_runs_deleted,
        dirs_removed=summary.dirs_removed,
    )


# --- Model endpoints ------------------------------------------------------


@router.get("/models/{model_id}", response_model=ModelInfo)
def get_model(model_id: str, db: Session = Depends(get_db)) -> ModelInfo:
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    return _model_to_info(model)


@router.patch("/models/{model_id}", response_model=ModelInfo)
def patch_model(
    model_id: str, payload: ModelPatch, db: Session = Depends(get_db)
) -> ModelInfo:
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    if payload.is_favorite is not None:
        model.is_favorite = payload.is_favorite
    if payload.display_name is not None:
        model.display_name = payload.display_name
    db.add(model)
    db.commit()
    db.refresh(model)
    return _model_to_info(model)


@router.post("/models/{model_id}/shuffle-preview", response_model=ShufflePreviewResponse)
def shuffle_preview(model_id: str, db: Session = Depends(get_db)) -> ShufflePreviewResponse:
    """Re-pick the 3 preview slide IDs and enqueue a re-render of the heatmaps.

    For PR 4 the post_train_viz handler is stubbed; PR 3 swaps it for the real
    renderer that consumes preview_slide_ids.
    """
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    slide_ids = pick_preview_slides(model)
    model.preview_slide_ids = json.dumps(slide_ids)
    model.viz_status = "pending"
    db.add(model)
    db.commit()

    job_id: str | None = None
    if slide_ids:
        job = enqueue_job(db, job_type="post_train_viz", ref_table="models", ref_id=model.id)
        job_id = job.id

    return ShufflePreviewResponse(
        model_id=model.id, preview_slide_ids=slide_ids, job_id=job_id
    )


@router.get("/models/{model_id}/trident-params", response_model=TridentParamsResponse)
def get_trident_params(model_id: str, db: Session = Depends(get_db)) -> TridentParamsResponse:
    model = db.get(Model, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    params = inference_service.inherited_trident_params(model, db)
    expected_dir = None
    if params.mag is not None and params.patch_size is not None:
        expected_dir = inference_service.expected_features_dir_name(
            params.mag, params.patch_size
        )
    return TridentParamsResponse(
        trident_run_id=params.trident_run_id,
        patch_encoder=params.patch_encoder,
        mag=params.mag,
        patch_size=params.patch_size,
        gpus=params.gpus,
        expected_features_dir_name=expected_dir,
    )
