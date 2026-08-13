"""Dataset / slide / model enumeration endpoints for the Model Comparison page.

There is NO Dataset/Slide table: `dataset_name` is a denormalized string on
`Model`, and slides are just the per-slide `.h5` files under a model's TRIDENT
`features_dir`. These endpoints derive both from the `Model` rows.

Only NON-LEGACY models participate: standalone runs carry `run_kind="single"`,
whereas legacy K-fold folds have `run_kind IS NULL`. A dataset that only has
legacy folds is invisible to the comparison page.

All heavy work stays lazy — no ML imports here. Path enumeration goes through
`resolve_within_roots` (the security boundary).
"""
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import Model
from app.models.schemas import (
    DatasetSlide,
    DatasetSlidesResponse,
    DatasetSummary,
    ModelInfo,
)
from app.routes.panther import _model_to_info
from app.services.fs import resolve_within_roots
from app.services.thumbnails import find_trident_thumbnail
from app.services.visualization import resolve_dataset_wsi_dir, resolve_wsi_path

router = APIRouter(prefix="/api/datasets", tags=["datasets"])


def _representative_model(db: Session, dataset_name: str) -> Model | None:
    """The newest non-legacy model for a dataset (source of features_dir/wsi_dir)."""
    return (
        db.query(Model)
        .filter(Model.dataset_name == dataset_name, Model.run_kind == "single")
        .order_by(Model.created_at.desc())
        .first()
    )


@router.get("", response_model=list[DatasetSummary])
def list_datasets(db: Session = Depends(get_db)) -> list[DatasetSummary]:
    """Distinct dataset_names that have >=1 non-legacy (run_kind="single") model.

    A dataset whose only models are legacy K-fold folds (run_kind IS NULL) does
    NOT appear. `model_count` counts single models only.
    """
    rows = (
        db.query(Model.dataset_name, func.count(Model.id))
        .filter(Model.run_kind == "single")
        .group_by(Model.dataset_name)
        .order_by(Model.dataset_name.asc())
        .all()
    )
    return [
        DatasetSummary(dataset_name=name, model_count=count)
        for name, count in rows
    ]


@router.get("/{dataset_name}/slides", response_model=DatasetSlidesResponse)
def list_dataset_slides(
    dataset_name: str, db: Session = Depends(get_db)
) -> DatasetSlidesResponse:
    """Enumerate a dataset's slides = the `.h5` files under a representative
    single-model's `features_dir`.

    404 if the dataset has no non-legacy model. A missing/unreadable
    features_dir is handled gracefully (empty slides + a `note`, never a 500).
    """
    model = _representative_model(db, dataset_name)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No non-legacy model found for dataset {dataset_name!r}.",
        )

    features_dir_raw = model.features_dir
    # wsi_dir: resolve from the model's TridentRun (may be None if unlinked).
    wsi_dir = resolve_dataset_wsi_dir(model, db)
    wsi_dir_str = str(wsi_dir) if wsi_dir is not None else None

    # Resolve features_dir through the security boundary; degrade gracefully if
    # it's outside roots, missing, or not a directory.
    try:
        features_dir = resolve_within_roots(features_dir_raw)
    except HTTPException:
        return DatasetSlidesResponse(
            dataset_name=dataset_name,
            features_dir=features_dir_raw,
            wsi_dir=wsi_dir_str,
            slides=[],
            slide_count=0,
            thumbnails_found=0,
            note="features_dir is outside the allowed roots.",
        )

    if not features_dir.is_dir():
        return DatasetSlidesResponse(
            dataset_name=dataset_name,
            features_dir=str(features_dir),
            wsi_dir=wsi_dir_str,
            slides=[],
            slide_count=0,
            thumbnails_found=0,
            note="features_dir does not exist or is not a directory.",
        )

    # Enumerate slides = `.h5` files directly under features_dir (not recursive).
    try:
        stems = sorted(p.stem for p in features_dir.glob("*.h5"))
    except OSError as exc:
        return DatasetSlidesResponse(
            dataset_name=dataset_name,
            features_dir=str(features_dir),
            wsi_dir=wsi_dir_str,
            slides=[],
            slide_count=0,
            thumbnails_found=0,
            note=f"features_dir is unreadable: {exc}",
        )

    features_dir_q = quote(str(features_dir), safe="")
    slides: list[DatasetSlide] = []
    thumbnails_found = 0
    for stem in stems:
        # F3 early-signal: does TRIDENT already have a thumbnail on disk?
        # find_trident_thumbnail probes {job_dir}/thumbnails/{stem}.{jpg,jpeg,png}
        # (job_dir = features_dir.parent.parent) through resolve_within_roots.
        try:
            if find_trident_thumbnail(features_dir, stem) is not None:
                thumbnails_found += 1
        except HTTPException:
            # Thumbnail sat outside allowed roots — not a usable hit.
            pass

        wsi_path: str | None = None
        if wsi_dir is not None:
            resolved_wsi = resolve_wsi_path(stem, wsi_dir)
            if resolved_wsi is not None:
                try:
                    wsi_path = str(resolve_within_roots(str(resolved_wsi)))
                except HTTPException:
                    wsi_path = None

        thumbnail_url: str | None = None
        if wsi_path is not None:
            thumbnail_url = (
                f"/api/slide-thumbnail?path={quote(wsi_path, safe='')}"
                f"&features_dir={features_dir_q}"
            )

        slides.append(
            DatasetSlide(
                slide_id=stem,
                wsi_path=wsi_path,
                has_wsi=wsi_path is not None,
                thumbnail_url=thumbnail_url,
            )
        )

    return DatasetSlidesResponse(
        dataset_name=dataset_name,
        features_dir=str(features_dir),
        wsi_dir=wsi_dir_str,
        slides=slides,
        slide_count=len(slides),
        thumbnails_found=thumbnails_found,
    )


@router.get("/{dataset_name}/models", response_model=list[ModelInfo])
def list_dataset_models(
    dataset_name: str, db: Session = Depends(get_db)
) -> list[ModelInfo]:
    """Non-legacy (run_kind="single") models for a dataset, newest first.

    Powers the Add-model dropdown on the Model Comparison page (the UI caps the
    selection at 4).
    """
    rows = (
        db.query(Model)
        .filter(Model.dataset_name == dataset_name, Model.run_kind == "single")
        .order_by(Model.created_at.desc())
        .all()
    )
    return [_model_to_info(r) for r in rows]
