"""Filesystem browsing endpoints."""
from __future__ import annotations

import csv
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query, status

from app.config import settings
from app.models.schemas import (
    FsCsvCountResponse,
    FsCsvInspectResponse,
    FsListResponse,
    FsRootsResponse,
)
from app.services.fs import list_directory, resolve_within_roots
from app.services.preview import SLIDE_ID_COLUMNS

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


@router.get("/csv-inspect", response_model=FsCsvInspectResponse)
def csv_inspect(path: str = Query(..., min_length=1)) -> FsCsvInspectResponse:
    """Inspect a CSV: row count, columns, and slide_id-column diagnostics.

    Detects a slide-id column case-insensitively against the shared
    SLIDE_ID_COLUMNS set, counts values ending in .tif/.tiff, and returns a few
    sample raw values so the UI can preview the auto-fix the splitter applies.
    """
    resolved = resolve_within_roots(path)
    if not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a file.")
    if resolved.suffix.lower() != ".csv":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Expected a .csv file."
        )

    # Lazy import per the "heavy deps imported inside functions" convention.
    import pandas as pd

    try:
        df = pd.read_csv(resolved, dtype=str)
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")
    except Exception as exc:  # pandas raises a variety of parse errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read CSV: {exc}",
        )

    columns = [str(c) for c in df.columns]
    slide_id_column: str | None = None
    for col in columns:
        if col.strip().lower() in SLIDE_ID_COLUMNS:
            slide_id_column = col
            break

    if slide_id_column is None:
        return FsCsvInspectResponse(
            rows=int(len(df)),
            columns=columns,
            has_slide_id=False,
            slide_id_column=None,
            tif_count=0,
            sample_ids=[],
        )

    values = [v for v in df[slide_id_column].tolist() if v is not None and str(v) != "nan"]
    tif_count = sum(
        1 for v in values if str(v).lower().endswith((".tif", ".tiff"))
    )
    sample_ids = [str(v) for v in values[:5]]

    return FsCsvInspectResponse(
        rows=int(len(df)),
        columns=columns,
        has_slide_id=True,
        slide_id_column=slide_id_column,
        tif_count=tif_count,
        sample_ids=sample_ids,
    )
