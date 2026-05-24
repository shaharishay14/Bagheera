"""Shared preview-slide picking.

Both the `/api/models/{id}/shuffle-preview` route and the `post_train_viz`
worker handler need to pick 3 deterministic slide IDs from a fold's
train.csv. Centralized here so the two callers stay in lockstep.
"""
from __future__ import annotations

import csv
import random
from pathlib import Path

from app.db.models import Model

PREVIEW_SLIDE_COUNT = 3
SLIDE_ID_COLUMNS = {"slide_id", "case_id", "slide", "id"}


def read_slide_ids_from_train_csv(split_dir_abs: str) -> list[str]:
    """Read the slide-identifier column out of `{split_dir_abs}/train.csv`.

    Returns [] on any error so callers can degrade gracefully (the UI will
    fall back to placeholder thumbnails). Tolerates a missing header or an
    unconventional first-column name.
    """
    try:
        csv_path = Path(split_dir_abs) / "train.csv"
        if not csv_path.is_file():
            return []
        with csv_path.open(newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if header is None:
                return []
            id_idx = 0
            for i, col in enumerate(header):
                if col.strip().lower() in SLIDE_ID_COLUMNS:
                    id_idx = i
                    break
            return [row[id_idx] for row in reader if len(row) > id_idx and row[id_idx]]
    except OSError:
        return []


def pick_preview_slides(model: Model, count: int = PREVIEW_SLIDE_COUNT) -> list[str]:
    """Deterministic per-model selection: same model + same train.csv → same IDs."""
    pool = read_slide_ids_from_train_csv(model.split_dir_abs)
    if not pool:
        return []
    rng = random.Random(f"{model.id}:{model.seed}:{model.fold_index}")
    rng.shuffle(pool)
    return pool[:count]
