"""PANTHER run endpoints."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import PantherRun
from app.models.schemas import (
    PantherRunRequest,
    PantherRunResponse,
    SplitCounts,
)
from app.services import panther_runner
from app.services.fs import resolve_within_roots
from app.services.splitter import SplitterError, split_dataset

router = APIRouter(prefix="/api/panther", tags=["panther"])


@router.post("/run", response_model=PantherRunResponse)
def start_run(payload: PantherRunRequest, db: Session = Depends(get_db)) -> PantherRunResponse:
    if not settings.panther_repo_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PANTHER_REPO_PATH is not set on the server.",
        )

    if payload.train_pct + payload.val_pct + payload.test_pct > 100:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="train_pct + val_pct + test_pct cannot exceed 100.",
        )
    if payload.train_pct <= 0 or payload.val_pct <= 0 or payload.test_pct <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="train_pct, val_pct and test_pct must all be greater than 0.",
        )

    # Reuse the fs guard so /run cannot bypass the directory restrictions.
    features_dir = resolve_within_roots(payload.features_dir)
    if not features_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="features_dir must be an existing directory.",
        )
    source_csv = resolve_within_roots(payload.source_csv)
    if not source_csv.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_csv must be an existing file.",
        )

    split_dir = panther_runner.split_dir_abs(settings.panther_repo_path, payload.dataset_name)
    try:
        split = split_dataset(
            source_csv=source_csv,
            output_dir=split_dir,
            train_pct=payload.train_pct,
            val_pct=payload.val_pct,
            test_pct=payload.test_pct,
            n_chunks=payload.n_chunks,
            seed=payload.seed,
        )
    except SplitterError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cannot write split files under {split_dir}: {exc}",
        )

    try:
        cmd = panther_runner.build_command(payload, str(features_dir))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    command_str = panther_runner.render_command(cmd)

    record = PantherRun(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name=payload.dataset_name,
        features_dir=str(features_dir),
        source_csv=str(source_csv),
        train_pct=payload.train_pct,
        val_pct=payload.val_pct,
        test_pct=payload.test_pct,
        n_chunks=payload.n_chunks,
        mode=payload.mode,
        in_dim=payload.in_dim,
        n_proto_patches=payload.n_proto_patches,
        n_proto=payload.n_proto,
        n_init=payload.n_init,
        seed=payload.seed,
        num_workers=payload.num_workers,
        command=command_str,
        status="running",
        split_counts=json.dumps(split.as_dict()),
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    result = panther_runner.execute(
        cmd, cwd=panther_runner.panther_src_dir(settings.panther_repo_path)
    )

    record.stdout = result.stdout
    record.stderr = result.stderr
    record.return_code = result.returncode
    record.status = "succeeded" if result.returncode == 0 else "failed"
    db.add(record)
    db.commit()
    db.refresh(record)

    return _to_response(record)


@router.get("/runs", response_model=list[PantherRunResponse])
def list_runs(db: Session = Depends(get_db)) -> list[PantherRunResponse]:
    rows = db.query(PantherRun).order_by(PantherRun.created_at.desc()).all()
    return [_to_response(row) for row in rows]


@router.get("/runs/{run_id}", response_model=PantherRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)) -> PantherRunResponse:
    row = db.get(PantherRun, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return _to_response(row)


def _to_response(row: PantherRun) -> PantherRunResponse:
    counts_raw = json.loads(row.split_counts or "{}")
    counts = SplitCounts(
        train=counts_raw.get("train", 0),
        val=counts_raw.get("val", 0),
        test=counts_raw.get("test", 0),
        unused=counts_raw.get("unused", 0),
        total=counts_raw.get("total", 0),
    )
    return PantherRunResponse(
        id=row.id,
        created_at=row.created_at,
        dataset_name=row.dataset_name,
        features_dir=row.features_dir,
        source_csv=row.source_csv,
        train_pct=row.train_pct,
        val_pct=row.val_pct,
        test_pct=row.test_pct,
        n_chunks=row.n_chunks,
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
        split_counts=counts,
    )
