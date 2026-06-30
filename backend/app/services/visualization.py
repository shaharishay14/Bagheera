"""Per-fold and per-slide visualization renderers for trained PANTHER models.

Implements the six §5c functions from the plan:

    render_assignment_heatmap(model, h5_path, wsi_path)              -> Path
    render_mixture_plot(model, h5_path)                              -> Path
    render_example_patches(model, h5_path, wsi_path, k_per_proto=4)  -> Path  (dir)
    render_tsne_per_slide(model, h5_path, wsi_path)                  -> Path
    render_topk_grid(model, dataset_features_dir, dataset_wsi_dir,
                     per_proto=3)                                    -> Path
    render_umap(model, dataset_features_dir)                         -> Path

Outputs are written under VIZ_CACHE_ROOT/{model_id}/ — the file path is
returned. The PR 6 static file endpoint will serve them at /api/viz/{file}.

------------------------------------------------------------------------
ASSUMPTIONS — VALIDATE ON FIRST DEPLOY
------------------------------------------------------------------------

These were inferred from reading PANTHER source + the
`prototypical_assignment_map_visualization.ipynb` notebook. Each is the most
plausible interpretation but couldn't be exercised end-to-end locally
(no GPU, deps not installed). If any of these turn out wrong on the first
real run, the failing render function will land in the job log and the
fix is usually a one-line change in this file.

1. Prototype .pkl file structure
   PANTHER writes prototypes with `pickle.dump({'prototypes': ndarray})`
   where the array has shape (n_proto, embed_dim) after `.squeeze()`.
   Confirmed by reading utils/proto_utils.py:check_prototypes:
       prototypes = load_pkl(proto_path)['prototypes'].squeeze()
   Assumption: both faiss and kmeans modes produce the same key/shape.
   If kmeans uses a different key (e.g. 'centroids'), update
   `_select_prototype_path` / loader call below.

2. PrototypeTokenizer signature
   The notebook calls `PrototypeTokenizer(p=16)` then `tokenizer.forward(out)`,
   but the default `out_type='param_cat'` raises NotImplementedError in the
   forward path — only `out_type='allcat'` is implemented. We pass
   `out_type='allcat'` explicitly. If a future PANTHER refactor renames this,
   adjust `_compute_assignments` below.

3. get_panther_encoder bug
   PANTHER's helper hardcodes `n_proto=16` (argparse default) and only honors
   the `p=` arg for `out_size`. For models trained with n_proto != 16 this
   loads the wrong shape and `check_prototypes` fails. We bypass it with
   `_load_panther_encoder` which sets both `n_proto` and `out_size` to the
   real model.n_proto. If PANTHER fixes their helper upstream, our local
   one stays a safe override.

4. PANTHER.representation() return shape
   Returns {'repr': out, 'qq': qqs}. `qqs[0, :, :, 0]` has shape
   (num_patches, n_proto) per the notebook indexing — confirmed in
   model_PANTHER.py:34-39. Soft assignment matrix; argmax gives per-patch
   cluster labels.

5. H5 feature file conventions
   TRIDENT-produced h5 files have:
       h5['features']             ndarray (num_patches, embed_dim)
       h5['coords']               ndarray (num_patches, 2) — (x, y) at level 0
       h5['coords'].attrs['patch_size']   int — patch side in pixels at level 0
   If TRIDENT renames these (e.g. 'feats' or 'patch_coords'), update
   `_load_h5`.

6. WSI file discovery
   For per-slide renderers we need the WSI file matching a slide_id.
   We search TridentRun.wsi_dir for files with stem == slide_id and any
   recognized extension (.svs, .tif, .tiff, .ndpi, .czi, .zarr, .mrxs, .scn).
   If the dataset uses a flat dir of WSIs named exactly by slide_id (the
   TRIDENT convention), this works. Nested directories or transformed
   filenames will need _resolve_wsi_path adjusted.

7. config_dir for create_embedding_model
   PANTHER's config_dir points at the dir containing model_config
   subdirectories (each holding a config.json). For a checkout this is
   `${PANTHER_REPO_PATH}/src/configs/`. The notebook example uses '../'
   because it runs from `src/visualization/` cwd — we use the absolute
   path so cwd doesn't matter.

8. mil_models import requires PANTHER_REPO_PATH/src on sys.path
   Their package uses `from utils.proto_utils import check_prototypes`-style
   absolute imports that assume `src/` is on PYTHONPATH. We prepend it
   lazily inside `_ensure_panther_on_syspath`.

9. Heavy deps (torch, openslide, sklearn/umap, matplotlib, h5py, PIL, cv2)
   are imported lazily inside render functions so the backend can boot in
   environments without them installed (dev laptops without a GPU). The
   `post_train_viz` job won't actually fire in such environments — but the
   API + UI continue to work, and the failure surfaces in the job log if
   it does fire.

10. UMAP cost on large datasets
    `render_umap` samples up to UMAP_MAX_PATCHES_PER_SLIDE patches per slide
    before fitting, capped at UMAP_MAX_TOTAL_PATCHES across the dataset.
    Tune these constants if a real dataset blows out memory or runtime.

11. Top-K grid cost
    `render_topk_grid` streams every h5 + WSI in the dataset once, keeping
    a per-prototype heap of the top patches by assignment score. Wall time
    scales with #slides; expected acceptable for typical PANTHER datasets
    (~500 slides) on a workstation. Heatmap-style crops at the level-0
    patch size are written into a grid image.

------------------------------------------------------------------------
"""
from __future__ import annotations

import heapq
import json
import logging
import math
import os
import pickle
import sys
from pathlib import Path
from typing import Iterable

from app.config import settings
from app.db.models import Model, TridentRun

logger = logging.getLogger(__name__)

# WSI extensions we'll match when resolving slide_id → file path.
WSI_EXTENSIONS = (".svs", ".tif", ".tiff", ".ndpi", ".czi", ".zarr", ".mrxs", ".scn")

# UMAP / top-K sampling caps (see assumption #10, #11).
UMAP_MAX_PATCHES_PER_SLIDE = 500
UMAP_MAX_TOTAL_PATCHES = 50_000
TOPK_DEFAULT_THUMB_PX = 96  # side length of each cropped patch in the grid

# Section A (Analysis page) tuning.
THUMB_MAX_PX = 2048          # longest side of the whole-slide thumbnail
SECTION_A_DOWNSAMPLE = 24    # hi-res assignment-map downsample target (zoomable)
ROI_GRID = 7                 # ROI is a ROI_GRID x ROI_GRID tile of patches
ROI_CELL_PX = 80             # rendered cell side in the colored ROI grid
ROI_RAW_MAX_PX = 768         # longest side of the raw ROI crop
ROI_TINT_ALPHA = 0.5         # blend weight of the prototype color over the patch


# ---------------------------------------------------------------------------
# PANTHER bootstrap (lazy — never touches sys.path at module import)
# ---------------------------------------------------------------------------


def _ensure_panther_on_syspath() -> str:
    if not settings.panther_repo_path:
        raise VisualizationError("PANTHER_REPO_PATH is not set on the server.")
    src = os.path.join(settings.panther_repo_path, "src")
    if not os.path.isdir(src):
        raise VisualizationError(
            f"PANTHER source dir not found: {src!r}. "
            "Check that PANTHER_REPO_PATH points at a checkout."
        )
    if src not in sys.path:
        sys.path.insert(0, src)
    return src


def _configs_dir() -> str:
    """Where mil_models.create_embedding_model looks for {model_config}/config.json."""
    return os.path.join(settings.panther_repo_path, "src", "configs")


class VisualizationError(RuntimeError):
    """User-facing visualization error (logged into the job log)."""


# ---------------------------------------------------------------------------
# Prototype + encoder loading
# ---------------------------------------------------------------------------


def _select_prototype_path(model: Model) -> Path:
    """Pick the prototype file that PANTHER training wrote for this fold.

    PANTHER usually writes one .pkl under prototypes_dir/. If there are
    multiple, we prefer the basename listed first in model.prototype_files
    (the canonical order TRIDENT/PANTHER wrote them in); else the
    lexicographically-first .pkl.
    """
    proto_dir = Path(model.prototypes_dir)
    if not proto_dir.is_dir():
        raise VisualizationError(f"Prototypes dir does not exist: {proto_dir}")

    listed: list[str] = []
    try:
        listed = json.loads(model.prototype_files or "[]")
    except json.JSONDecodeError:
        listed = []

    for name in listed:
        p = proto_dir / name
        if p.suffix in {".pkl", ".npy"} and p.is_file():
            return p

    fallback = sorted([p for p in proto_dir.iterdir() if p.suffix in {".pkl", ".npy"}])
    if not fallback:
        raise VisualizationError(
            f"No .pkl/.npy prototype files found under {proto_dir}"
        )
    return fallback[0]


def _load_panther_encoder(model: Model):
    """Local replacement for PANTHER's get_panther_encoder() — see assumption #3.

    Returns an instantiated, eval-mode PANTHER model wired up with this fold's
    prototypes.
    """
    _ensure_panther_on_syspath()

    # Imports deferred: heavy ML deps shouldn't be required to boot the API.
    import argparse  # noqa: WPS433

    from mil_models import create_embedding_model  # type: ignore[import-not-found]

    proto_path = _select_prototype_path(model)

    args = argparse.Namespace(
        model_type="PANTHER",
        proto_model_type="PANTHER",
        model_config="PANTHER_default",
        in_dim=model.in_dim,
        embed_dim=64,
        n_proto=model.n_proto,
        n_classes=2,
        out_size=model.n_proto,
        em_iter=1,
        tau=1.0,
        out_type="allcat",
        n_fc_layers=0,
        load_proto=1,
        ot_eps=1,
        fix_proto=1,
        proto_path=str(proto_path),
    )

    encoder = create_embedding_model(args, mode="emb", config_dir=_configs_dir())
    encoder.eval()
    return encoder


def _load_prototype_centers(model: Model) -> "np.ndarray":  # type: ignore[name-defined]
    """Load this fold's trained prototype centers as (n_proto, embed_dim) float32.

    PANTHER writes the prototypes as a pickled ``{'prototypes': ndarray}`` (see
    assumption #1); a few configs save a bare ``.npy``. We read the centers
    directly — no encoder needed — so Section B can measure how close held-out
    patches land to them.
    """
    import numpy as np  # noqa: WPS433

    proto_path = _select_prototype_path(model)
    if proto_path.suffix == ".npy":
        arr = np.load(proto_path, allow_pickle=True)
    else:
        import pickle  # noqa: WPS433

        with open(proto_path, "rb") as f:
            data = pickle.load(f)
        arr = data["prototypes"] if isinstance(data, dict) else data
    if hasattr(arr, "detach"):  # torch.Tensor
        arr = arr.detach().cpu().numpy()
    arr = np.asarray(arr, dtype=np.float32).squeeze()
    if arr.ndim != 2:
        arr = arr.reshape(model.n_proto, -1)
    return arr


# ---------------------------------------------------------------------------
# H5 + WSI helpers
# ---------------------------------------------------------------------------


def _load_h5(h5_path: Path) -> tuple["np.ndarray", "torch.Tensor", int]:  # type: ignore[name-defined]
    """Open a TRIDENT-produced h5 features file.

    Returns (coords ndarray, features torch.Tensor, patch_size px). Caller is
    responsible for closing the file (we close immediately since we copy the
    arrays into memory — files are typically small enough for that).
    """
    import h5py  # noqa: WPS433
    import torch  # noqa: WPS433

    with h5py.File(str(h5_path), "r") as h5:
        coords = h5["coords"][:]
        feats = torch.as_tensor(h5["features"][:], dtype=torch.float32)
        try:
            patch_size = int(h5["coords"].attrs["patch_size"])
        except KeyError:
            patch_size = 256  # safe default — TRIDENT's most common config
    return coords, feats, patch_size


def _open_wsi(wsi_path: Path):
    """openslide.open_slide wrapper that surfaces a friendly error."""
    import openslide  # noqa: WPS433

    if not wsi_path.is_file():
        raise VisualizationError(f"WSI file not found: {wsi_path}")
    return openslide.open_slide(str(wsi_path))


def resolve_wsi_path(slide_id: str, wsi_dir: Path | str) -> Path | None:
    """Find a WSI file whose stem matches `slide_id`, under `wsi_dir` or any
    subdirectory beneath it.

    Returns None if no match — callers skip slides with missing WSIs gracefully
    (per assumption #6). The recursive fallback supports datasets nested *under*
    the folder TRIDENT was pointed at: e.g. a run whose `wsi_dir=/data` whose
    slides actually live in `/data/Test/`. First stem-match (with a recognized
    extension) wins. `os.walk` over a very large root is the cost of this
    convenience; in practice `wsi_dir` is dataset-scoped so the subtree is small.
    """
    base = Path(wsi_dir)
    if not base.is_dir():
        return None
    # Cheap direct hits first (slide sitting directly in wsi_dir).
    for ext in WSI_EXTENSIONS:
        candidate = base / f"{slide_id}{ext}"
        if candidate.is_file():
            return candidate
    # Then any file at any depth whose stem matches and extension is recognized.
    # os.walk visits `base` itself first, so this also covers the flat case.
    exts = set(WSI_EXTENSIONS)
    for dirpath, _dirnames, filenames in os.walk(base):
        for name in filenames:
            p = Path(name)
            if p.stem == slide_id and p.suffix.lower() in exts:
                return Path(dirpath) / name
    return None


def _viz_dir(model: Model, subdir: str | None = None) -> Path:
    out = settings.viz_cache_root / model.id
    if subdir:
        out = out / subdir
    out.mkdir(parents=True, exist_ok=True)
    return out


def _features_files_iter(features_dir: Path) -> Iterable[Path]:
    return sorted(features_dir.glob("*.h5"))


# ---------------------------------------------------------------------------
# Encoder → per-slide assignments
# ---------------------------------------------------------------------------


def _compute_assignments(encoder, feats):
    """Run the PANTHER encoder on one slide's features.

    Returns:
        cluster_labels: ndarray (num_patches,) of int prototype indices
        qq:             ndarray (num_patches, n_proto) of soft assignments
        mixture_probs:  ndarray (n_proto,) of slide-level prototype proportions
    """
    import torch  # noqa: WPS433

    from mil_models.tokenizer import PrototypeTokenizer  # type: ignore[import-not-found]

    with torch.inference_mode():
        info = encoder.representation(feats.unsqueeze(dim=0))
        repr_out = info["repr"]
        qqs = info["qq"]

    qq = qqs[0, :, :, 0].detach().cpu().numpy()
    cluster_labels = qq.argmax(axis=1)

    # PrototypeTokenizer with out_type='allcat' returns (prob, mean, cov).
    tokenizer = PrototypeTokenizer(
        proto_model_type="PANTHER", out_type="allcat", p=qq.shape[1]
    )
    prob, _mean, _cov = tokenizer.forward(repr_out)
    mixture_probs = prob[0].detach().cpu().numpy()

    return cluster_labels, qq, mixture_probs


# ---------------------------------------------------------------------------
# §5c renderers
# ---------------------------------------------------------------------------


def render_assignment_heatmap(
    model: Model,
    h5_path: Path,
    wsi_path: Path,
    *,
    downsample_target: int = 128,
    out_path: Path | None = None,
) -> Path:
    """Categorical assignment heatmap painted over the WSI thumbnail.

    Per-slide. Output: viz_cache/{model_id}/heatmap_{slide_stem}.png

    `downsample_target` controls resolution: a smaller value renders the slide
    at a higher (more zoomable) resolution. Section A passes a small value
    (SECTION_A_DOWNSAMPLE); the per-fold previews keep the default 128.
    `out_path` lets a caller redirect the file (e.g. into the section_a/ dir).
    """
    encoder = _load_panther_encoder(model)
    coords, feats, patch_size = _load_h5(h5_path)
    cluster_labels, _qq, _probs = _compute_assignments(encoder, feats)
    if out_path is None:
        out_path = _viz_dir(model) / f"heatmap_{Path(h5_path).stem}.png"
    return render_assignment_heatmap_from_assignments(
        model,
        coords,
        cluster_labels,
        patch_size,
        wsi_path,
        downsample_target=downsample_target,
        out_path=out_path,
    )


def render_assignment_heatmap_from_assignments(
    model: Model,
    coords,
    cluster_labels,
    patch_size: int,
    wsi_path: Path,
    *,
    downsample_target: int = 128,
    crop_to_tissue: bool = False,
    out_path: Path | None = None,
) -> Path:
    """Paint a categorical assignment heatmap from already-computed assignments.

    Split out of `render_assignment_heatmap` so Section A can reuse the
    `(coords, cluster_labels)` it already computed for the thumbnail / π_c /
    ROI renders instead of re-running the encoder.

    When `crop_to_tissue` is set the overlay is cropped to the tissue bounding
    box of `coords` (same math as the thumbnail crop) so it frames the tissue
    and stays aligned with the cropped thumbnail in the Section A panel.
    """
    _ensure_panther_on_syspath()
    from visualization.prototype_visualization_utils import (  # type: ignore[import-not-found]
        get_default_cmap,
        visualize_categorical_heatmap,
    )

    wsi = _open_wsi(wsi_path)
    cmap = get_default_cmap(model.n_proto)
    # Match the notebook's choice; fall back to the deepest level if the slide
    # is too small to satisfy the requested downsample.
    try:
        vis_level = wsi.get_best_level_for_downsample(downsample_target)
    except Exception:  # noqa: BLE001 — openslide quirks
        vis_level = wsi.level_count - 1

    img = visualize_categorical_heatmap(
        wsi,
        coords,
        cluster_labels,
        label2color_dict=cmap,
        vis_level=vis_level,
        patch_size=(patch_size, patch_size),
        alpha=0.4,
        verbose=False,
    )

    if crop_to_tissue:
        w0, h0 = wsi.dimensions
        bbox = _tissue_bbox_level0(coords, patch_size, w0, h0)
        img = _crop_full_extent(img, w0, h0, bbox)

    if out_path is None:
        out_path = _viz_dir(model) / f"heatmap_{Path(wsi_path).stem}.png"
    img.save(str(out_path), format="PNG", optimize=True)
    return out_path


def render_mixture_plot(model: Model, h5_path: Path) -> Path:
    """Bar plot of prototype proportions for one slide.

    Per-slide. Output: viz_cache/{model_id}/mixture_{slide_stem}.png

    Doesn't need the WSI — features alone determine the mixture.
    """
    _ensure_panther_on_syspath()
    from visualization.prototype_visualization_utils import get_mixture_plot  # type: ignore[import-not-found]

    encoder = _load_panther_encoder(model)
    _coords, feats, _patch_size = _load_h5(h5_path)
    _labels, _qq, mixture_probs = _compute_assignments(encoder, feats)

    fig = get_mixture_plot(mixture_probs)
    out_path = _viz_dir(model) / f"mixture_{Path(h5_path).stem}.png"
    fig.savefig(str(out_path), bbox_inches="tight", dpi=150)
    _close_fig(fig)
    return out_path


def render_example_patches(
    model: Model,
    h5_path: Path,
    wsi_path: Path,
    k_per_proto: int = 4,
) -> Path:
    """Top-K patches per prototype FROM THIS SLIDE, saved as cropped PNGs.

    Per-slide. Output: viz_cache/{model_id}/example_patches_{slide_stem}/
        prototype_{kk:02d}/patch_{rank:02d}.png

    Returns the directory path. Caller can list it to build an index.
    """
    encoder = _load_panther_encoder(model)
    coords, feats, patch_size = _load_h5(h5_path)
    _labels, qq, _probs = _compute_assignments(encoder, feats)

    wsi = _open_wsi(wsi_path)
    out_dir = _viz_dir(model, subdir=f"example_patches_{Path(h5_path).stem}")

    # For each prototype, take the patches with the highest soft assignment.
    for proto_idx in range(qq.shape[1]):
        scores = qq[:, proto_idx]
        if scores.size == 0:
            continue
        top = _topk_indices(scores, k_per_proto)
        sub_dir = out_dir / f"prototype_{proto_idx:02d}"
        sub_dir.mkdir(parents=True, exist_ok=True)
        for rank, patch_idx in enumerate(top):
            x, y = int(coords[patch_idx][0]), int(coords[patch_idx][1])
            try:
                region = wsi.read_region(
                    (x, y), 0, (patch_size, patch_size)
                ).convert("RGB")
            except Exception as exc:  # noqa: BLE001 — openslide can throw
                logger.warning("read_region failed for %s patch %s: %s", wsi_path, patch_idx, exc)
                continue
            region.save(str(sub_dir / f"patch_{rank:02d}.png"), format="PNG", optimize=True)

    return out_dir


def render_tsne_per_slide(model: Model, h5_path: Path, wsi_path: Path) -> Path:
    """t-SNE of this slide's patch features, colored by cluster assignment.

    Per-slide. Output: viz_cache/{model_id}/tsne_{slide_stem}.png

    `wsi_path` is part of the signature for parity with other per-slide
    renderers but isn't read — t-SNE doesn't need pixels.
    """
    _ = wsi_path  # signature-only

    encoder = _load_panther_encoder(model)
    _coords, feats, _patch_size = _load_h5(h5_path)
    labels, _qq, _probs = _compute_assignments(encoder, feats)

    import matplotlib.pyplot as plt  # noqa: WPS433
    from sklearn.manifold import TSNE  # noqa: WPS433

    from visualization.prototype_visualization_utils import get_default_cmap  # type: ignore[import-not-found]

    feats_np = feats.detach().cpu().numpy()
    # Perplexity must be < n_samples; cap to stay reasonable on small slides.
    perplexity = max(5, min(30, feats_np.shape[0] // 4))
    tsne = TSNE(n_components=2, perplexity=perplexity, init="pca", random_state=model.seed)
    proj = tsne.fit_transform(feats_np)

    cmap = get_default_cmap(model.n_proto)
    colors = [tuple(c / 255 for c in cmap[int(lbl)]) for lbl in labels]

    fig, ax = plt.subplots(figsize=(6, 5), dpi=150)
    ax.scatter(proj[:, 0], proj[:, 1], c=colors, s=6, alpha=0.7, linewidths=0)
    ax.set_xlabel("t-SNE 1")
    ax.set_ylabel("t-SNE 2")
    ax.set_title(f"t-SNE — {Path(h5_path).stem}")
    out_path = _viz_dir(model) / f"tsne_{Path(h5_path).stem}.png"
    fig.savefig(str(out_path), bbox_inches="tight", dpi=150)
    _close_fig(fig)
    return out_path


def render_topk_grid(
    model: Model,
    dataset_features_dir: Path,
    dataset_wsi_dir: Path,
    per_proto: int = 3,
) -> Path:
    """Top-K representative patches per prototype, ACROSS the dataset.

    Cross-slide. One row per prototype × `per_proto` columns. Output:
    viz_cache/{model_id}/topk_grid.png

    Streams every h5 in the dataset features dir, maintains a heap of the
    best (score, slide_id, patch_idx, x, y, patch_size) per prototype, then
    crops the chosen patches from each slide's WSI at the end.
    """
    encoder = _load_panther_encoder(model)
    features_dir = Path(dataset_features_dir)
    if not features_dir.is_dir():
        raise VisualizationError(f"dataset_features_dir does not exist: {features_dir}")

    # heaps[k] = list of (score, tiebreak, slide_stem, x, y, patch_size)
    n_proto = model.n_proto
    heaps: list[list[tuple]] = [[] for _ in range(n_proto)]
    tiebreak = 0

    for h5_file in _features_files_iter(features_dir):
        try:
            coords, feats, patch_size = _load_h5(h5_file)
            _labels, qq, _probs = _compute_assignments(encoder, feats)
        except Exception as exc:  # noqa: BLE001 — one bad slide shouldn't kill the grid
            logger.warning("topk: failed to process %s: %s", h5_file.name, exc)
            continue

        for proto_idx in range(n_proto):
            scores = qq[:, proto_idx]
            for patch_idx in _topk_indices(scores, per_proto):
                score = float(scores[patch_idx])
                x = int(coords[patch_idx][0])
                y = int(coords[patch_idx][1])
                entry = (score, tiebreak, h5_file.stem, x, y, patch_size)
                tiebreak += 1
                if len(heaps[proto_idx]) < per_proto:
                    heapq.heappush(heaps[proto_idx], entry)
                else:
                    heapq.heappushpop(heaps[proto_idx], entry)

    # Build the composite grid image.
    from PIL import Image  # noqa: WPS433

    cell_px = TOPK_DEFAULT_THUMB_PX
    grid_w = cell_px * per_proto
    grid_h = cell_px * n_proto
    canvas = Image.new("RGB", (grid_w, grid_h), color=(245, 245, 245))

    # Cache opened WSIs so we don't re-open the same slide for every prototype.
    open_wsis: dict[str, object] = {}

    try:
        for proto_idx, heap in enumerate(heaps):
            ranked = sorted(heap, key=lambda e: -e[0])  # highest score → leftmost
            for col, (_score, _tb, slide_stem, x, y, patch_size) in enumerate(ranked):
                wsi_path = resolve_wsi_path(slide_stem, dataset_wsi_dir)
                if wsi_path is None:
                    continue
                if slide_stem not in open_wsis:
                    try:
                        open_wsis[slide_stem] = _open_wsi(wsi_path)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("topk: cannot open %s: %s", wsi_path, exc)
                        open_wsis[slide_stem] = None  # type: ignore[assignment]
                wsi = open_wsis[slide_stem]
                if wsi is None:
                    continue
                try:
                    crop = wsi.read_region(  # type: ignore[union-attr]
                        (x, y), 0, (patch_size, patch_size)
                    ).convert("RGB")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("topk: read_region failed for %s: %s", slide_stem, exc)
                    continue
                crop = crop.resize((cell_px, cell_px), Image.Resampling.BICUBIC)
                canvas.paste(crop, (col * cell_px, proto_idx * cell_px))
    finally:
        # OpenSlide handles need explicit close on some backends.
        for wsi in open_wsis.values():
            try:
                if wsi is not None:
                    wsi.close()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass

    out_path = _viz_dir(model) / "topk_grid.png"
    canvas.save(str(out_path), format="PNG", optimize=True)
    return out_path


def render_prototype_dictionary(
    model: Model,
    dataset_features_dir: Path,
    dataset_wsi_dir: Path,
    per_proto: int = 3,
) -> dict:
    """PANTHER-paper prototype dictionary — top patches + color per prototype.

    Cross-slide. The dictionary view (Section D of the Analysis page) replaces
    the single composite top-K grid: for each prototype C1..Cn we select the
    `per_proto` most-representative patches across the whole dataset (identical
    scoring to `render_topk_grid` — a per-prototype heap over the soft
    assignment score `qq[:, c]`), but instead of compositing one PNG we write
    each patch as its own image so the UI can lay them out per column and color
    each column with the prototype's assignment-map color.

    Output layout:
        viz_cache/{model_id}/section_d/proto_{index:02d}/patch_{rank:02d}.png

    Returns:
        {
          "per_proto": per_proto,
          "prototypes": [
            {"index": c, "color": "#rrggbb", "patches": ["<abs viz path>", ...]},
            ...  # ALL c in range(n_proto); empty `patches` for prototypes with
                 # no patches, so every column still renders.
          ],
        }
    """
    encoder = _load_panther_encoder(model)
    features_dir = Path(dataset_features_dir)
    if not features_dir.is_dir():
        raise VisualizationError(f"dataset_features_dir does not exist: {features_dir}")

    n_proto = model.n_proto

    # heaps[c] = top `per_proto` (score, tiebreak, slide_stem, x, y, patch_size).
    heaps: list[list[tuple]] = [[] for _ in range(n_proto)]
    tiebreak = 0

    for h5_file in _features_files_iter(features_dir):
        try:
            coords, feats, patch_size = _load_h5(h5_file)
            _labels, qq, _probs = _compute_assignments(encoder, feats)
        except Exception as exc:  # noqa: BLE001 — one bad slide shouldn't kill the dict
            logger.warning("proto_dict: failed to process %s: %s", h5_file.name, exc)
            continue

        for proto_idx in range(n_proto):
            scores = qq[:, proto_idx]
            for patch_idx in _topk_indices(scores, per_proto):
                score = float(scores[patch_idx])
                x = int(coords[patch_idx][0])
                y = int(coords[patch_idx][1])
                entry = (score, tiebreak, h5_file.stem, x, y, patch_size)
                tiebreak += 1
                if len(heaps[proto_idx]) < per_proto:
                    heapq.heappush(heaps[proto_idx], entry)
                else:
                    heapq.heappushpop(heaps[proto_idx], entry)

    # Prototype colors from the SAME cmap the assignment map / π_c bars use.
    _ensure_panther_on_syspath()
    from visualization.prototype_visualization_utils import get_default_cmap  # type: ignore[import-not-found]

    cmap = get_default_cmap(n_proto)

    from PIL import Image  # noqa: WPS433

    base_dir = _viz_dir(model, subdir="section_d")
    cell_px = TOPK_DEFAULT_THUMB_PX
    open_wsis: dict[str, object] = {}

    prototypes: list[dict] = []
    try:
        for proto_idx in range(n_proto):
            proto_dir = base_dir / f"proto_{proto_idx:02d}"
            proto_dir.mkdir(parents=True, exist_ok=True)

            ranked = sorted(heaps[proto_idx], key=lambda e: -e[0])  # best first
            patch_paths: list[str] = []
            for rank, (_score, _tb, slide_stem, x, y, patch_size) in enumerate(ranked):
                wsi_path = resolve_wsi_path(slide_stem, dataset_wsi_dir)
                if wsi_path is None:
                    continue
                if slide_stem not in open_wsis:
                    try:
                        open_wsis[slide_stem] = _open_wsi(wsi_path)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("proto_dict: cannot open %s: %s", wsi_path, exc)
                        open_wsis[slide_stem] = None  # type: ignore[assignment]
                wsi = open_wsis[slide_stem]
                if wsi is None:
                    continue
                try:
                    crop = wsi.read_region(  # type: ignore[union-attr]
                        (x, y), 0, (patch_size, patch_size)
                    ).convert("RGB")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("proto_dict: read_region failed for %s: %s", slide_stem, exc)
                    continue
                crop = crop.resize((cell_px, cell_px), Image.Resampling.BICUBIC)
                out_path = proto_dir / f"patch_{rank:02d}.png"
                crop.save(str(out_path), format="PNG", optimize=True)
                patch_paths.append(str(out_path))

            prototypes.append(
                {
                    "index": proto_idx,
                    "color": _cmap_to_hex(cmap, proto_idx),
                    "patches": patch_paths,
                }
            )
    finally:
        for wsi in open_wsis.values():
            try:
                if wsi is not None:
                    wsi.close()  # type: ignore[union-attr]
            except Exception:  # noqa: BLE001
                pass

    return {"per_proto": per_proto, "prototypes": prototypes}


def render_umap(model: Model, dataset_features_dir: Path) -> Path:
    """UMAP of patch features across the dataset, colored by cluster.

    Cross-slide. Output: viz_cache/{model_id}/umap.png

    Samples up to UMAP_MAX_PATCHES_PER_SLIDE per slide and caps at
    UMAP_MAX_TOTAL_PATCHES total. WSIs are not needed.
    """
    encoder = _load_panther_encoder(model)
    features_dir = Path(dataset_features_dir)
    if not features_dir.is_dir():
        raise VisualizationError(f"dataset_features_dir does not exist: {features_dir}")

    import numpy as np  # noqa: WPS433
    import torch  # noqa: WPS433

    rng = np.random.default_rng(model.seed)

    feats_chunks: list["np.ndarray"] = []  # type: ignore[name-defined]
    label_chunks: list["np.ndarray"] = []  # type: ignore[name-defined]
    total = 0

    for h5_file in _features_files_iter(features_dir):
        if total >= UMAP_MAX_TOTAL_PATCHES:
            break
        try:
            _coords, feats, _patch_size = _load_h5(h5_file)
            labels, _qq, _probs = _compute_assignments(encoder, feats)
        except Exception as exc:  # noqa: BLE001
            logger.warning("umap: failed to process %s: %s", h5_file.name, exc)
            continue
        n_avail = feats.shape[0]
        budget_remaining = UMAP_MAX_TOTAL_PATCHES - total
        take = min(UMAP_MAX_PATCHES_PER_SLIDE, n_avail, budget_remaining)
        if take <= 0:
            continue
        if take < n_avail:
            idxs = rng.choice(n_avail, size=take, replace=False)
            feats_chunks.append(feats[idxs].numpy())
            label_chunks.append(labels[idxs])
        else:
            feats_chunks.append(feats.numpy())
            label_chunks.append(labels)
        total += take

    if not feats_chunks:
        raise VisualizationError(
            f"No usable feature files found under {features_dir} for UMAP."
        )

    all_feats = np.concatenate(feats_chunks, axis=0)
    all_labels = np.concatenate(label_chunks, axis=0)

    # umap-learn is the canonical package; sklearn doesn't ship UMAP.
    import umap  # type: ignore[import-not-found]  # noqa: WPS433
    import matplotlib.pyplot as plt  # noqa: WPS433
    from visualization.prototype_visualization_utils import get_default_cmap  # type: ignore[import-not-found]

    reducer = umap.UMAP(n_neighbors=15, min_dist=0.1, random_state=model.seed)
    proj = reducer.fit_transform(all_feats)

    cmap = get_default_cmap(model.n_proto)
    colors = [tuple(c / 255 for c in cmap[int(lbl)]) for lbl in all_labels]

    fig, ax = plt.subplots(figsize=(7, 6), dpi=150)
    ax.scatter(proj[:, 0], proj[:, 1], c=colors, s=4, alpha=0.6, linewidths=0)
    ax.set_xlabel("UMAP 1")
    ax.set_ylabel("UMAP 2")
    ax.set_title(f"UMAP — {model.dataset_name} ({total:,} patches sampled)")
    out_path = _viz_dir(model) / "umap.png"
    fig.savefig(str(out_path), bbox_inches="tight", dpi=150)
    _close_fig(fig)
    return out_path


# ---------------------------------------------------------------------------
# Section C (on-tissue 2D-embedding map) renderer
# ---------------------------------------------------------------------------
#
# Bivariate (2D) colormap: a Stevens-style bilinear choropleth scheme. Each
# patch's two normalized UMAP coordinates (u, v) drive a bilinear blend of four
# corner colors, so the painted slide reads as a smooth 2D color field that the
# adjacent color-square legend decodes:
#     (u=0, v=0) light grey   → "neither axis high"
#     (u=1, v=0) muted red    → high UMAP-1 only
#     (u=0, v=1) muted teal    → high UMAP-2 only
#     (u=1, v=1) dark violet   → both axes high
# This keeps low values neutral and pushes each axis toward a distinct,
# perceptually separable hue, with the diagonal darkening so density is legible.

# Stevens bivariate corner colors (RGB 0-255), indexed [u][v].
_BIVARIATE_C00 = (232, 232, 232)  # low  UMAP-1, low  UMAP-2  (#e8e8e8)
_BIVARIATE_C10 = (200, 90, 90)    # high UMAP-1, low  UMAP-2  (#c85a5a)
_BIVARIATE_C01 = (100, 172, 190)  # low  UMAP-1, high UMAP-2  (#64acbe)
_BIVARIATE_C11 = (87, 66, 73)     # high UMAP-1, high UMAP-2  (#574249)

SECTION_C_DOWNSAMPLE = SECTION_A_DOWNSAMPLE  # hi-res / zoomable, like Section A


def section_c_dir(model: Model) -> Path:
    """The VIZ_CACHE_ROOT/{model_id}/section_c/ directory (created on demand)."""
    return _viz_dir(model, subdir="section_c")


def _norm01(arr):
    """Robustly normalize a 1D array to [0, 1] via 2nd/98th percentile clipping.

    Percentile clipping keeps a couple of UMAP outliers from compressing the
    whole color range into one corner. Degenerate (constant) inputs return all
    zeros.
    """
    import numpy as np  # noqa: WPS433

    a = np.asarray(arr, dtype=float)
    if a.size == 0:
        return a
    lo, hi = np.percentile(a, 2), np.percentile(a, 98)
    if hi <= lo:
        lo, hi = float(a.min()), float(a.max())
    if hi <= lo:
        return np.zeros_like(a)
    return np.clip((a - lo) / (hi - lo), 0.0, 1.0)


def _bivariate_colors(u, v):
    """Map normalized (u, v) arrays in [0,1] to RGB (0-255) via bilinear blend.

    Returns an (N, 3) int array. `u` drives the UMAP-1 axis (toward red), `v`
    the UMAP-2 axis (toward teal); the (1,1) corner darkens to violet.
    """
    import numpy as np  # noqa: WPS433

    c00 = np.asarray(_BIVARIATE_C00, dtype=float)
    c10 = np.asarray(_BIVARIATE_C10, dtype=float)
    c01 = np.asarray(_BIVARIATE_C01, dtype=float)
    c11 = np.asarray(_BIVARIATE_C11, dtype=float)

    u = np.clip(np.asarray(u, dtype=float), 0.0, 1.0)[:, None]
    v = np.clip(np.asarray(v, dtype=float), 0.0, 1.0)[:, None]

    rgb = (
        (1 - u) * (1 - v) * c00
        + u * (1 - v) * c10
        + (1 - u) * v * c01
        + u * v * c11
    )
    return np.clip(np.round(rgb), 0, 255).astype(int)


def _bivariate_legend_square(size: int = 128):
    """A `size`×`size` PIL image of the 2D colormap (UMAP-1 → x, UMAP-2 → y up)."""
    import numpy as np  # noqa: WPS433
    from PIL import Image  # noqa: WPS433

    xs = np.linspace(0.0, 1.0, size)
    ys = np.linspace(0.0, 1.0, size)
    uu, vv = np.meshgrid(xs, ys)
    rgb = _bivariate_colors(uu.ravel(), vv.ravel()).reshape(size, size, 3).astype("uint8")
    # Row 0 is the image top; flip so larger v (UMAP-2) sits higher visually.
    rgb = rgb[::-1, :, :]
    return Image.fromarray(rgb, "RGB")


def _build_bivariate_legend_panel(square_px: int = 128):
    """Color square + axis labels ('UMAP-1' x, 'UMAP-2' y) composited on white.

    Returned as a single RGB PIL image to paste into a corner of the on-tissue
    map so the bivariate colors are interpretable.
    """
    from PIL import Image, ImageDraw, ImageFont  # noqa: WPS433

    left_pad = 18   # room for the rotated y-axis label
    bottom_pad = 16  # room for the x-axis label
    border = 1

    sq = _bivariate_legend_square(square_px)
    panel = Image.new("RGB", (left_pad + square_px + 2 * border, square_px + 2 * border + bottom_pad), (255, 255, 255))
    panel.paste(sq, (left_pad + border, border))

    draw = ImageDraw.Draw(panel)
    try:
        font = ImageFont.load_default()
    except Exception:  # noqa: BLE001
        font = None
    # Thin frame around the swatch.
    draw.rectangle(
        [left_pad, 0, left_pad + square_px + 2 * border - 1, square_px + 2 * border - 1],
        outline=(40, 40, 40),
        width=border,
    )
    # X-axis label along the bottom of the swatch.
    draw.text(
        (left_pad + square_px // 2, square_px + 2 * border + 1),
        "UMAP-1 →",
        fill=(0, 0, 0),
        font=font,
        anchor="ma",
    )
    # Y-axis label, rotated, along the left edge of the swatch.
    ylabel = Image.new("RGB", (square_px, 12), (255, 255, 255))
    yd = ImageDraw.Draw(ylabel)
    yd.text((square_px // 2, 6), "UMAP-2 →", fill=(0, 0, 0), font=font, anchor="mm")
    ylabel = ylabel.rotate(90, expand=True)
    panel.paste(ylabel, (0, border + (square_px - ylabel.height) // 2))
    return panel


def render_umap_on_tissue(
    model: Model,
    h5_path: Path,
    wsi_path: Path,
    *,
    downsample_target: int = SECTION_C_DOWNSAMPLE,
    out_path: Path | None = None,
) -> Path:
    """On-tissue 2D-embedding map for ONE slide (Section C of the Analysis page).

    Per-slide companion to the dataset-wide abstract UMAP scatter (`render_umap`).
    For this slide's patches we fit a **2D UMAP**, normalize the two embedding
    axes to [0,1], and color each patch via a bivariate (2D) colormap, then paint
    those colors at each patch's spatial `coords`/`patch_size` location over the
    downsampled slide — reusing the same `visualize_categorical_heatmap` overlay
    machinery as the assignment map (same alpha/vis-level conventions, so it's
    zoomable). A small 2D-colormap legend (color square + 'UMAP-1'/'UMAP-2' axes)
    is composited into the bottom-right corner so the colors are interpretable.

    Output: viz_cache/{model_id}/section_c/umap_on_tissue_{slide_stem}.png

    `downsample_target` mirrors Section A (smaller = higher resolution).
    """
    _ensure_panther_on_syspath()
    import numpy as np  # noqa: WPS433
    from PIL import Image  # noqa: WPS433

    from visualization.prototype_visualization_utils import (  # type: ignore[import-not-found]
        visualize_categorical_heatmap,
    )

    coords, feats, patch_size = _load_h5(h5_path)
    feats_np = feats.detach().cpu().numpy()
    n_patches = feats_np.shape[0]
    if n_patches == 0:
        raise VisualizationError("No patches in features file for on-tissue UMAP.")

    # 2D UMAP of THIS slide's patches (heavy import stays lazy).
    import umap  # type: ignore[import-not-found]  # noqa: WPS433

    # n_neighbors must be < n_samples; clamp for small slides.
    n_neighbors = max(2, min(15, n_patches - 1))
    reducer = umap.UMAP(
        n_components=2, n_neighbors=n_neighbors, min_dist=0.1, random_state=model.seed
    )
    emb = reducer.fit_transform(feats_np)

    u = _norm01(emb[:, 0])
    v = _norm01(emb[:, 1])
    colors = _bivariate_colors(u, v)  # (n_patches, 3) int

    # Reuse the assignment-map overlay: give every patch its own "label" and a
    # color dict keyed by that label = its bivariate embedding color.
    labels = np.arange(n_patches)
    label2color = {int(i): tuple(int(c) for c in colors[i]) for i in range(n_patches)}

    wsi = _open_wsi(wsi_path)
    try:
        try:
            vis_level = wsi.get_best_level_for_downsample(downsample_target)
        except Exception:  # noqa: BLE001 — openslide quirks
            vis_level = wsi.level_count - 1

        img = visualize_categorical_heatmap(
            wsi,
            coords,
            labels,
            label2color_dict=label2color,
            vis_level=vis_level,
            patch_size=(patch_size, patch_size),
            alpha=0.4,
            verbose=False,
        ).convert("RGB")
        # Frame the tissue (same crop as Section A) before the legend goes on.
        w0, h0 = wsi.dimensions
        img = _crop_full_extent(img, w0, h0, _tissue_bbox_level0(coords, patch_size, w0, h0))
    finally:
        _close_wsi(wsi)

    # Composite the 2D-colormap legend into the bottom-right corner.
    try:
        legend = _build_bivariate_legend_panel()
        margin = max(8, img.width // 80)
        lx = img.width - legend.width - margin
        ly = img.height - legend.height - margin
        if lx >= 0 and ly >= 0:
            img.paste(legend, (lx, ly))
    except Exception as exc:  # noqa: BLE001 — a legend hiccup must not drop the map
        logger.warning("umap_on_tissue: legend composite failed: %s", exc)

    if out_path is None:
        out_path = section_c_dir(model) / f"umap_on_tissue_{Path(wsi_path).stem}.png"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(out_path), format="PNG", optimize=True)
    return out_path


# ---------------------------------------------------------------------------
# Section A (per-fold Analysis page) renderers
# ---------------------------------------------------------------------------


def section_a_dir(model: Model) -> Path:
    """The VIZ_CACHE_ROOT/{model_id}/section_a/ directory (created on demand)."""
    return _viz_dir(model, subdir="section_a")


def render_wsi_thumbnail(
    model: Model,
    wsi_path: Path,
    *,
    coords=None,
    patch_size: int | None = None,
) -> Path:
    """Downscaled H&E thumbnail of the whole slide, with a physical scale bar.

    Per-slide. Output: viz_cache/{model_id}/section_a/thumbnail_{slide_stem}.png

    Microns-per-pixel is read from openslide's MPP_X property. If it's missing
    the thumbnail is still rendered, just without the scale bar (we never fail
    on a missing MPP).

    When `coords` (+ `patch_size`) are supplied, the thumbnail is cropped to the
    tissue bounding box of those patches (with a small margin) so the default,
    un-zoomed view frames the tissue instead of a mostly-empty slide. The crop
    matches the assignment-map crop (same bbox math) so the two line up in the UI.
    """
    from PIL import Image  # noqa: WPS433,F401 — Resampling enum lives on Image

    wsi = _open_wsi(wsi_path)
    try:
        w0, h0 = wsi.dimensions
        longest = max(w0, h0)
        if longest > THUMB_MAX_PX:
            tw = max(1, round(w0 * THUMB_MAX_PX / longest))
            th = max(1, round(h0 * THUMB_MAX_PX / longest))
        else:
            tw, th = w0, h0
        thumb = wsi.get_thumbnail((tw, th)).convert("RGB")
        mpp = _wsi_mpp(wsi)
        # Per-pixel micron span of the full-extent thumbnail — capture BEFORE any
        # crop changes thumb.width (cropping preserves the per-pixel scale).
        um_per_pixel = mpp * (w0 / thumb.width) if mpp else None
        if coords is not None and patch_size:
            bbox = _tissue_bbox_level0(coords, patch_size, w0, h0)
            thumb = _crop_full_extent(thumb, w0, h0, bbox)
        if um_per_pixel:
            _draw_scale_bar(thumb, um_per_pixel)
    finally:
        _close_wsi(wsi)

    out_path = section_a_dir(model) / f"thumbnail_{Path(wsi_path).stem}.png"
    thumb.save(str(out_path), format="PNG", optimize=True)
    return out_path


def render_pi_c_barplot(model: Model, mixture_probs) -> Path:
    """Bar chart of the GMM mixture proportions π_c for one slide.

    Per-slide. Output: viz_cache/{model_id}/section_a/pi_c.png

    One bar per prototype, each bar colored with that prototype's color from
    PANTHER's `get_default_cmap(n_proto)` — the same cmap the assignment map
    uses, so colors line up across the panel. X labels are C1..Cn.
    """
    _ensure_panther_on_syspath()
    import numpy as np  # noqa: WPS433
    import matplotlib.pyplot as plt  # noqa: WPS433

    from visualization.prototype_visualization_utils import get_default_cmap  # type: ignore[import-not-found]

    n = model.n_proto
    probs = np.asarray(mixture_probs, dtype=float).ravel()
    if probs.shape[0] < n:
        probs = np.concatenate([probs, np.zeros(n - probs.shape[0])])
    probs = probs[:n]

    cmap = get_default_cmap(n)
    colors = [tuple(c / 255 for c in cmap[i][:3]) for i in range(n)]

    fig, ax = plt.subplots(figsize=(max(4.0, n * 0.45), 3.2), dpi=150)
    ax.bar(range(n), probs, color=colors, edgecolor="black", linewidth=0.4)
    ax.set_xticks(range(n))
    ax.set_xticklabels([f"C{i + 1}" for i in range(n)], fontsize=8)
    ax.set_ylabel(r"Proportion $\pi_c$")
    ax.set_xlabel("Prototype")
    ax.set_ylim(bottom=0)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)

    out_path = section_a_dir(model) / "pi_c.png"
    fig.savefig(str(out_path), bbox_inches="tight", dpi=150)
    _close_fig(fig)
    return out_path


def _select_roi_windows(coords, cluster_labels, patch_size: int, grid: int = ROI_GRID):
    """Deterministically rank non-overlapping grid×grid ROI windows.

    Tiles the level-0 plane into `span = grid * patch_size` squares aligned to
    the absolute coordinate origin, groups each patch into its tile, and ranks
    the occupied tiles by **occupancy first** (how many of the grid² cells hold
    an extracted patch), then prototype diversity, then density.

    Occupancy-first is what makes the colored tiling read like the PANTHER paper
    figure: the top window is one sampled from the *middle of dense tissue* where
    nearly every cell is on-tissue, so the grid fills with color instead of
    showing background gaps. (A diversity-first rank could otherwise land on a
    tissue-boundary window that's half background.) Among equally-full windows we
    still prefer the most prototype-diverse one, so the tiling stays multi-color.

    The non-overlapping tiling guarantees that consecutive `roi_index` values pick
    visibly different ROIs (no near-duplicate windows), and the ranking is fully
    determined by the cached `(coords, cluster_labels)` — so repick is
    reproducible.

    Returns a best-first list of `(x0, y0, w, h, member_indices)`.
    """
    import numpy as np  # noqa: WPS433
    from collections import defaultdict  # noqa: WPS433

    coords = np.asarray(coords)
    labels = np.asarray(cluster_labels)
    if coords.shape[0] == 0:
        return []

    # Tile on the TRUE level-0 patch pitch, not the stored patch_size — otherwise
    # a sub-base-mag extraction lands patches on only every Nth cell (gaps).
    cell = _coord_pitch(coords, patch_size)
    span = grid * cell
    tx = (coords[:, 0] // span).astype(np.int64)
    ty = (coords[:, 1] // span).astype(np.int64)

    members: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i in range(coords.shape[0]):
        members[(int(tx[i]), int(ty[i]))].append(i)

    ranked = []
    for (kx, ky), idxs in members.items():
        x0, y0 = kx * span, ky * span
        # Distinct (col, row) cells filled within this window — its "fullness".
        occupied = {
            ((int(coords[i][0]) - x0) // cell, (int(coords[i][1]) - y0) // cell)
            for i in idxs
        }
        occupancy = len(occupied)
        distinct = len({int(labels[i]) for i in idxs})
        ranked.append((occupancy, distinct, len(idxs), x0, y0, idxs))

    # Fullness first (paper-style packed tile), then diversity, then density;
    # deterministic spatial tiebreak keeps repick reproducible.
    ranked.sort(key=lambda w: (-w[0], -w[1], -w[2], w[3], w[4]))
    return [(int(x0), int(y0), span, span, idxs) for (_o, _d, _c, x0, y0, idxs) in ranked]


def render_roi_from_assignments(
    model: Model,
    coords,
    cluster_labels,
    patch_size: int,
    wsi_path: Path,
    roi_index: int = 0,
):
    """Render the raw + prototype-colored ROI for the `roi_index`-th window.

    Used by both the Section A render (with freshly computed assignments) and
    the repick endpoint (with assignments loaded from the .npz cache — no
    encoder run). Deterministic given `(model, slide, roi_index)`.

    Returns `(roi_raw_path, roi_colored_path, [x, y, w, h], used_index, num_windows)`.
    `used_index` is `roi_index % num_windows`, so the caller can wrap around.
    """
    _ensure_panther_on_syspath()
    import numpy as np  # noqa: WPS433
    from PIL import Image  # noqa: WPS433

    from visualization.prototype_visualization_utils import get_default_cmap  # type: ignore[import-not-found]

    windows = _select_roi_windows(coords, cluster_labels, patch_size, grid=ROI_GRID)
    if not windows:
        raise VisualizationError("No tissue patches available to pick an ROI from.")

    n = len(windows)
    idx = int(roi_index) % n
    x0, y0, w, h, member_idxs = windows[idx]

    coords = np.asarray(coords)
    labels = np.asarray(cluster_labels)
    cmap = get_default_cmap(model.n_proto)
    # Same true pitch the windows were tiled on, so every cell maps to a patch.
    cell = _coord_pitch(coords, patch_size)
    stem = Path(wsi_path).stem
    out_dir = section_a_dir(model)

    wsi = _open_wsi(wsi_path)
    try:
        # (a) Raw H&E crop of the whole ROI window, with a scale bar.
        try:
            raw = wsi.read_region((x0, y0), 0, (w, h)).convert("RGB")
        except Exception as exc:  # noqa: BLE001
            raise VisualizationError(f"read_region failed for ROI window: {exc}")
        raw_disp = _fit_max(raw, ROI_RAW_MAX_PX)
        mpp = _wsi_mpp(wsi)
        if mpp:
            _draw_scale_bar(raw_disp, mpp * (raw.width / raw_disp.width))
        raw_path = out_dir / f"roi_raw_{stem}_{idx}.png"
        raw_disp.save(str(raw_path), format="PNG", optimize=True)

        # (b) The same region with each ON-TISSUE patch tinted by its prototype
        #     color (same cmap as the assignment map). The raw ROI crop is the
        #     base layer, so cells where TRIDENT extracted no patch (background /
        #     fat / glass) still show real tissue context instead of a white gap.
        side = ROI_GRID * ROI_CELL_PX
        grid_img = raw.resize((side, side), Image.Resampling.BILINEAR).convert("RGB")
        for i in member_idxs:
            cx, cy = int(coords[i][0]), int(coords[i][1])
            col = (cx - x0) // cell
            row = (cy - y0) // cell
            if not (0 <= col < ROI_GRID and 0 <= row < ROI_GRID):
                continue
            box = (col * ROI_CELL_PX, row * ROI_CELL_PX, (col + 1) * ROI_CELL_PX, (row + 1) * ROI_CELL_PX)
            color = tuple(int(c) for c in cmap[int(labels[i])][:3])
            tint = Image.new("RGB", (ROI_CELL_PX, ROI_CELL_PX), color=color)
            blended = Image.blend(grid_img.crop(box), tint, ROI_TINT_ALPHA)
            grid_img.paste(blended, box)
        colored_path = out_dir / f"roi_colored_{stem}_{idx}.png"
        grid_img.save(str(colored_path), format="PNG", optimize=True)
    finally:
        _close_wsi(wsi)

    return raw_path, colored_path, [int(x0), int(y0), int(w), int(h)], idx, n


def render_roi(
    model: Model,
    h5_path: Path,
    wsi_path: Path,
    roi_index: int = 0,
) -> tuple[Path, Path, list[int]]:
    """Compute assignments for one slide, then render the `roi_index`-th ROI.

    Convenience wrapper around `render_roi_from_assignments` that runs the
    encoder. Returns `(roi_raw_path, roi_colored_path, [x, y, w, h])`.
    """
    encoder = _load_panther_encoder(model)
    coords, feats, patch_size = _load_h5(h5_path)
    cluster_labels, _qq, _probs = _compute_assignments(encoder, feats)
    raw, colored, bbox, _idx, _n = render_roi_from_assignments(
        model, coords, cluster_labels, patch_size, wsi_path, roi_index=roi_index
    )
    return raw, colored, bbox


# ---------------------------------------------------------------------------
# Section A repick cache (coords + labels for the chosen slide)
# ---------------------------------------------------------------------------


def save_section_a_cache(model: Model, slide_id: str, coords, cluster_labels, patch_size: int) -> None:
    """Persist the Section A slide's coords/labels so ROI repick can re-tile
    without re-running the encoder. Writes a small .npz + .json sidecar under
    section_a/."""
    import numpy as np  # noqa: WPS433

    d = section_a_dir(model)
    np.savez(
        str(d / "roi_cache.npz"),
        coords=np.asarray(coords),
        cluster_labels=np.asarray(cluster_labels),
    )
    (d / "roi_cache.json").write_text(
        json.dumps({"slide_id": slide_id, "patch_size": int(patch_size)})
    )


def load_section_a_cache(model: Model):
    """Load the cached Section A assignments.

    Returns `(slide_id, coords, cluster_labels, patch_size)`. Raises
    VisualizationError if the cache is missing (caller maps that to a 409).
    """
    import numpy as np  # noqa: WPS433

    d = section_a_dir(model)
    npz_path = d / "roi_cache.npz"
    meta_path = d / "roi_cache.json"
    if not npz_path.is_file() or not meta_path.is_file():
        raise VisualizationError(
            "Section A cache not found — render the model's visualizations first."
        )
    data = np.load(str(npz_path))
    meta = json.loads(meta_path.read_text())
    return meta["slide_id"], data["coords"], data["cluster_labels"], int(meta["patch_size"])


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def _topk_indices(scores, k: int):
    """Return indices of the k highest-scoring entries (no allocation if k>=n)."""
    import numpy as np  # noqa: WPS433

    arr = np.asarray(scores)
    k = min(k, arr.size)
    if k <= 0:
        return []
    if k == arr.size:
        return np.argsort(-arr).tolist()
    # argpartition for large arrays, then sort the small slice for ordering.
    part = np.argpartition(-arr, k - 1)[:k]
    return part[np.argsort(-arr[part])].tolist()


def _cmap_to_hex(cmap, index: int) -> str:
    """Convert a `get_default_cmap` entry (RGB 0-255 triple) to '#rrggbb'.

    Matches the colors the assignment map / π_c bars paint, so the UI can color
    each prototype column and label box to agree with the heatmap.
    """
    rgb = cmap[int(index)][:3]
    r, g, b = (max(0, min(255, int(round(float(c))))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _close_fig(fig) -> None:
    import matplotlib.pyplot as plt  # noqa: WPS433

    plt.close(fig)


def _close_wsi(wsi) -> None:
    try:
        wsi.close()
    except Exception:  # noqa: BLE001 — some backends lack/raise on close
        pass


def _wsi_mpp(wsi) -> float | None:
    """Microns-per-pixel at level 0 from openslide's MPP_X property, or None."""
    import openslide  # noqa: WPS433

    try:
        raw = wsi.properties.get(openslide.PROPERTY_NAME_MPP_X)
        return float(raw) if raw else None
    except (TypeError, ValueError):
        return None


def _fit_max(img, max_px: int):
    """Downscale a PIL image so its longest side is <= max_px (no upscaling)."""
    from PIL import Image  # noqa: WPS433

    longest = max(img.width, img.height)
    if longest <= max_px:
        return img
    scale = max_px / longest
    return img.resize(
        (max(1, round(img.width * scale)), max(1, round(img.height * scale))),
        Image.Resampling.BILINEAR,
    )


# Fraction of the tissue bbox added as breathing room on each side when cropping
# a whole-slide render down to the tissue. Small enough to fill the frame with
# tissue, large enough that edge patches aren't flush against the border.
TISSUE_CROP_MARGIN = 0.04
# Percentile clip for the tissue bbox — trims a few stray outlier patches (pen
# marks, dust, detached control tissue) so the crop frames the main tissue mass
# instead of being stretched across the whole slide by one speck in a corner.
TISSUE_BBOX_PCTILE = 1.0


def _coord_pitch(coords, fallback: int) -> int:
    """The level-0 grid pitch of the extracted patches, derived from the coords.

    TRIDENT stores patch top-left corners at level-0 pixels, but the stored
    `patch_size` attr is the patch side at the *extraction* magnification — which
    can be half (or a quarter) of the level-0 pitch when patches are extracted
    below the slide's base magnification. Tiling on the stored `patch_size`
    therefore lands a colored cell on only every Nth patch, leaving gaps.

    The *most common* positive step between adjacent unique x/y coordinates is
    the true pitch (one patch to its neighbor), regardless of magnification — so
    we use that for tiling and read_region. The mode (rather than the min) is
    robust to a few off-grid artifact patches, which would otherwise inject tiny
    spurious steps and underestimate the pitch. Falls back to `patch_size` when
    there aren't enough coords to measure a step.
    """
    import numpy as np  # noqa: WPS433

    c = np.asarray(coords)
    if c.shape[0] < 2:
        return int(fallback)
    steps = []
    for axis in (0, 1):
        u = np.unique(c[:, axis].astype(np.int64))
        if u.size > 1:
            d = np.diff(u)
            steps.append(d[d > 0])
    if not steps:
        return int(fallback)
    allsteps = np.concatenate(steps)
    if allsteps.size == 0:
        return int(fallback)
    vals, counts = np.unique(allsteps, return_counts=True)
    return int(vals[int(np.argmax(counts))])


def _tissue_bbox_level0(coords, patch_size: int, w0: int, h0: int, margin: float = TISSUE_CROP_MARGIN):
    """Robust level-0 bounding box (x0, y0, x1, y1) of the main tissue mass.

    Uses a percentile clip (TISSUE_BBOX_PCTILE / 100 - that) rather than raw
    min/max so a handful of stray artifact patches in the slide corners don't
    stretch the box across mostly-empty glass. The high edge is extended by one
    patch pitch so the last row/column of patches is fully inside. Clamped to the
    slide dimensions; falls back to the full slide when there are no coords.
    """
    import numpy as np  # noqa: WPS433

    c = np.asarray(coords)
    if c.shape[0] == 0:
        return 0, 0, int(w0), int(h0)
    pitch = _coord_pitch(coords, patch_size)
    lo, hi = TISSUE_BBOX_PCTILE, 100.0 - TISSUE_BBOX_PCTILE
    x0 = int(np.percentile(c[:, 0], lo))
    y0 = int(np.percentile(c[:, 1], lo))
    x1 = int(np.percentile(c[:, 0], hi)) + pitch
    y1 = int(np.percentile(c[:, 1], hi)) + pitch
    mx = int((x1 - x0) * margin)
    my = int((y1 - y0) * margin)
    x0 = max(0, x0 - mx)
    y0 = max(0, y0 - my)
    x1 = min(int(w0), x1 + mx)
    y1 = min(int(h0), y1 + my)
    return x0, y0, x1, y1


def _crop_full_extent(img, w0: int, h0: int, bbox_l0):
    """Crop a full-slide-extent PIL image to a level-0 bbox.

    `img` is a render whose pixel grid spans the entire level-0 plane (a
    thumbnail or a `visualize_categorical_heatmap` overlay), so its width maps to
    `w0`. We scale the level-0 bbox into the image's own pixel space and crop.
    """
    sx = img.width / float(w0)
    sy = img.height / float(h0)
    x0, y0, x1, y1 = bbox_l0
    box = (
        int(x0 * sx),
        int(y0 * sy),
        max(int(x0 * sx) + 1, int(x1 * sx)),
        max(int(y0 * sy) + 1, int(y1 * sy)),
    )
    return img.crop(box)


def _nice_scale_length(target_um: float) -> float:
    """Snap a target micron length to the nearest 'nice' 1/2/5×10ⁿ value <= target."""
    if target_um <= 0:
        return 0.0
    exp = math.floor(math.log10(target_um))
    base = 10 ** exp
    for mult in (5, 2, 1):
        if mult * base <= target_um:
            return float(mult * base)
    return float(base)


def _format_scale_label(um: float) -> str:
    if um >= 1000:
        return f"{um / 1000:g} mm"
    return f"{um:g} µm"


def _draw_scale_bar(img, um_per_pixel: float, *, frac: float = 0.22) -> None:
    """Draw a physical scale bar (bottom-left) onto a PIL RGB image in place.

    `um_per_pixel` is the microns spanned by one pixel of `img`. The bar length
    is snapped to a 'nice' value (~`frac` of the image width). No-op if the
    image is too small to host a sensible bar.
    """
    from PIL import ImageDraw, ImageFont  # noqa: WPS433

    if not um_per_pixel or um_per_pixel <= 0:
        return
    target_um = um_per_pixel * img.width * frac
    bar_um = _nice_scale_length(target_um)
    if bar_um <= 0:
        return
    bar_px = bar_um / um_per_pixel
    if bar_px < 8 or bar_px > img.width * 0.9:
        return

    draw = ImageDraw.Draw(img)
    margin = max(6, img.width // 40)
    bar_h = max(3, img.height // 120)
    x1 = margin
    x2 = margin + bar_px
    y = img.height - margin
    # Dark outline then white fill so the bar reads on light or dark tissue.
    draw.rectangle([x1 - 1, y - bar_h - 1, x2 + 1, y + 1], fill=(0, 0, 0))
    draw.rectangle([x1, y - bar_h, x2, y], fill=(255, 255, 255))

    label = _format_scale_label(bar_um)
    try:
        font = ImageFont.load_default()
    except Exception:  # noqa: BLE001
        font = None
    text_y = y - bar_h - 2
    # Cheap text outline: draw black offsets, then white on top.
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
        draw.text((x1 + dx, text_y - 11 + dy), label, fill=(0, 0, 0), font=font, anchor="lb")
    draw.text((x1, text_y - 11), label, fill=(255, 255, 255), font=font, anchor="lb")


# ---------------------------------------------------------------------------
# Dataset WSI dir resolution (used by post_train_viz)
# ---------------------------------------------------------------------------


def resolve_dataset_wsi_dir(model: Model, db) -> Path | None:
    """Look up the TridentRun that produced this model's features and return
    its wsi_dir. None if no link is recorded — top-K and per-slide renders
    that need WSIs should skip in that case.
    """
    if not model.trident_run_id:
        return None
    run = db.get(TridentRun, model.trident_run_id)
    if run is None or not run.wsi_dir:
        return None
    p = Path(run.wsi_dir)
    return p if p.is_dir() else None


# ---------------------------------------------------------------------------
# Section B — validation-slide prototype consistency
# ---------------------------------------------------------------------------

TRAIN_USAGE_SAMPLE_CAP = 50  # cap train slides scanned for the usage average


def render_validation_consistency(model: Model, features_dir: Path) -> dict:
    """Section B — how the fold's prototypes hold up on its held-out validation slides.

    The heaviest renderer: runs the PANTHER encoder over every validation slide
    and a deterministic sample of training slides (capped at TRAIN_USAGE_SAMPLE_CAP).
    Produces two PNGs under viz_cache/{model_id}/section_b/:

      - violin.png: per prototype, the distribution of cosine similarity between
        each validation patch assigned to that prototype and the prototype's
        trained center, colored by prototype, with the per-prototype patch count
        annotated. Tight + high → the prototype generalizes; wide/low → it drifts.
      - usage.png: train-vs-val prototype usage — the mean GMM mixture weight π_c
        per prototype across each set (grouped bars).

    Returns {"violin", "usage", "n_val_slides", "n_train_slides"}. Raises
    VisualizationError when the fold has no usable validation slides (the
    post_train_viz handler treats that as a graceful skip, not a failure).
    """
    import random  # noqa: WPS433

    import matplotlib.pyplot as plt  # noqa: WPS433
    import numpy as np  # noqa: WPS433

    from app.services.preview import read_slide_ids_from_csv
    from visualization.prototype_visualization_utils import get_default_cmap  # type: ignore[import-not-found]

    val_ids = read_slide_ids_from_csv(model.split_dir_abs, "val.csv")
    if not val_ids:
        raise VisualizationError("fold has no validation slides (val.csv missing/empty)")
    train_ids = read_slide_ids_from_csv(model.split_dir_abs, "train.csv")

    n_proto = model.n_proto
    centers = _load_prototype_centers(model)  # (n_proto, dim)
    centers_norm = centers / (np.linalg.norm(centers, axis=1, keepdims=True) + 1e-8)
    encoder = _load_panther_encoder(model)

    # --- Validation pass: per-prototype cosine-sim distribution + usage ------
    val_sims: list[list[float]] = [[] for _ in range(n_proto)]
    val_usage = np.zeros(n_proto, dtype=np.float64)
    n_val_used = 0
    for sid in val_ids:
        h5 = features_dir / f"{sid}.h5"
        if not h5.is_file():
            continue
        _coords, feats, _ps = _load_h5(h5)
        labels, _qq, mix = _compute_assignments(encoder, feats)
        feats_np = feats.detach().cpu().numpy()
        feats_norm = feats_np / (np.linalg.norm(feats_np, axis=1, keepdims=True) + 1e-8)
        # cosine of each patch to the center it was assigned to
        sims = np.einsum("ij,ij->i", feats_norm, centers_norm[labels])
        for c in range(n_proto):
            m = labels == c
            if m.any():
                val_sims[c].extend(sims[m].astype(float).tolist())
        val_usage += np.asarray(mix, dtype=np.float64)
        n_val_used += 1
    if n_val_used == 0:
        raise VisualizationError("no validation slide had a matching .h5 feature file")
    val_usage /= n_val_used

    # --- Train usage (sampled, deterministic) -------------------------------
    sampled = train_ids
    if len(train_ids) > TRAIN_USAGE_SAMPLE_CAP:
        sampled = sorted(random.Random(f"{model.id}:section_b").sample(train_ids, TRAIN_USAGE_SAMPLE_CAP))
    train_usage = np.zeros(n_proto, dtype=np.float64)
    n_train_used = 0
    for sid in sampled:
        h5 = features_dir / f"{sid}.h5"
        if not h5.is_file():
            continue
        _coords, feats, _ps = _load_h5(h5)
        _labels, _qq, mix = _compute_assignments(encoder, feats)
        train_usage += np.asarray(mix, dtype=np.float64)
        n_train_used += 1
    if n_train_used:
        train_usage /= n_train_used

    cmap = get_default_cmap(n_proto)
    proto_colors = [tuple(c / 255 for c in cmap[i]) for i in range(n_proto)]
    xticks = list(range(1, n_proto + 1))
    xlabels = [f"C{i + 1}" for i in range(n_proto)]
    rot = 45 if n_proto > 12 else 0
    fig_w = max(6.0, n_proto * 0.6)

    out_dir = _viz_dir(model, "section_b")

    # --- violin.png ---------------------------------------------------------
    counts = [len(val_sims[c]) for c in range(n_proto)]
    positions = [c + 1 for c in range(n_proto) if counts[c] > 0]
    datasets = [val_sims[c] for c in range(n_proto) if counts[c] > 0]

    fig, ax = plt.subplots(figsize=(fig_w, 4.5), dpi=120)
    if datasets:
        parts = ax.violinplot(datasets, positions=positions, showmedians=True, widths=0.8)
        for body, pos in zip(parts["bodies"], positions):
            body.set_facecolor(proto_colors[pos - 1])
            body.set_edgecolor("#333333")
            body.set_alpha(0.85)
        for key in ("cbars", "cmins", "cmaxes", "cmedians"):
            if key in parts:
                parts[key].set_edgecolor("#333333")
                parts[key].set_linewidth(1.0)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xlabels, rotation=rot, fontsize=8)
    ax.set_ylabel("cosine sim to prototype center")
    ax.set_title(f"Validation patch → prototype consistency ({n_val_used} val slides)")
    ax.set_ylim(-0.05, 1.08)
    for c in range(n_proto):
        ax.text(c + 1, 1.03, f"n={counts[c]}", ha="center", va="bottom",
                fontsize=6, rotation=90, color="#555555")
    ax.grid(axis="y", alpha=0.2)
    fig.tight_layout()
    violin_path = out_dir / "violin.png"
    fig.savefig(violin_path)
    plt.close(fig)

    # --- usage.png ----------------------------------------------------------
    fig2, ax2 = plt.subplots(figsize=(fig_w, 4.0), dpi=120)
    xs = np.arange(n_proto)
    w = 0.4
    ax2.bar(xs - w / 2, train_usage, w, label=f"train (n={n_train_used})",
            color="#9ecae1", edgecolor="#333333", linewidth=0.4)
    ax2.bar(xs + w / 2, val_usage, w, label=f"val (n={n_val_used})",
            color="#fdae6b", edgecolor="#333333", linewidth=0.4)
    ax2.set_xticks(xs)
    ax2.set_xticklabels(xlabels, rotation=rot, fontsize=8)
    ax2.set_ylabel(r"Proportion $\pi_c$")
    ax2.set_title("Prototype usage — train vs validation")
    ax2.legend(fontsize=8)
    ax2.grid(axis="y", alpha=0.2)
    fig2.tight_layout()
    usage_path = out_dir / "usage.png"
    fig2.savefig(usage_path)
    plt.close(fig2)

    return {
        "violin": str(violin_path),
        "usage": str(usage_path),
        "n_val_slides": n_val_used,
        "n_train_slides": n_train_used,
    }
