"""Stratified-by-chunk train/val/test splitter for PANTHER inputs."""
from __future__ import annotations

import csv
import random
import shutil
from dataclasses import dataclass
from pathlib import Path


class SplitterError(ValueError):
    """User-facing splitter problem (translated to HTTP 400)."""


@dataclass(frozen=True)
class SplitResult:
    train: int
    val: int
    test: int
    unused: int
    total: int

    def as_dict(self) -> dict[str, int]:
        return {
            "train": self.train,
            "val": self.val,
            "test": self.test,
            "unused": self.unused,
            "total": self.total,
        }


def split_dataset(
    source_csv: Path,
    output_dir: Path,
    train_pct: float,
    val_pct: float,
    test_pct: float,
    n_chunks: int,
    seed: int,
) -> SplitResult:
    if train_pct + val_pct + test_pct > 100:
        raise SplitterError("train_pct + val_pct + test_pct cannot exceed 100.")
    if n_chunks < 2:
        raise SplitterError("n_chunks must be >= 2.")

    try:
        with source_csv.open(newline="") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            rows = list(reader)
    except OSError as exc:
        raise SplitterError(f"Failed to read source CSV: {exc}")

    total = len(rows)
    if total < n_chunks:
        raise SplitterError(
            f"Source CSV has {total} data rows; need at least {n_chunks} to form {n_chunks} chunks."
        )

    random.Random(seed).shuffle(rows)

    # Roughly-equal chunks: the first `rem` chunks get one extra row.
    base, rem = divmod(total, n_chunks)
    chunks: list[list[list[str]]] = []
    start = 0
    for i in range(n_chunks):
        size = base + (1 if i < rem else 0)
        chunks.append(rows[start : start + size])
        start += size

    train_rows: list[list[str]] = []
    val_rows: list[list[str]] = []
    test_rows: list[list[str]] = []
    unused = 0

    for chunk in chunks:
        size = len(chunk)
        n_train = round(size * train_pct / 100)
        n_val = round(size * val_pct / 100)
        n_test = round(size * test_pct / 100)
        # Clamp boundaries so cumulative slicing never overruns the chunk.
        b1 = min(n_train, size)
        b2 = min(b1 + n_val, size)
        b3 = min(b2 + n_test, size)
        train_rows.extend(chunk[:b1])
        val_rows.extend(chunk[b1:b2])
        test_rows.extend(chunk[b2:b3])
        unused += size - b3

    output_dir.mkdir(parents=True, exist_ok=True)
    _write_split(output_dir / "train.csv", header, train_rows)
    _write_split(output_dir / "val.csv", header, val_rows)
    _write_split(output_dir / "test.csv", header, test_rows)

    return SplitResult(
        train=len(train_rows),
        val=len(val_rows),
        test=len(test_rows),
        unused=unused,
        total=total,
    )


def _write_split(path: Path, header: list[str] | None, rows: list[list[str]]) -> None:
    if path.exists():
        # Preserve the previous run's split so a re-run never silently destroys data.
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        if header is not None:
            writer.writerow(header)
        writer.writerows(rows)
