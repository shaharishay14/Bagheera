"""Inference service helpers: WSI hashing, cache lookup, TRIDENT argv.

Nothing here runs TRIDENT — `build_trident_command` only *builds* argv, which is
exactly the part worth pinning down, since a wrong flag only surfaces on a GPU
box hours into a run.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from pathlib import Path

import pytest

from app.db.models import Inference, Model, TridentRun
from app.services.inference import (
    DEFAULT_GPUS,
    InferenceServiceError,
    build_trident_command,
    compute_wsi_hash,
    expected_features_dir_name,
    generate_custom_wsi_csv,
    inference_output_dir,
    inherited_trident_params,
    locate_features_file,
    lookup_cached_inference,
    render_command,
    trident_output_root,
)


def _trident_run(db, *, encoder="uni_v1", mag=20, patch_size=256) -> TridentRun:
    row = TridentRun(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        dataset_name="ds",
        wsi_dir="/wsi",
        patch_encoder=encoder,
        mag=mag,
        patch_size=patch_size,
        command="bash run_trident.sh",
        status="succeeded",
        output_dir="/feats",
    )
    db.add(row)
    db.commit()
    return row


def _model(db, *, trident_run_id: str | None) -> Model:
    mid = str(uuid.uuid4())
    row = Model(
        id=mid,
        created_at=datetime.utcnow(),
        base_name="m",
        model_name=f"m_{mid[:8]}",
        group_id=mid,
        fold_index=0,
        fold_k=1,
        dataset_name="ds",
        features_dir="/feats",
        trident_run_id=trident_run_id,
        split_id=str(uuid.uuid4()),
        split_name="sp",
        mode="faiss",
        in_dim=1024,
        n_proto_patches=1000,
        n_proto=8,
        n_init=1,
        seed=1,
        num_workers=0,
        status="ready",
    )
    db.add(row)
    db.commit()
    return row


@pytest.fixture()
def wsi(tmp_path):
    p = tmp_path / "slide-001.svs"
    p.write_bytes(b"fake-wsi-bytes" * 100)
    return p


# --- compute_wsi_hash -----------------------------------------------------


def test_hash_matches_a_plain_sha256_of_the_file(wsi):
    assert compute_wsi_hash(wsi) == hashlib.sha256(wsi.read_bytes()).hexdigest()


def test_hash_is_stable_across_repeated_calls(wsi):
    assert compute_wsi_hash(wsi) == compute_wsi_hash(wsi)


def test_hash_changes_when_the_file_content_changes(wsi):
    before = compute_wsi_hash(wsi)
    wsi.write_bytes(b"different")
    assert compute_wsi_hash(wsi) != before


def test_hash_spans_multiple_chunks(tmp_path, monkeypatch):
    """A file larger than the chunk size must hash the same as the whole blob."""
    import app.services.inference as inference_mod

    monkeypatch.setattr(inference_mod, "HASH_CHUNK_BYTES", 8)
    big = tmp_path / "big.svs"
    big.write_bytes(b"0123456789" * 50)
    assert compute_wsi_hash(big) == hashlib.sha256(big.read_bytes()).hexdigest()


def test_hash_raises_for_a_missing_file(tmp_path):
    with pytest.raises(InferenceServiceError):
        compute_wsi_hash(tmp_path / "nope.svs")


def test_hash_raises_for_a_directory(tmp_path):
    with pytest.raises(InferenceServiceError):
        compute_wsi_hash(tmp_path)


# --- lookup_cached_inference ----------------------------------------------


def _inference_row(db, model_id: str, wsi: Path, *, wsi_hash: str) -> Inference:
    stat = wsi.stat()
    row = Inference(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow(),
        model_id=model_id,
        wsi_path=str(wsi),
        wsi_filename=wsi.name,
        wsi_mtime=stat.st_mtime,
        wsi_size=stat.st_size,
        wsi_hash=wsi_hash,
        output_dir="/out",
        status="succeeded",
    )
    db.add(row)
    db.commit()
    return row


def test_lookup_returns_the_row_on_a_verified_hit(db, wsi):
    model = _model(db, trident_run_id=None)
    row = _inference_row(db, model.id, wsi, wsi_hash=compute_wsi_hash(wsi))
    assert lookup_cached_inference(db, model.id, wsi).id == row.id


def test_lookup_misses_when_no_row_exists(db, wsi):
    model = _model(db, trident_run_id=None)
    assert lookup_cached_inference(db, model.id, wsi) is None


def test_lookup_misses_for_a_different_model(db, wsi):
    a = _model(db, trident_run_id=None)
    b = _model(db, trident_run_id=None)
    _inference_row(db, a.id, wsi, wsi_hash=compute_wsi_hash(wsi))
    assert lookup_cached_inference(db, b.id, wsi) is None


def test_lookup_misses_when_the_stored_hash_disagrees(db, wsi):
    """mtime + size pre-check passes but the hash is the source of truth."""
    model = _model(db, trident_run_id=None)
    _inference_row(db, model.id, wsi, wsi_hash="0" * 64)
    assert lookup_cached_inference(db, model.id, wsi) is None


def test_lookup_misses_when_the_file_size_changed(db, wsi):
    model = _model(db, trident_run_id=None)
    _inference_row(db, model.id, wsi, wsi_hash=compute_wsi_hash(wsi))
    wsi.write_bytes(wsi.read_bytes() + b"appended")
    assert lookup_cached_inference(db, model.id, wsi) is None


def test_lookup_misses_when_the_wsi_is_gone(db, wsi):
    model = _model(db, trident_run_id=None)
    _inference_row(db, model.id, wsi, wsi_hash=compute_wsi_hash(wsi))
    wsi.unlink()
    assert lookup_cached_inference(db, model.id, wsi) is None


# --- inherited_trident_params ---------------------------------------------


def test_params_come_from_the_linked_trident_run(db):
    run = _trident_run(db, encoder="phikon", mag=20, patch_size=224)
    params = inherited_trident_params(_model(db, trident_run_id=run.id), db)
    assert (params.patch_encoder, params.mag, params.patch_size) == ("phikon", 20, 224)
    assert params.trident_run_id == run.id
    assert params.gpus == DEFAULT_GPUS


def test_params_are_all_none_when_the_model_has_no_run(db):
    params = inherited_trident_params(_model(db, trident_run_id=None), db)
    assert params.trident_run_id is None
    assert params.patch_encoder is None


def test_params_keep_the_dangling_run_id_when_the_run_row_is_gone(db):
    model = _model(db, trident_run_id="deleted-run-id")
    params = inherited_trident_params(model, db)
    assert params.trident_run_id == "deleted-run-id"
    assert params.patch_encoder is None


# --- path helpers ---------------------------------------------------------


def test_features_dir_name_follows_the_trident_convention():
    assert expected_features_dir_name(20, 256) == "20x_256px_0px_overlap"


def test_trident_output_root_is_nested_under_the_output_dir(tmp_path):
    assert trident_output_root(tmp_path) == tmp_path / "trident_output"


def test_locate_features_file_returns_the_h5_when_present(tmp_path):
    feats = (
        trident_output_root(tmp_path) / "20x_256px_0px_overlap" / "features_uni_v1"
    )
    feats.mkdir(parents=True)
    (feats / "slide-001.h5").write_bytes(b"")
    found = locate_features_file(
        tmp_path, "slide-001", mag=20, patch_size=256, patch_encoder="uni_v1"
    )
    assert found == feats / "slide-001.h5"


def test_locate_features_file_raises_with_the_expected_path(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        locate_features_file(
            tmp_path, "slide-001", mag=20, patch_size=256, patch_encoder="uni_v1"
        )
    assert "20x_256px_0px_overlap" in str(exc.value)


def test_inference_output_dir_is_created_under_the_inference_root(
    tmp_path, override_settings
):
    override_settings(inference_root=tmp_path / "inf")
    out = inference_output_dir("model-1", "inf-1")
    assert out == tmp_path / "inf" / "model-1" / "inf-1"
    assert out.is_dir()


# --- generate_custom_wsi_csv ----------------------------------------------


def test_custom_csv_holds_a_wsi_header_and_the_basename(tmp_path, wsi):
    target = tmp_path / "nested" / "custom.csv"
    generate_custom_wsi_csv(wsi, target)
    assert target.read_text().splitlines() == ["wsi", wsi.name]


def test_custom_csv_creates_missing_parent_directories(tmp_path, wsi):
    target = tmp_path / "a" / "b" / "c" / "custom.csv"
    generate_custom_wsi_csv(wsi, target)
    assert target.is_file()


# --- build_trident_command ------------------------------------------------


def test_command_carries_the_inherited_encoder_mag_and_patch_size(db, wsi, tmp_path):
    run = _trident_run(db, encoder="phikon", mag=20, patch_size=224)
    model = _model(db, trident_run_id=run.id)
    cmd = build_trident_command(model, db, wsi, tmp_path, tmp_path / "custom.csv")

    assert cmd[1] == "run_batch_of_slides.py"
    assert cmd[cmd.index("--patch_encoder") + 1] == "phikon"
    assert cmd[cmd.index("--mag") + 1] == "20"
    assert cmd[cmd.index("--patch_size") + 1] == "224"
    assert cmd[cmd.index("--task") + 1] == "all"


def test_command_points_wsi_dir_at_the_parent_and_filters_with_the_csv(
    db, wsi, tmp_path
):
    run = _trident_run(db)
    model = _model(db, trident_run_id=run.id)
    cmd = build_trident_command(model, db, wsi, tmp_path, tmp_path / "custom.csv")
    assert cmd[cmd.index("--wsi_dir") + 1] == str(wsi.parent)
    assert cmd[cmd.index("--custom_list_of_wsis") + 1] == str(tmp_path / "custom.csv")
    assert cmd[cmd.index("--job_dir") + 1] == str(trident_output_root(tmp_path))


def test_command_defaults_to_gpu_zero(db, wsi, tmp_path):
    run = _trident_run(db)
    model = _model(db, trident_run_id=run.id)
    cmd = build_trident_command(model, db, wsi, tmp_path, tmp_path / "custom.csv")
    assert cmd[cmd.index("--gpus") + 1 :] == ["0"]


def test_command_uses_the_configured_trident_python(db, wsi, tmp_path, override_settings):
    override_settings(trident_python="/opt/conda/envs/trident/bin/python")
    run = _trident_run(db)
    model = _model(db, trident_run_id=run.id)
    cmd = build_trident_command(model, db, wsi, tmp_path, tmp_path / "custom.csv")
    assert cmd[0] == "/opt/conda/envs/trident/bin/python"


def test_command_raises_when_the_model_has_no_inherited_params(db, wsi, tmp_path):
    model = _model(db, trident_run_id=None)
    with pytest.raises(InferenceServiceError):
        build_trident_command(model, db, wsi, tmp_path, tmp_path / "custom.csv")


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("0", ["0"]),
        ("0 1", ["0", "1"]),
        ("0,1,2", ["0", "1", "2"]),
        ("-1", ["-1"]),
        ("", ["0"]),
        (None, ["0"]),
        ("   ", ["0"]),
    ],
)
def test_gpu_string_splits_into_individual_cli_tokens(raw, expected):
    from app.services.inference import _parse_gpus

    assert _parse_gpus(raw) == expected


def test_render_command_quotes_arguments_containing_spaces():
    assert render_command(["python", "run.py", "--wsi_dir", "/a b/c"]) == (
        "python run.py --wsi_dir '/a b/c'"
    )
