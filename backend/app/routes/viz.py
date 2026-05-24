"""Visualization artifact serving + placeholders.

Two responsibilities:

1. `/api/viz/placeholder/{kind}` synthesizes an SVG placeholder on the fly.
   Used by the UI when a real rendered image isn't available yet (newly
   trained model, viz job in flight, seed data without files on disk).

2. `/api/viz/{file_path:path}` serves a real rendered image from disk.
   Files live under either VIZ_CACHE_ROOT (PR 3's post_train_viz output:
   per-fold heatmaps, top-K grids, UMAPs) or INFERENCE_ROOT (PR 5's
   inference output: per-slide heatmaps, mixture plots, example patches,
   t-SNE projections). The endpoint accepts both absolute and root-relative
   paths and matches against both roots; first hit wins.

Deploy-day verification (do these on the remote desktop after the first
real render lands):

  1. Confirm INFERENCE_ROOT and VIZ_CACHE_ROOT in `.env` are absolute paths.
     Relative paths resolve from uvicorn's cwd — usually `backend/` —
     which is fine in dev but surprises everyone in production.
  2. Confirm both directories are readable by the uvicorn user. A 404
     where you expected an image usually means a permissions miss.
  3. After a real training run, `ls viz_cache/{model_id}/` should show
     heatmap_*.png, topk_grid.png, umap.png. Hit /api/viz/{absolute_path}
     for one of them and confirm the bytes come back with the right
     content-type (FileResponse auto-infers from the filename suffix —
     .png → image/png, .jpg → image/jpeg, .svg → image/svg+xml).
  4. After a real inference run, `ls inference_outputs/{model_id}/{inference_id}/`
     should show the per-slide viz files. Same probe as above.

Path-traversal protection:
  - We resolve the candidate path with `Path.resolve()` which follows
    symlinks AND collapses `..`. Then we require the resolved path to
    sit under VIZ_CACHE_ROOT or INFERENCE_ROOT. A symlink pointing
    outside the roots fails this check after resolve. A `..` segment
    that escapes either root fails too.
  - Out-of-roots ABSOLUTE paths return 403 (deliberate — the user gave
    us a real path that we can't serve).
  - Missing files under either root return 404.
  - No directory listing endpoint exists — listing is intentional only
    via `/api/inferences/{id}/example-patches` for the patches dir,
    which enumerates files but doesn't serve directory bytes.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Path as PathParam, Query, Response, status
from fastapi.responses import FileResponse

from app.config import settings

router = APIRouter(prefix="/api/viz", tags=["viz"])

# Keep the kind→color map deterministic so previews look stable across reloads.
_KIND_COLORS: dict[str, tuple[str, str, str]] = {
    "heatmap": ("#fef3c7", "#b45309", "Heatmap"),
    "mixture": ("#dbeafe", "#1d4ed8", "Mixture"),
    "patches": ("#dcfce7", "#15803d", "Example patches"),
    "tsne": ("#ede9fe", "#6d28d9", "t-SNE"),
    "topk": ("#ffe4e6", "#be123c", "Top-K grid"),
    "umap": ("#f5f5f4", "#44403c", "UMAP"),
}

_DEFAULT_KIND = ("#e2e8f0", "#475569", "Preview")


@router.get("/placeholder/{kind}")
def placeholder(
    kind: str = PathParam(...),
    label: str | None = Query(None),
    width: int = Query(480, ge=64, le=2048),
    height: int = Query(320, ge=64, le=2048),
) -> Response:
    """SVG placeholder. Used by the UI when no real render is available."""
    bg, fg, title = _KIND_COLORS.get(kind, _DEFAULT_KIND)
    text = label or title
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="xMidYMid meet">'
        f'<rect width="100%" height="100%" fill="{bg}"/>'
        f'<g fill="{fg}" font-family="ui-monospace,Menlo,monospace" '
        f'text-anchor="middle">'
        f'<text x="50%" y="46%" font-size="{max(14, width // 24)}" font-weight="600">{_escape(text)}</text>'
        f'<text x="50%" y="62%" font-size="{max(11, width // 36)}" opacity="0.6">placeholder</text>'
        f'</g></svg>'
    )
    return Response(content=svg, media_type="image/svg+xml")


def _escape(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


@router.get("/{file_path:path}")
def serve_viz(file_path: str) -> Response:
    """Serve a viz file from either VIZ_CACHE_ROOT or INFERENCE_ROOT.

    Accepts:
      - An absolute path (must resolve to a file under one of the roots)
      - A root-relative path (tried against each root in order)

    See the module docstring for the path-traversal contract.
    """
    candidate = Path(file_path)
    if not candidate.is_absolute():
        for root in (settings.viz_cache_root, settings.inference_root):
            maybe = (root / candidate).resolve()
            if _is_under(maybe, root) and maybe.is_file():
                return FileResponse(maybe)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    resolved = candidate.resolve()
    for root in (settings.viz_cache_root, settings.inference_root):
        if _is_under(resolved, root):
            if resolved.is_file():
                return FileResponse(resolved)
            # In-roots but missing → 404 (vs out-of-roots absolute → 403).
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="File not found."
            )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Path is outside the visualization cache roots.",
    )


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
