"""TRIDENT run lookup endpoints (separate from /api/trident which owns POST + list)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.db.models import TridentRun
from app.models.schemas import RunResolveResponse
from app.services.fs import resolve_within_roots
from app.services.runner import feature_dim_for

router = APIRouter(prefix="/api/runs", tags=["runs"])


@router.get("/resolve", response_model=RunResolveResponse)
def resolve_features_dir(
    features_dir: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
) -> RunResolveResponse:
    """Match a features directory back to the TRIDENT run that produced it.

    TridentRun.output_dir is the canonical features directory of a run; we accept
    either that exact path or a path that is the same as it after `Path.resolve()`.
    """
    target = resolve_within_roots(features_dir)
    target_str = str(target)

    rows = db.query(TridentRun).all()
    matches: list[TridentRun] = []
    for row in rows:
        try:
            candidate = Path(row.output_dir).expanduser().resolve()
        except OSError:
            continue
        if str(candidate) == target_str:
            matches.append(row)

    if not matches:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"No TRIDENT run found whose output_dir matches {target_str!r}. "
                "Run TRIDENT first or pick a different features directory."
            ),
        )
    if len(matches) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Ambiguous: {len(matches)} TRIDENT runs share output_dir {target_str!r}."
            ),
        )
    row = matches[0]
    return RunResolveResponse(
        trident_run_id=row.id,
        dataset_name=row.dataset_name,
        output_dir=row.output_dir,
        patch_encoder=row.patch_encoder,
        mag=row.mag,
        patch_size=row.patch_size,
        in_dim=feature_dim_for(row.patch_encoder),
    )
