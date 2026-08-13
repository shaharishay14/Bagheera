"""TRIDENT run endpoints."""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import TridentRun
from app.models.schemas import TridentRunRequest, TridentRunResponse
from app.services import runner
from app.services.fs import resolve_within_roots

router = APIRouter(prefix="/api/trident", tags=["trident"])


@router.post("/run", response_model=TridentRunResponse)
def start_run(payload: TridentRunRequest, db: Session = Depends(get_db)) -> TridentRunResponse:
    # Reuse the fs guard so /run cannot bypass the directory restrictions.
    wsi_path = resolve_within_roots(payload.wsi_dir)
    if not wsi_path.exists() or not wsi_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="wsi_dir must be an existing directory.",
        )

    try:
        cmd = runner.build_command(payload.dataset_name, str(wsi_path), payload.patch_encoder)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    command_str = runner.render_command(cmd)
    output_dir = runner.output_dir_for(payload.dataset_name, payload.patch_encoder)

    record = TridentRun(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name=payload.dataset_name,
        wsi_dir=str(wsi_path),
        patch_encoder=payload.patch_encoder,
        mag=runner.MAGNIFICATION,
        patch_size=runner.patch_size_for(payload.patch_encoder),
        command=command_str,
        status="running",
        output_dir=output_dir,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    result = runner.execute(cmd)

    record.stdout = result.stdout
    record.stderr = result.stderr
    record.return_code = result.returncode
    record.status = "succeeded" if result.returncode == 0 else "failed"
    db.add(record)
    db.commit()
    db.refresh(record)

    return TridentRunResponse.model_validate(record)


@router.get("/runs", response_model=list[TridentRunResponse])
def list_runs(db: Session = Depends(get_db)) -> list[TridentRunResponse]:
    rows = db.query(TridentRun).order_by(TridentRun.created_at.desc()).all()
    return [TridentRunResponse.model_validate(row) for row in rows]


@router.get("/runs/{run_id}", response_model=TridentRunResponse)
def get_run(run_id: str, db: Session = Depends(get_db)) -> TridentRunResponse:
    row = db.get(TridentRun, run_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    return TridentRunResponse.model_validate(row)
