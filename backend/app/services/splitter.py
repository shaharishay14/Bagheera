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


def _write_split(path: Path, header: list[str] | None, rows: list[list[str]]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        if header is not None:
            writer.writerow(header)
        writer.writerows(rows)
