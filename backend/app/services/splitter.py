"""K-fold cross-validation splitter for PANTHER inputs.

For K folds, each fold i uses:
    test  = chunk[i]
    val   = chunk[(i+1) % K]
    train = concat of the K-2 remaining chunks

Every source row appears in `test` exactly once across the K folds.
"""
from __future__ import annotations

import csv
import json
import random
import secrets
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Reuse the same set the preview/inspection layers use so detection stays in lockstep.
from app.services.preview import SLIDE_ID_COLUMNS

_TIF_SUFFIXES = (".tif", ".tiff")


class SplitterError(ValueError):
    """User-facing splitter problem (translated to HTTP 400)."""


@dataclass(frozen=True)
class FoldCounts:
    train: int
    val: int
    test: int

    def as_dict(self) -> dict[str, int]:
        return {"train": self.train, "val": self.val, "test": self.test}


@dataclass(frozen=True)
class KFoldSplitInfo:
    split_name: str
    abs_path: Path
    k: int
    seed: int
    total_rows: int
    per_fold_counts: list[FoldCounts]

    def per_fold_dicts(self) -> list[dict[str, int]]:
        return [f.as_dict() for f in self.per_fold_counts]


def _rand_suffix() -> str:
    return secrets.token_hex(4)


def _strip_tif_suffix(value: str) -> str:
    """Strip a trailing .tif/.tiff (case-insensitive) from a slide-id value."""
    lowered = value.lower()
    for suffix in _TIF_SUFFIXES:
        if lowered.endswith(suffix):
            return value[: -len(suffix)]
    return value


def create_kfold_split(
    dataset_name: str,
    source_csv: Path,
    output_root: Path,
    k: int,
    seed: int,
) -> KFoldSplitInfo:
    """Produce K folds under {output_root}/{split_name}/k={i}/{train,val,test}.csv.

    `output_root` should be the dataset-level dir (e.g. .../datasets_splits/{dataset_name}/).
    Returns metadata; also writes a metadata.json next to the K fold dirs.
    """
    if k < 2:
        raise SplitterError("k must be >= 2.")

    try:
        with source_csv.open(newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            rows = list(reader)
    except OSError as exc:
        raise SplitterError(f"Failed to read source CSV: {exc}")

    # Locate the slide-id column (case-insensitive) so we can normalize its
    # values. The /data mount is read-only, so we transform the GENERATED split
    # CSVs only, never the source.
    slide_id_idx: int | None = None
    slide_id_column: str | None = None
    if header is not None:
        for i, col in enumerate(header):
            if col.strip().lower() in SLIDE_ID_COLUMNS:
                slide_id_idx = i
                slide_id_column = col
                break
    if slide_id_idx is None:
        expected = ", ".join(sorted(SLIDE_ID_COLUMNS))
        raise SplitterError(
            f"Source CSV has no slide_id column (expected one of: {expected})"
        )

    # Strip a trailing .tif/.tiff from each slide-id value before any writes.
    slide_id_normalized = False
    for row in rows:
        if len(row) > slide_id_idx:
            original = row[slide_id_idx]
            stripped = _strip_tif_suffix(original)
            if stripped != original:
                row[slide_id_idx] = stripped
                slide_id_normalized = True

    total = len(rows)
    if total < k:
        raise SplitterError(
            f"Source CSV has {total} data rows; need at least {k} to form {k} folds."
        )

    random.Random(seed).shuffle(rows)

    # Roughly-equal chunks: the first `rem` chunks get one extra row.
    base, rem = divmod(total, k)
    chunks: list[list[list[str]]] = []
    start = 0
    for i in range(k):
        size = base + (1 if i < rem else 0)
        chunks.append(rows[start : start + size])
        start += size

    split_name = f"kfold_k_{k}_seed_{seed}_{_rand_suffix()}"
    split_root = output_root / split_name
    split_root.mkdir(parents=True, exist_ok=True)

    per_fold: list[FoldCounts] = []
    for i in range(k):
        test_rows = chunks[i]
        val_rows = chunks[(i + 1) % k]
        train_rows: list[list[str]] = []
        for j, chunk in enumerate(chunks):
            if j == i or j == (i + 1) % k:
                continue
            train_rows.extend(chunk)

        fold_dir = split_root / f"k={i}"
        fold_dir.mkdir(parents=True, exist_ok=True)
        _write_split(fold_dir / "train.csv", header, train_rows)
        _write_split(fold_dir / "val.csv", header, val_rows)
        _write_split(fold_dir / "test.csv", header, test_rows)

        per_fold.append(
            FoldCounts(train=len(train_rows), val=len(val_rows), test=len(test_rows))
        )

    # Invariant: every source row appears in exactly one test set across all K folds.
    # (Trivially true by construction — chunks partition rows, and test = chunk[i].)
    test_total = sum(f.test for f in per_fold)
    if test_total != total:
        raise SplitterError(
            f"Internal invariant violated: union of test sets has {test_total} rows, expected {total}."
        )

    metadata = {
        "dataset_name": dataset_name,
        "source_csv": str(source_csv),
        "k": k,
        "seed": seed,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "per_fold_counts": [f.as_dict() for f in per_fold],
        "total_rows": total,
        "slide_id_column": slide_id_column,
        "slide_id_normalized": slide_id_normalized,
    }
    (split_root / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return KFoldSplitInfo(
        split_name=split_name,
        abs_path=split_root,
        k=k,
        seed=seed,
        total_rows=total,
        per_fold_counts=per_fold,
    )


def _read_normalized_rows(
    source_csv: Path,
) -> tuple[list[str] | None, list[list[str]], str | None, bool]:
    """Read a source CSV, detect its slide-id column, strip .tif/.tiff from that
    column's values (never touching the source file), and return
    ``(header, rows, slide_id_column, slide_id_normalized)``.

    Shared entry point for the single-split builder; mirrors the detection +
    normalization ``create_kfold_split`` does inline (left untouched by design).
    """
    try:
        with source_csv.open(newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            rows = list(reader)
    except OSError as exc:
        raise SplitterError(f"Failed to read source CSV: {exc}")

    slide_id_idx: int | None = None
    slide_id_column: str | None = None
    if header is not None:
        for i, col in enumerate(header):
            if col.strip().lower() in SLIDE_ID_COLUMNS:
                slide_id_idx = i
                slide_id_column = col
                break
    if slide_id_idx is None:
        expected = ", ".join(sorted(SLIDE_ID_COLUMNS))
        raise SplitterError(
            f"Source CSV has no slide_id column (expected one of: {expected})"
        )

    slide_id_normalized = False
    for row in rows:
        if len(row) > slide_id_idx:
            original = row[slide_id_idx]
            stripped = _strip_tif_suffix(original)
            if stripped != original:
                row[slide_id_idx] = stripped
                slide_id_normalized = True

    return header, rows, slide_id_column, slide_id_normalized


def create_single_split(
    dataset_name: str,
    source_csv: Path,
    output_root: Path,
    seed: int,
) -> KFoldSplitInfo:
    """Produce a single "100% train" fold under {output_root}/{split_name}/k=0/.

    PANTHER only ever reads train.csv, so a standalone run puts EVERY row in
    train.csv and writes header-only val.csv/test.csv so any downstream glob
    still finds them. Returns the same ``KFoldSplitInfo`` shape as
    ``create_kfold_split`` with ``k == 1``. Also writes a metadata.json marked
    ``kind: "single"`` next to the fold dir. ``seed`` is retained only for
    provenance/naming (no shuffling is required when all rows go to train).
    """
    header, rows, slide_id_column, slide_id_normalized = _read_normalized_rows(source_csv)

    total = len(rows)
    if total < 1:
        raise SplitterError("Source CSV has no data rows.")

    split_name = f"alltrain_seed_{seed}_{_rand_suffix()}"
    split_root = output_root / split_name
    fold_dir = split_root / "k=0"
    fold_dir.mkdir(parents=True, exist_ok=True)

    _write_split(fold_dir / "train.csv", header, rows)
    _write_split(fold_dir / "val.csv", header, [])
    _write_split(fold_dir / "test.csv", header, [])

    per_fold = [FoldCounts(train=total, val=0, test=0)]

    metadata = {
        "dataset_name": dataset_name,
        "source_csv": str(source_csv),
        "kind": "single",
        "k": 1,
        "seed": seed,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "per_fold_counts": [f.as_dict() for f in per_fold],
        "total_rows": total,
        "slide_id_column": slide_id_column,
        "slide_id_normalized": slide_id_normalized,
    }
    (split_root / "metadata.json").write_text(json.dumps(metadata, indent=2))

    return KFoldSplitInfo(
        split_name=split_name,
        abs_path=split_root,
        k=1,
        seed=seed,
        total_rows=total,
        per_fold_counts=per_fold,
    )


def _write_split(path: Path, header: list[str] | None, rows: list[list[str]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        if header is not None:
            writer.writerow(header)
        writer.writerows(rows)
