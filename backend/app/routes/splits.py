"""K-fold split CRUD endpoints."""
from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import Split
from app.models.schemas import CreateSplitRequest, SplitInfo
from app.services import panther_runner
from app.services.fs import resolve_within_roots
from app.services.splitter import SplitterError, create_kfold_split, create_single_split

router = APIRouter(prefix="/api/splits", tags=["splits"])


def _to_info(row: Split) -> SplitInfo:
    return SplitInfo(
        id=row.id,
        created_at=row.created_at,
        dataset_name=row.dataset_name,
        split_name=row.split_name,
        abs_path=row.abs_path,
        source_csv=row.source_csv,
        k=row.k,
        seed=row.seed,
        total_rows=row.total_rows,
        per_fold_counts=json.loads(row.per_fold_counts or "[]"),
    )


def _output_root_for(dataset_name: str) -> Path:
    """Where to write split folders. Prefers PANTHER_REPO_PATH/src/datasets_splits/{dataset},
    falls back to the standalone DATASETS_SPLITS_ROOT.
    """
    if settings.panther_repo_path:
        return panther_runner.dataset_splits_root_abs(settings.panther_repo_path, dataset_name)
    return settings.datasets_splits_root / dataset_name


def create_split_record(
    db: Session,
    *,
    dataset_name: str,
    source_csv: Path,
    k: int,
    seed: int,
    kind: str = "kfold",
) -> Split:
    output_root = _output_root_for(dataset_name)
    output_root.mkdir(parents=True, exist_ok=True)

    try:
        if kind == "single":
            info = create_single_split(
                dataset_name=dataset_name,
                source_csv=source_csv,
                output_root=output_root,
                seed=seed,
            )
        else:
            info = create_kfold_split(
                dataset_name=dataset_name,
                source_csv=source_csv,
                output_root=output_root,
                k=k,
                seed=seed,
            )
    except SplitterError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cannot write split files under {output_root}: {exc}",
        )

    row = Split(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name=dataset_name,
        split_name=info.split_name,
        abs_path=str(info.abs_path),
        source_csv=str(source_csv),
        k=info.k,
        seed=info.seed,
        total_rows=info.total_rows,
        per_fold_counts=json.dumps(info.per_fold_dicts()),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@router.post("", response_model=SplitInfo)
def create_split(payload: CreateSplitRequest, db: Session = Depends(get_db)) -> SplitInfo:
    source_csv = resolve_within_roots(payload.source_csv)
    if not source_csv.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_csv must be an existing file.",
        )
    row = create_split_record(
        db,
        dataset_name=payload.dataset_name,
        source_csv=source_csv,
        k=payload.k,
        seed=payload.seed,
        kind=payload.kind,
    )
    return _to_info(row)


@router.get("", response_model=list[SplitInfo])
def list_splits(
    dataset_name: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[SplitInfo]:
    q = db.query(Split).order_by(Split.created_at.desc())
    if dataset_name:
        q = q.filter(Split.dataset_name == dataset_name)
    return [_to_info(r) for r in q.all()]


@router.get("/{split_id}", response_model=SplitInfo)
def get_split(split_id: str, db: Session = Depends(get_db)) -> SplitInfo:
    row = db.get(Split, split_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Split not found.")
    return _to_info(row)
