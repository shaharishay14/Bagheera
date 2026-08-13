"""The single ("100% train") splitter — the only split the product creates.

One model is trained on the entire dataset, so the property that matters is
that the whole cohort reaches train.csv unchanged: no row dropped, no row
duplicated, no column mangled. `val.csv` and `test.csv` are written header-only
because PANTHER's loader globs for them but only ever reads train.
"""
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


# --- the whole cohort reaches training ------------------------------------


def test_single_split_loses_no_row_and_duplicates_none(tmp_path):
    """The defining property: train.csv is the cohort, exactly once each."""
    src = tmp_path / "source.csv"
    _write_source_csv(src, 50)
    info = create_single_split("ds", src, tmp_path / "out", seed=1)

    ids = [row[0] for row in _read_rows(info.abs_path / "k=0" / "train.csv")[1:]]
    assert sorted(ids) == sorted(f"slide_{i}" for i in range(50))
    assert len(ids) == len(set(ids))


def test_single_split_preserves_row_order(tmp_path):
    """No shuffling — a reviewer can diff train.csv against the source."""
    src = tmp_path / "source.csv"
    _write_source_csv(src, 20)
    info = create_single_split("ds", src, tmp_path / "out", seed=1)

    ids = [row[0] for row in _read_rows(info.abs_path / "k=0" / "train.csv")[1:]]
    assert ids == [f"slide_{i}" for i in range(20)]


def test_single_split_preserves_every_column(tmp_path):
    src = tmp_path / "source.csv"
    with src.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slide_id", "label", "site", "stain"])
        w.writerow(["s1", "pos", "site_a", "he"])
        w.writerow(["s2", "neg", "site_b", "ihc"])

    info = create_single_split("ds", src, tmp_path / "out", seed=1)
    rows = _read_rows(info.abs_path / "k=0" / "train.csv")
    assert rows[0] == ["slide_id", "label", "site", "stain"]
    assert rows[1] == ["s1", "pos", "site_a", "he"]
    assert rows[2] == ["s2", "neg", "site_b", "ihc"]


def test_single_split_seed_does_not_change_the_contents(tmp_path):
    """Seed is provenance only — with no held-out set there is nothing to shuffle."""
    src = tmp_path / "source.csv"
    _write_source_csv(src, 15)
    a = create_single_split("ds", src, tmp_path / "out", seed=1)
    b = create_single_split("ds", src, tmp_path / "out", seed=999)

    assert _read_rows(a.abs_path / "k=0" / "train.csv") == _read_rows(
        b.abs_path / "k=0" / "train.csv"
    )


def test_single_split_handles_a_one_slide_cohort(tmp_path):
    src = tmp_path / "source.csv"
    _write_source_csv(src, 1)
    info = create_single_split("ds", src, tmp_path / "out", seed=1)

    assert info.total_rows == 1
    assert len(_read_rows(info.abs_path / "k=0" / "train.csv")) == 2  # header + 1


def test_single_split_writes_the_fold_layout_panther_expects(tmp_path):
    """PANTHER reads {split_dir}/k=0/train.csv — the directory name is a contract."""
    src = tmp_path / "source.csv"
    _write_source_csv(src, 5)
    info = create_single_split("ds", src, tmp_path / "out", seed=1)

    fold = info.abs_path / "k=0"
    assert fold.is_dir()
    for name in ("train.csv", "val.csv", "test.csv"):
        assert (fold / name).is_file()


def test_single_split_names_do_not_collide_across_runs(tmp_path):
    src = tmp_path / "source.csv"
    _write_source_csv(src, 5)
    a = create_single_split("ds", src, tmp_path / "out", seed=1)
    b = create_single_split("ds", src, tmp_path / "out", seed=1)

    assert a.split_name != b.split_name
    assert a.abs_path != b.abs_path


@pytest.mark.parametrize("column", ["slide_id", "case_id", "slide", "id"])
def test_single_split_accepts_any_recognized_id_column(tmp_path, column):
    src = tmp_path / "source.csv"
    _write_source_csv(src, 6, slide_col=column)
    info = create_single_split("ds", src, tmp_path / "out", seed=1)

    assert info.total_rows == 6
    meta = json.loads((info.abs_path / "metadata.json").read_text())
    assert meta["slide_id_column"] == column


def test_single_split_strips_tiff_case_insensitively(tmp_path):
    src = tmp_path / "source.csv"
    with src.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["slide_id"])
        w.writerows([["a.TIF"], ["b.tiff"], ["c.TIFF"], ["d"]])

    info = create_single_split("ds", src, tmp_path / "out", seed=1)
    ids = [row[0] for row in _read_rows(info.abs_path / "k=0" / "train.csv")[1:]]
    assert ids == ["a", "b", "c", "d"]


def test_single_split_leaves_ids_alone_when_nothing_needs_stripping(tmp_path):
    src = tmp_path / "source.csv"
    _write_source_csv(src, 4)
    info = create_single_split("ds", src, tmp_path / "out", seed=1)

    meta = json.loads((info.abs_path / "metadata.json").read_text())
    assert meta["slide_id_normalized"] is False


def test_single_split_never_modifies_the_source_csv(tmp_path):
    """The /data mount is read-only; only generated files are transformed."""
    src = tmp_path / "source.csv"
    _write_source_csv(src, 8, tif=True)
    original = src.read_bytes()

    create_single_split("ds", src, tmp_path / "out", seed=1)
    assert src.read_bytes() == original


def test_single_split_rejects_an_unreadable_source(tmp_path):
    with pytest.raises(SplitterError):
        create_single_split("ds", tmp_path / "missing.csv", tmp_path / "out", seed=1)


def test_single_split_train_csv_is_readable_by_the_preview_helper(tmp_path):
    """Downstream contract: preview picking reads the file this writes."""
    from app.services.preview import read_slide_ids_from_train_csv

    src = tmp_path / "source.csv"
    _write_source_csv(src, 9)
    info = create_single_split("ds", src, tmp_path / "out", seed=1)

    ids = read_slide_ids_from_train_csv(str(info.abs_path / "k=0"))
    assert ids == [f"slide_{i}" for i in range(9)]


def test_single_split_val_csv_reads_back_as_empty(tmp_path):
    """Section B consistency reads val.csv; header-only must yield [], not a crash."""
    from app.services.preview import read_slide_ids_from_csv

    src = tmp_path / "source.csv"
    _write_source_csv(src, 5)
    info = create_single_split("ds", src, tmp_path / "out", seed=1)

    assert read_slide_ids_from_csv(str(info.abs_path / "k=0"), "val.csv") == []
