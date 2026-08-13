"""Preview-slide picking: CSV column detection + per-model determinism.

The route and the post_train_viz handler both call `pick_preview_slides`, so a
drift here would silently show one set of slides in the UI and render another.
"""
from __future__ import annotations

import uuid

import pytest

from app.db.models import Model
from app.services.preview import (
    PREVIEW_SLIDE_COUNT,
    pick_preview_slides,
    read_slide_ids_from_csv,
    read_slide_ids_from_train_csv,
)


def _model(split_dir, *, seed: int = 1, fold_index: int = 0, model_id: str | None = None) -> Model:
    """A detached Model instance — `pick_preview_slides` never touches the DB."""
    return Model(
        id=model_id or str(uuid.uuid4()),
        base_name="m",
        model_name="m_1",
        group_id="g",
        fold_index=fold_index,
        fold_k=1,
        dataset_name="ds",
        features_dir="/feats",
        split_id="s",
        split_name="sp",
        split_dir_abs=str(split_dir),
        mode="faiss",
        in_dim=1024,
        n_proto_patches=1000,
        n_proto=8,
        n_init=1,
        seed=seed,
        num_workers=0,
    )


@pytest.fixture()
def split_dir(tmp_path):
    d = tmp_path / "split"
    d.mkdir()
    return d


# --- read_slide_ids_from_csv ----------------------------------------------


def test_reads_the_slide_id_column_by_name(split_dir):
    (split_dir / "train.csv").write_text("label,slide_id\ntumor,S1\nnormal,S2\n")
    assert read_slide_ids_from_csv(str(split_dir), "train.csv") == ["S1", "S2"]


@pytest.mark.parametrize("column", ["slide_id", "case_id", "slide", "id"])
def test_accepts_every_recognized_id_column_name(split_dir, column):
    (split_dir / "train.csv").write_text(f"{column}\nS1\n")
    assert read_slide_ids_from_csv(str(split_dir), "train.csv") == ["S1"]


def test_column_match_is_case_and_whitespace_insensitive(split_dir):
    (split_dir / "train.csv").write_text("  Slide_ID  \nS1\n")
    assert read_slide_ids_from_csv(str(split_dir), "train.csv") == ["S1"]


def test_falls_back_to_the_first_column_when_no_name_matches(split_dir):
    (split_dir / "train.csv").write_text("whatever,extra\nS1,x\nS2,y\n")
    assert read_slide_ids_from_csv(str(split_dir), "train.csv") == ["S1", "S2"]


def test_skips_rows_with_a_blank_or_missing_id(split_dir):
    (split_dir / "train.csv").write_text("slide_id,label\nS1,a\n,b\nS3,c\n")
    assert read_slide_ids_from_csv(str(split_dir), "train.csv") == ["S1", "S3"]


def test_missing_file_returns_empty_list(split_dir):
    assert read_slide_ids_from_csv(str(split_dir), "nope.csv") == []


def test_empty_file_returns_empty_list(split_dir):
    (split_dir / "train.csv").write_text("")
    assert read_slide_ids_from_csv(str(split_dir), "train.csv") == []


def test_header_only_file_returns_empty_list(split_dir):
    (split_dir / "train.csv").write_text("slide_id\n")
    assert read_slide_ids_from_csv(str(split_dir), "train.csv") == []


def test_val_csv_is_read_through_the_same_helper(split_dir):
    (split_dir / "val.csv").write_text("slide_id\nV1\n")
    assert read_slide_ids_from_csv(str(split_dir), "val.csv") == ["V1"]


def test_train_csv_wrapper_targets_train_csv(split_dir):
    (split_dir / "train.csv").write_text("slide_id\nT1\n")
    (split_dir / "val.csv").write_text("slide_id\nV1\n")
    assert read_slide_ids_from_train_csv(str(split_dir)) == ["T1"]


# --- pick_preview_slides --------------------------------------------------


def test_pick_is_deterministic_for_the_same_model(split_dir):
    (split_dir / "train.csv").write_text(
        "slide_id\n" + "\n".join(f"S{i}" for i in range(20)) + "\n"
    )
    model = _model(split_dir, model_id="fixed-id")
    assert pick_preview_slides(model) == pick_preview_slides(_model(split_dir, model_id="fixed-id"))


def test_pick_differs_across_models(split_dir):
    (split_dir / "train.csv").write_text(
        "slide_id\n" + "\n".join(f"S{i}" for i in range(50)) + "\n"
    )
    a = pick_preview_slides(_model(split_dir, model_id="model-a"))
    b = pick_preview_slides(_model(split_dir, model_id="model-b"))
    assert a != b


def test_pick_returns_at_most_the_preview_count(split_dir):
    (split_dir / "train.csv").write_text(
        "slide_id\n" + "\n".join(f"S{i}" for i in range(20)) + "\n"
    )
    assert len(pick_preview_slides(_model(split_dir))) == PREVIEW_SLIDE_COUNT


def test_pick_returns_everything_when_the_pool_is_smaller(split_dir):
    (split_dir / "train.csv").write_text("slide_id\nS1\nS2\n")
    assert sorted(pick_preview_slides(_model(split_dir))) == ["S1", "S2"]


def test_pick_honors_an_explicit_count(split_dir):
    (split_dir / "train.csv").write_text(
        "slide_id\n" + "\n".join(f"S{i}" for i in range(20)) + "\n"
    )
    assert len(pick_preview_slides(_model(split_dir), count=5)) == 5


def test_pick_only_returns_ids_from_the_pool(split_dir):
    ids = [f"S{i}" for i in range(20)]
    (split_dir / "train.csv").write_text("slide_id\n" + "\n".join(ids) + "\n")
    assert set(pick_preview_slides(_model(split_dir))) <= set(ids)


def test_pick_returns_empty_when_train_csv_is_absent(split_dir):
    assert pick_preview_slides(_model(split_dir)) == []
