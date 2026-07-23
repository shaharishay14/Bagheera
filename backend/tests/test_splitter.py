"""Tests for the single ("100% train") splitter."""
from __future__ import annotations

import csv
import json
import re

import pytest

from app.services.splitter import SplitterError, create_single_split


def _write_source_csv(path, n_rows, *, slide_col="slide_id", tif=False):
    header = [slide_col, "label"]
    rows = []
    for i in range(n_rows):
        sid = f"slide_{i}.tif" if tif else f"slide_{i}"
        rows.append([sid, "pos" if i % 2 == 0 else "neg"])
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    return header


def _read_rows(path):
    with path.open(newline="") as f:
        return list(csv.reader(f))


def test_single_split_all_rows_in_train(tmp_path):
    src = tmp_path / "source.csv"
    n = 7
    _write_source_csv(src, n)
    output_root = tmp_path / "out"

    info = create_single_split("ds", src, output_root, seed=1)

    assert info.k == 1
    assert info.total_rows == n
    fold_dir = info.abs_path / "k=0"

    train = _read_rows(fold_dir / "train.csv")
    val = _read_rows(fold_dir / "val.csv")
    test = _read_rows(fold_dir / "test.csv")

    # train.csv = header + all N data rows.
    assert len(train) == n + 1
    # val.csv / test.csv are header-only.
    assert len(val) == 1
    assert len(test) == 1
    assert val[0] == train[0] == test[0]  # same header everywhere


def test_single_split_name_pattern(tmp_path):
    src = tmp_path / "source.csv"
    _write_source_csv(src, 3)
    info = create_single_split("ds", src, tmp_path / "out", seed=42)
    assert re.match(r"^alltrain_seed_\d+_[0-9a-f]{8}$", info.split_name)


def test_single_split_metadata(tmp_path):
    src = tmp_path / "source.csv"
    n = 5
    _write_source_csv(src, n)
    info = create_single_split("ds", src, tmp_path / "out", seed=3)

    meta = json.loads((info.abs_path / "metadata.json").read_text())
    assert meta["kind"] == "single"
    assert meta["k"] == 1
    assert meta["seed"] == 3
    assert meta["total_rows"] == n
    assert meta["per_fold_counts"] == [{"train": n, "val": 0, "test": 0}]
    assert meta["slide_id_column"] == "slide_id"


def test_single_split_strips_tif(tmp_path):
    src = tmp_path / "source.csv"
    _write_source_csv(src, 4, tif=True)
    info = create_single_split("ds", src, tmp_path / "out", seed=1)

    train = _read_rows(info.abs_path / "k=0" / "train.csv")
    # Every slide-id value had its .tif stripped in the generated CSV.
    for row in train[1:]:
        assert not row[0].endswith(".tif")
    meta = json.loads((info.abs_path / "metadata.json").read_text())
    assert meta["slide_id_normalized"] is True


def test_single_split_rejects_missing_slide_id(tmp_path):
    src = tmp_path / "source.csv"
    with src.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["foo", "bar"])
        w.writerow(["1", "2"])
    with pytest.raises(SplitterError):
        create_single_split("ds", src, tmp_path / "out", seed=1)


def test_single_split_rejects_empty(tmp_path):
    src = tmp_path / "source.csv"
    with src.open("w", newline="") as f:
        csv.writer(f).writerow(["slide_id", "label"])
    with pytest.raises(SplitterError):
        create_single_split("ds", src, tmp_path / "out", seed=1)
