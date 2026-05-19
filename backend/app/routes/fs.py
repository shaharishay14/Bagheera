"""Filesystem browsing endpoints."""
from __future__ import annotations

import csv
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.config import settings
from app.models.schemas import FsCsvCountResponse, FsListResponse, FsRootsResponse
from app.services.fs import list_directory, resolve_within_roots

router = APIRouter(prefix="/api/fs", tags=["fs"])


@router.get("/roots", response_model=FsRootsResponse)
def get_roots() -> FsRootsResponse:
    return FsRootsResponse(roots=[str(r) for r in settings.allowed_roots])


@router.get("/list", response_model=FsListResponse)
def list_dir(
    path: Optional[str] = Query(default=None),
    show_hidden: bool = Query(default=False),
    filter: Optional[Literal["dirs_only"]] = Query(default=None),
) -> FsListResponse:
    target, parent, entries, at_root = list_directory(
        path,
        show_hidden=show_hidden,
        dirs_only=(filter == "dirs_only"),
    )
    return FsListResponse(
        path=str(target),
        parent=str(parent) if parent is not None else None,
        entries=entries,
        is_root=at_root,
    )


@router.get("/csv-count", response_model=FsCsvCountResponse)
def csv_count(path: str = Query(..., min_length=1)) -> FsCsvCountResponse:
    resolved = resolve_within_roots(path)
    if not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a file.")
    if resolved.suffix.lower() != ".csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Expected a .csv file."
        )
    try:
        with resolved.open(newline="") as f:
            reader = csv.reader(f)
            next(reader, None)  # skip header
            count = sum(1 for _ in reader)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read CSV: {exc.strerror or exc}",
        )
    return FsCsvCountResponse(rows=count)
