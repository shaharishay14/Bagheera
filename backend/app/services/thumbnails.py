"""Small-thumbnail helper for the WSI slide pickers.

Two jobs, both kept dependency-light so the server boots without ML deps:

1. `find_trident_thumbnail(features_dir, slide_stem)` — locate a thumbnail
   TRIDENT already wrote next to a features dir. No heavy imports (pure path
   probing + the `resolve_within_roots` security check).
2. `generate_slide_thumbnail(resolved_path, max_px)` — fall back to opening the
   WSI with openslide (LAZY import) and rendering a plain small RGB JPEG, cached
   under `{VIZ_CACHE_ROOT}/slide_thumbs/{key}.jpg`. The cache key is a stable
   hash of (resolved_path, mtime, size, max_px) so repeat requests are cheap.

The route layer (`routes/thumbnails.py`) owns the HTTP contract, status codes,
and the `X-Thumbnail-Source` header.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from app.config import settings
from app.services.fs import resolve_within_roots

# TRIDENT writes one thumbnail per slide. We probe these extensions in order.
_TRIDENT_THUMB_EXTS = (".jpg", ".jpeg", ".png")


class ThumbnailError(Exception):
    """Raised when the WSI can't be opened / rendered (→ HTTP 422 at the route)."""


def trident_job_dir(features_dir: str | Path) -> Path:
    """Derive the TRIDENT job dir from a features dir.

    The canonical features layout (see services/runner.py `output_dir_for`) is::

        {job_dir}/{mag}x_{ps}px_0px_overlap/features_{encoder}

    so the job dir is two levels up from the features dir. This is a pure path
    computation (no filesystem access); the caller validates existence + roots.
    """
    return Path(features_dir).parent.parent


def find_trident_thumbnail(features_dir: str | Path, slide_stem: str) -> Path | None:
    """Return an existing TRIDENT-written thumbnail for ``slide_stem``, or None.

    Probes ``{job_dir}/thumbnails/{slide_stem}{ext}`` for ext in
    ``.jpg, .jpeg, .png`` (in that order) and returns the first hit after
    running it through `resolve_within_roots` (the security boundary). Returns
    None when nothing matches so the caller can fall through to generation.

    F3 CAVEAT: the exact TRIDENT thumbnail subpath and extension are UNVERIFIED
    — the TRIDENT README was not vendored into this repo. This code assumes a
    `thumbnails/` subdir under the job dir with the slide stem as the filename.
    Confirm this against a real GPU data dir on first deploy; if TRIDENT uses a
    different subpath/extension, update `_TRIDENT_THUMB_EXTS` / this function.
    """
    thumbs_dir = trident_job_dir(features_dir) / "thumbnails"
    for ext in _TRIDENT_THUMB_EXTS:
        candidate = thumbs_dir / f"{slide_stem}{ext}"
        if candidate.is_file():
            # Security boundary: only serve if it resolves inside an allowed root.
            return resolve_within_roots(str(candidate))
    return None


def slide_thumb_cache_key(
    resolved_path: str | Path, mtime: float | int, size: int, max_px: int = 512
) -> str:
    """Deterministic cache key for a generated slide thumbnail.

    Stable across processes for the same (path, mtime, size, max_px), so repeat
    requests hit the on-disk cache instead of re-opening the WSI.
    """
    raw = f"{resolved_path}|{mtime}|{size}|{max_px}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def slide_thumbs_dir() -> Path:
    return settings.viz_cache_root / "slide_thumbs"


def generate_slide_thumbnail(resolved_path: Path, max_px: int = 512) -> Path:
    """Generate (or reuse a cached) plain small RGB JPEG thumbnail for a WSI.

    Longest side <= ``max_px``. No scale bar / coords overlay — just a small
    picker thumbnail. Cached under `{VIZ_CACHE_ROOT}/slide_thumbs/{key}.jpg`.

    Raises `ThumbnailError` on any openslide failure (the route maps it to 422).
    Heavy imports (openslide, PIL) are LAZY so importing this module never pulls
    in ML deps.
    """
    try:
        stat = resolved_path.stat()
    except OSError as exc:  # pragma: no cover — caller already checked is_file
        raise ThumbnailError(f"Cannot stat WSI: {exc}") from exc

    key = slide_thumb_cache_key(str(resolved_path), stat.st_mtime_ns, stat.st_size, max_px)
    cache_dir = slide_thumbs_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    out_path = cache_dir / f"{key}.jpg"
    if out_path.is_file():
        return out_path

    # Lazy heavy imports — the server boots without openslide/PIL installed.
    try:
        import openslide  # noqa: WPS433

        wsi = openslide.OpenSlide(str(resolved_path))
        try:
            # get_thumbnail fits the image inside the box, preserving aspect,
            # so the longest side ends up <= max_px.
            thumb = wsi.get_thumbnail((max_px, max_px)).convert("RGB")
        finally:
            try:
                wsi.close()
            except Exception:  # noqa: BLE001 — best-effort close
                pass
    except ThumbnailError:
        raise
    except Exception as exc:  # noqa: BLE001 — openslide raises a variety of errors
        raise ThumbnailError(f"Failed to open/render WSI: {exc}") from exc

    # Write atomically-ish: save to a temp name then replace, so a partial write
    # from a crash never leaves a corrupt cache entry that looks complete.
    tmp_path = cache_dir / f"{key}.jpg.tmp"
    thumb.save(str(tmp_path), format="JPEG", quality=85, optimize=True)
    tmp_path.replace(out_path)
    return out_path
