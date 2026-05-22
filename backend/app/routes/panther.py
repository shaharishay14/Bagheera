"""PANTHER K-fold run endpoints."""
from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.db.models import Model, PantherRun, Split
from app.models.schemas import (
    CreateSplitRequest,
    FoldOutcome,
    KFoldRunSummary,
    ModelInfo,
    PantherKFoldRunRequest,
    PantherKFoldRunResponse,
    PantherRunInfo,
    SplitInfo,
)
from app.services import panther_runner
from app.services.fs import resolve_within_roots
from app.services.splitter import SplitterError, create_kfold_split

router = APIRouter(prefix="/api/panther", tags=["panther"])


# --- splits ---------------------------------------------------------------


def _split_to_info(row: Split) -> SplitInfo:
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


def _require_panther_repo() -> str:
    if not settings.panther_repo_path:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="PANTHER_REPO_PATH is not set on the server.",
        )
    return settings.panther_repo_path


def _create_split_record(
    db: Session,
    *,
    dataset_name: str,
    source_csv: Path,
    k: int,
    seed: int,
) -> Split:
    repo_path = _require_panther_repo()
    output_root = panther_runner.dataset_splits_root_abs(repo_path, dataset_name)
    output_root.mkdir(parents=True, exist_ok=True)

    try:
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


@router.post("/splits", response_model=SplitInfo)
def create_split(payload: CreateSplitRequest, db: Session = Depends(get_db)) -> SplitInfo:
    _require_panther_repo()
    source_csv = resolve_within_roots(payload.source_csv)
    if not source_csv.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_csv must be an existing file.",
        )
    row = _create_split_record(
        db,
        dataset_name=payload.dataset_name,
        source_csv=source_csv,
        k=payload.k,
        seed=payload.seed,
    )
    return _split_to_info(row)


@router.get("/splits", response_model=list[SplitInfo])
def list_splits(
    dataset_name: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[SplitInfo]:
    q = db.query(Split).order_by(Split.created_at.desc())
    if dataset_name:
        q = q.filter(Split.dataset_name == dataset_name)
    return [_split_to_info(r) for r in q.all()]


# --- models ---------------------------------------------------------------


def _model_to_info(row: Model) -> ModelInfo:
    return ModelInfo(
        id=row.id,
        created_at=row.created_at,
        base_name=row.base_name,
        model_name=row.model_name,
        group_id=row.group_id,
        fold_index=row.fold_index,
        fold_k=row.fold_k,
        dataset_name=row.dataset_name,
        features_dir=row.features_dir,
        split_id=row.split_id,
        split_name=row.split_name,
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
    )


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


@router.get("/runs", response_model=list[PantherRunInfo])
def list_runs(
    group_id: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[PantherRunInfo]:
    q = db.query(PantherRun).order_by(PantherRun.created_at.desc(), PantherRun.fold_index.asc())
    if group_id:
        q = q.filter(PantherRun.group_id == group_id)
    return [_run_to_info(r) for r in q.all()]


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


# --- K-fold training ------------------------------------------------------


def _resolve_or_create_split(
    payload: PantherKFoldRunRequest, db: Session
) -> Split:
    if payload.split_name:
        row = db.query(Split).filter(Split.split_name == payload.split_name).one_or_none()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown split_name: {payload.split_name!r}",
            )
        if row.dataset_name != payload.dataset_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"split_name {payload.split_name!r} belongs to dataset "
                    f"{row.dataset_name!r}, not {payload.dataset_name!r}."
                ),
            )
        return row

    if not payload.source_csv or not payload.k or payload.split_seed is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide either split_name OR (source_csv + k + split_seed) to create a new split.",
        )
    source_csv = resolve_within_roots(payload.source_csv)
    if not source_csv.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="source_csv must be an existing file.",
        )
    return _create_split_record(
        db,
        dataset_name=payload.dataset_name,
        source_csv=source_csv,
        k=payload.k,
        seed=payload.split_seed,
    )


@router.post("/run", response_model=PantherKFoldRunResponse)
def start_run(
    payload: PantherKFoldRunRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> PantherKFoldRunResponse:
    repo_path = _require_panther_repo()

    features_dir = resolve_within_roots(payload.features_dir)
    if not features_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="features_dir must be an existing directory.",
        )

    split = _resolve_or_create_split(payload, db)
    group_id = str(uuid.uuid4())
    outcomes: list[FoldOutcome] = []

    for i in range(split.k):
        rand8 = secrets.token_hex(4)
        model_name = f"{payload.model_name}_k{i}_{rand8}"
        model_id = str(uuid.uuid4())
        run_id = str(uuid.uuid4())

        split_dir_rel = panther_runner.fold_dir_rel(payload.dataset_name, split.split_name, i)
        fold_abs = panther_runner.fold_dir_abs(
            repo_path, payload.dataset_name, split.split_name, i
        )
        prototypes_dir = fold_abs / "prototypes"

        cmd = panther_runner.build_command(
            panther_runner.PantherFoldArgs(
                features_dir=str(features_dir),
                split_dir_rel=split_dir_rel,
                mode=payload.mode,
                in_dim=payload.in_dim,
                n_proto_patches=payload.n_proto_patches,
                n_proto=payload.n_proto,
                n_init=payload.n_init,
                seed=payload.seed,
                num_workers=payload.num_workers,
            )
        )
        command_str = panther_runner.render_command(cmd)

        model_row = Model(
            id=model_id,
            created_at=datetime.utcnow(),
            base_name=payload.model_name,
            model_name=model_name,
            group_id=group_id,
            fold_index=i,
            fold_k=split.k,
            dataset_name=payload.dataset_name,
            features_dir=str(features_dir),
            split_id=split.id,
            split_name=split.split_name,
            mode=payload.mode,
            in_dim=payload.in_dim,
            n_proto_patches=payload.n_proto_patches,
            n_proto=payload.n_proto,
            n_init=payload.n_init,
            seed=payload.seed,
            num_workers=payload.num_workers,
            status="running",
            prototypes_dir=str(prototypes_dir),
        )
        run_row = PantherRun(
            id=run_id,
            created_at=datetime.utcnow(),
            group_id=group_id,
            fold_index=i,
            model_id=model_id,
            dataset_name=payload.dataset_name,
            features_dir=str(features_dir),
            split_name=split.split_name,
            mode=payload.mode,
            in_dim=payload.in_dim,
            n_proto_patches=payload.n_proto_patches,
            n_proto=payload.n_proto,
            n_init=payload.n_init,
            seed=payload.seed,
            num_workers=payload.num_workers,
            command=command_str,
            status="running",
        )
        db.add(model_row)
        db.add(run_row)
        db.commit()

        result = panther_runner.execute(
            cmd, cwd=panther_runner.panther_src_dir(repo_path)
        )

        run_row.stdout = result.stdout
        run_row.stderr = result.stderr
        run_row.return_code = result.returncode

        prototype_files: list[str] = []
        if result.returncode == 0:
            prototype_files = panther_runner.scan_prototype_files(prototypes_dir)
            if prototype_files:
                model_status = "ready"
            else:
                model_status = "failed"
        else:
            model_status = "failed"

        model_row.status = model_status
        model_row.prototype_files = json.dumps(prototype_files)
        run_row.status = "succeeded" if result.returncode == 0 else "failed"

        db.add(model_row)
        db.add(run_row)
        db.commit()

        outcomes.append(
            FoldOutcome(
                fold_index=i,
                model_id=model_id,
                model_name=model_name,
                status=model_status,
                prototypes_dir=str(prototypes_dir),
                prototype_files=prototype_files,
                return_code=result.returncode,
                stderr_tail=_tail(result.stderr, 2000),
            )
        )

        panther_runner.between_folds_cleanup()

    succeeded = sum(1 for o in outcomes if o.status == "ready")
    failed = len(outcomes) - succeeded
    if succeeded == 0:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    elif failed > 0:
        response.status_code = status.HTTP_207_MULTI_STATUS

    return PantherKFoldRunResponse(
        group_id=group_id,
        split_id=split.id,
        split_name=split.split_name,
        k=split.k,
        models=outcomes,
        summary=KFoldRunSummary(total=len(outcomes), succeeded=succeeded, failed=failed),
    )


def _tail(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return "…" + text[-max_chars:]
