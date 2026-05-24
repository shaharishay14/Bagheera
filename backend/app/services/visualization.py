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
    """Find a WSI file under wsi_dir whose stem matches `slide_id`.

    Returns None if no match — callers use this to skip slides with missing
    WSIs gracefully (per assumption #6).
    """
    base = Path(wsi_dir)
    if not base.is_dir():
        return None
    # Cheap direct hits first.
    for ext in WSI_EXTENSIONS:
        candidate = base / f"{slide_id}{ext}"
        if candidate.is_file():
            return candidate
    # Fallback: scan one level deep for variant naming.
    for child in base.iterdir():
        if child.is_file() and child.stem == slide_id and child.suffix.lower() in WSI_EXTENSIONS:
            return child
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


def render_assignment_heatmap(model: Model, h5_path: Path, wsi_path: Path) -> Path:
    """Categorical assignment heatmap painted over the WSI thumbnail.

    Per-slide. Output: viz_cache/{model_id}/heatmap_{slide_stem}.png
    """
    _ensure_panther_on_syspath()
    from visualization.prototype_visualization_utils import (  # type: ignore[import-not-found]
        get_default_cmap,
        visualize_categorical_heatmap,
    )

    encoder = _load_panther_encoder(model)
    coords, feats, patch_size = _load_h5(h5_path)
    cluster_labels, _qq, _probs = _compute_assignments(encoder, feats)

    wsi = _open_wsi(wsi_path)
    cmap = get_default_cmap(model.n_proto)
    # Match the notebook's choice: downsample 128× target, fall back to deepest
    # level if the slide is too small.
    try:
        vis_level = wsi.get_best_level_for_downsample(128)
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

    out_path = _viz_dir(model) / f"heatmap_{Path(h5_path).stem}.png"
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


def _close_fig(fig) -> None:
    import matplotlib.pyplot as plt  # noqa: WPS433

    plt.close(fig)


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
