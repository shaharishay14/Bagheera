"""PANTHER subprocess plumbing: path layout, argv, data_source shimming.

`execute` is never called — building the command and resolving the paths is the
part that has to be right before a GPU box is involved.
"""
from __future__ import annotations

import pytest

from app.services.panther_runner import (
    CUDA_VISIBLE_DEVICES,
    FEATS_DIR_NAMES,
    SPLIT_NAMES,
    PantherFoldArgs,
    build_command,
    dataset_splits_root_abs,
    datasets_splits_root_abs,
    feats_h5_data_source,
    fold_dir_abs,
    fold_dir_rel,
    kfold_split_dir_abs,
    panther_src_dir,
    render_command,
    scan_prototype_files,
)


REPO = "/opt/PANTHER"


# --- path layout ----------------------------------------------------------


def test_src_dir_is_the_repos_src_folder():
    assert str(panther_src_dir(REPO)) == "/opt/PANTHER/src"


def test_datasets_splits_root_lives_under_src_splits():
    assert str(datasets_splits_root_abs(REPO)) == "/opt/PANTHER/src/splits/datasets_splits"


def test_dataset_splits_root_appends_the_dataset_name():
    assert str(dataset_splits_root_abs(REPO, "brca")) == (
        "/opt/PANTHER/src/splits/datasets_splits/brca"
    )


def test_split_dir_appends_the_split_name():
    assert str(kfold_split_dir_abs(REPO, "brca", "kfold_k_5_seed_1_ab12")) == (
        "/opt/PANTHER/src/splits/datasets_splits/brca/kfold_k_5_seed_1_ab12"
    )


def test_fold_dir_abs_appends_the_fold_folder():
    assert str(fold_dir_abs(REPO, "brca", "sp", 2)) == (
        "/opt/PANTHER/src/splits/datasets_splits/brca/sp/k=2"
    )


def test_fold_dir_rel_omits_the_splits_prefix_panther_prepends():
    """PANTHER does `split_dir = join('splits', split_dir)`, so the CLI value
    must NOT carry the prefix even though the on-disk path does."""
    assert fold_dir_rel("brca", "sp", 2) == "datasets_splits/brca/sp/k=2"


def test_the_relative_fold_dir_resolves_to_the_absolute_one_under_src():
    from pathlib import Path

    rel = fold_dir_rel("brca", "sp", 2)
    assert panther_src_dir(REPO) / "splits" / rel == Path(fold_dir_abs(REPO, "brca", "sp", 2))


@pytest.mark.parametrize("bad_name", ["../etc", "has space", "a/b", "$(id)"])
def test_dataset_paths_reject_a_name_that_could_escape(bad_name):
    with pytest.raises(ValueError, match="Invalid dataset_name"):
        dataset_splits_root_abs(REPO, bad_name)


# --- feats_h5_data_source -------------------------------------------------


@pytest.mark.parametrize("name", FEATS_DIR_NAMES)
def test_a_directory_panther_already_accepts_is_passed_through(tmp_path, name):
    d = tmp_path / name
    d.mkdir()
    assert feats_h5_data_source(str(d)) == str(d)


def test_a_trident_features_dir_is_wrapped_in_a_feats_h5_symlink(tmp_path, monkeypatch):
    import app.services.panther_runner as pr

    monkeypatch.setattr(pr, "FEATS_LINKS_ROOT", tmp_path / "links")
    feats = tmp_path / "features_uni_v1"
    feats.mkdir()

    source = pr.feats_h5_data_source(str(feats))
    from pathlib import Path

    link = Path(source)
    assert link.name == "feats_h5"
    assert link.is_symlink()
    assert link.resolve() == feats.resolve()


def test_the_shim_is_idempotent(tmp_path, monkeypatch):
    import app.services.panther_runner as pr

    monkeypatch.setattr(pr, "FEATS_LINKS_ROOT", tmp_path / "links")
    feats = tmp_path / "features_uni_v1"
    feats.mkdir()
    assert pr.feats_h5_data_source(str(feats)) == pr.feats_h5_data_source(str(feats))


def test_distinct_features_dirs_get_distinct_wrappers(tmp_path, monkeypatch):
    import app.services.panther_runner as pr

    monkeypatch.setattr(pr, "FEATS_LINKS_ROOT", tmp_path / "links")
    a = tmp_path / "features_uni_v1"
    b = tmp_path / "features_phikon"
    a.mkdir()
    b.mkdir()
    assert pr.feats_h5_data_source(str(a)) != pr.feats_h5_data_source(str(b))


def test_a_stale_symlink_is_repointed(tmp_path, monkeypatch):
    import app.services.panther_runner as pr
    from pathlib import Path

    monkeypatch.setattr(pr, "FEATS_LINKS_ROOT", tmp_path / "links")
    feats = tmp_path / "features_uni_v1"
    feats.mkdir()
    source = Path(pr.feats_h5_data_source(str(feats)))

    source.unlink()
    source.symlink_to(tmp_path / "somewhere_else")
    assert Path(pr.feats_h5_data_source(str(feats))).resolve() == feats.resolve()


def test_the_shim_falls_back_to_the_original_dir_on_oserror(tmp_path, monkeypatch):
    import app.services.panther_runner as pr

    monkeypatch.setattr(pr, "FEATS_LINKS_ROOT", tmp_path / "links")
    monkeypatch.setattr(
        pr.Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only fs"))
    )
    feats = tmp_path / "features_uni_v1"
    assert pr.feats_h5_data_source(str(feats)) == str(feats)


# --- build_command --------------------------------------------------------


@pytest.fixture()
def fold_args() -> PantherFoldArgs:
    return PantherFoldArgs(
        features_dir="/feats/feats_h5",
        split_dir_rel="splits/datasets_splits/brca/sp/k=0",
        mode="faiss",
        in_dim=1024,
        n_proto_patches=1000000,
        n_proto=16,
        n_init=5,
        seed=7,
        num_workers=8,
    )


def test_command_invokes_the_bash_wrapper(fold_args):
    cmd = build_command(fold_args)
    assert cmd[0] == "bash"
    assert cmd[1].endswith("scripts/run_panther.sh")


def test_command_carries_every_hyperparameter(fold_args):
    cmd = build_command(fold_args)
    pairs = {cmd[i]: cmd[i + 1] for i in range(2, len(cmd) - 1, 2)}
    assert pairs["--mode"] == "faiss"
    assert pairs["--data_source"] == "/feats/feats_h5"
    assert pairs["--split_dir"] == "splits/datasets_splits/brca/sp/k=0"
    assert pairs["--split_names"] == SPLIT_NAMES
    assert pairs["--in_dim"] == "1024"
    assert pairs["--n_proto_patches"] == "1000000"
    assert pairs["--n_proto"] == "16"
    assert pairs["--n_init"] == "5"
    assert pairs["--seed"] == "7"
    assert pairs["--num_workers"] == "8"


def test_command_flags_and_values_are_balanced(fold_args):
    cmd = build_command(fold_args)
    assert len(cmd[2:]) % 2 == 0


def test_render_command_quotes_paths_with_spaces(fold_args):
    args = PantherFoldArgs(**{**fold_args.__dict__, "features_dir": "/my feats/feats_h5"})
    assert "'/my feats/feats_h5'" in render_command(build_command(args))


def test_the_runner_pins_a_single_gpu():
    assert CUDA_VISIBLE_DEVICES == "0"


# --- scan_prototype_files -------------------------------------------------


def test_scan_returns_pkl_and_pt_basenames_sorted(tmp_path):
    for name in ("b.pt", "a.pkl", "c.pkl"):
        (tmp_path / name).write_bytes(b"")
    assert scan_prototype_files(tmp_path) == ["a.pkl", "b.pt", "c.pkl"]


def test_scan_ignores_other_files_and_subdirectories(tmp_path):
    (tmp_path / "a.pkl").write_bytes(b"")
    (tmp_path / "log.txt").write_text("x")
    (tmp_path / "nested").mkdir()
    assert scan_prototype_files(tmp_path) == ["a.pkl"]


def test_scan_returns_empty_for_a_missing_directory(tmp_path):
    assert scan_prototype_files(tmp_path / "nope") == []


def test_scan_returns_empty_for_an_empty_directory(tmp_path):
    assert scan_prototype_files(tmp_path) == []
