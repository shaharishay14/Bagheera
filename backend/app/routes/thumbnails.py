"""WSI thumbnail endpoint for the slide pickers.

`GET /api/slide-thumbnail` returns a small binary image (FileResponse), NOT
JSON. Two sources, tried in order:

  1. A thumbnail TRIDENT already wrote next to the features dir
     (`X-Thumbnail-Source: trident`) — cheap, no ML deps on this path.
  2. A generated + cached small RGB JPEG opened via openslide
     (`X-Thumbnail-Source: generated`).

The picker degrades to a placeholder icon client-side when this returns a 422
(WSI couldn't be opened), so an openslide failure is a soft failure here.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse

from app.services.fs import resolve_within_roots
from app.services.thumbnails import (
    ThumbnailError,
    find_trident_thumbnail,
    generate_slide_thumbnail,
)

router = APIRouter(prefix="/api", tags=["viz"])


@router.get("/slide-thumbnail")
def slide_thumbnail(
    path: str = Query(..., description="Absolute path to the WSI file."),
    features_dir: str | None = Query(
        None, description="Optional TRIDENT features dir; used to find a prebuilt thumbnail."
    ),
    max_px: int = Query(512, ge=32, le=4096, description="Longest side of the thumbnail."),
) -> FileResponse:
    """Serve a small thumbnail for a WSI (TRIDENT-written first, else generated)."""
    # Security boundary + existence check.
    resolved = resolve_within_roots(path)
    if not resolved.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="WSI not found.")

    # 1. TRIDENT thumbnail first (if a features dir was supplied).
    if features_dir:
        trident_thumb = find_trident_thumbnail(features_dir, resolved.stem)
        if trident_thumb is not None:
            return FileResponse(trident_thumb, headers={"X-Thumbnail-Source": "trident"})

    # 2. Fallback — generate (lazy openslide) + cache.
    try:
        cached = generate_slide_thumbnail(resolved, max_px)
    except ThumbnailError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not generate thumbnail: {exc}",
        )
    return FileResponse(cached, headers={"X-Thumbnail-Source": "generated"})
