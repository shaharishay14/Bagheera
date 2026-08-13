"""TRIDENT command construction and the /api/trident endpoints.

`runner.execute` is monkeypatched everywhere — the bash wrapper and the real
TRIDENT repo are never invoked.
"""
from __future__ import annotations

import uuid
from datetime import datetime

import pytest

from app.db.models import TridentRun
from app.services import runner
from app.services.runner import (
    ENCODER_FEATURE_DIM,
    ENCODER_PATCH_SIZE,
    MAGNIFICATION,
    CommandResult,
    build_command,
    feature_dim_for,
    job_dir_for,
    output_dir_for,
    patch_size_for,
    render_command,
)


@pytest.fixture()
def wsi_root(tmp_path, override_settings):
    root = tmp_path / "wsi"
    root.mkdir()
    (root / "slide-001.svs").write_bytes(b"")
    override_settings(allowed_roots=[root.resolve()])
    return root


@pytest.fixture()
def fake_execute(monkeypatch):
    """Replace the subprocess call with a recorder; returns the captured argv."""
    captured: dict[str, list[str]] = {}

    def _fake(cmd, *, returncode=0):
        captured["cmd"] = cmd
        return CommandResult(returncode=returncode, stdout="ok", stderr="")

    monkeypatch.setattr(runner, "execute", _fake)
    return captured


# --- encoder tables -------------------------------------------------------


@pytest.mark.parametrize("encoder,size", sorted(ENCODER_PATCH_SIZE.items()))
def test_patch_size_is_defined_for_every_supported_encoder(encoder, size):
    assert patch_size_for(encoder) == size


@pytest.mark.parametrize("encoder,dim", sorted(ENCODER_FEATURE_DIM.items()))
def test_feature_dim_is_defined_for_every_supported_encoder(encoder, dim):
    assert feature_dim_for(encoder) == dim


def test_every_encoder_has_both_a_patch_size_and_a_feature_dim():
    assert set(ENCODER_PATCH_SIZE) == set(ENCODER_FEATURE_DIM)


def test_feature_dim_is_none_for_an_unknown_encoder():
    assert feature_dim_for("not_an_encoder") is None


def test_patch_size_raises_for_an_unknown_encoder():
    with pytest.raises(KeyError):
        patch_size_for("not_an_encoder")


# --- path helpers ---------------------------------------------------------


def test_job_dir_is_namespaced_by_dataset():
    assert job_dir_for("brca") == "./trident_processed/brca"


def test_output_dir_encodes_mag_patch_size_and_encoder():
    assert output_dir_for("brca", "phikon") == (
        "./trident_processed/brca/20x_224px_0px_overlap/features_phikon"
    )


def test_output_dir_tracks_the_encoder_patch_size():
    assert "256px" in output_dir_for("brca", "uni_v1")
    assert "224px" in output_dir_for("brca", "phikon")


# --- build_command --------------------------------------------------------


def test_command_invokes_the_bash_wrapper_with_the_expected_flags():
    cmd = build_command("brca", "/data/wsi", "uni_v1")
    assert cmd[0] == "bash"
    assert cmd[1].endswith("scripts/run_trident.sh")
    assert cmd[cmd.index("--wsi_dir") + 1] == "/data/wsi"
    assert cmd[cmd.index("--job_dir") + 1] == "./trident_processed/brca"
    assert cmd[cmd.index("--patch_encoder") + 1] == "uni_v1"
    assert cmd[cmd.index("--mag") + 1] == str(MAGNIFICATION)
    assert cmd[cmd.index("--patch_size") + 1] == "256"


@pytest.mark.parametrize(
    "bad_name", ["../etc", "has space", "semi;colon", "$(whoami)", "a/b"]
)
def test_command_rejects_a_dataset_name_that_could_reach_the_shell(bad_name):
    with pytest.raises(ValueError, match="Invalid dataset_name"):
        build_command(bad_name, "/data/wsi", "uni_v1")


def test_render_command_quotes_paths_containing_spaces():
    rendered = render_command(build_command("brca", "/data/my wsi", "uni_v1"))
    assert "'/data/my wsi'" in rendered


# --- POST /api/trident/run ------------------------------------------------


def test_run_persists_a_succeeded_row(client, db, wsi_root, fake_execute):
    resp = client.post(
        "/api/trident/run",
        json={"dataset_name": "brca", "wsi_dir": str(wsi_root), "patch_encoder": "uni_v1"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "succeeded"
    assert body["return_code"] == 0
    assert body["mag"] == MAGNIFICATION
    assert body["patch_size"] == 256
    assert db.query(TridentRun).count() == 1


def test_run_records_the_rendered_command_and_output_dir(client, db, wsi_root, fake_execute):
    body = client.post(
        "/api/trident/run",
        json={"dataset_name": "brca", "wsi_dir": str(wsi_root), "patch_encoder": "phikon"},
    ).json()
    assert "--patch_encoder phikon" in body["command"]
    assert body["output_dir"] == output_dir_for("brca", "phikon")


def test_run_passes_the_resolved_wsi_dir_to_the_subprocess(client, db, wsi_root, fake_execute):
    client.post(
        "/api/trident/run",
        json={"dataset_name": "brca", "wsi_dir": str(wsi_root), "patch_encoder": "uni_v1"},
    )
    cmd = fake_execute["cmd"]
    assert cmd[cmd.index("--wsi_dir") + 1] == str(wsi_root.resolve())


def test_run_marks_the_row_failed_on_a_nonzero_exit(client, db, wsi_root, monkeypatch):
    monkeypatch.setattr(
        runner,
        "execute",
        lambda cmd: CommandResult(returncode=2, stdout="", stderr="boom"),
    )
    body = client.post(
        "/api/trident/run",
        json={"dataset_name": "brca", "wsi_dir": str(wsi_root), "patch_encoder": "uni_v1"},
    ).json()
    assert body["status"] == "failed"
    assert body["return_code"] == 2
    assert body["stderr"] == "boom"


def test_run_400_when_the_wsi_dir_does_not_exist(client, db, wsi_root, fake_execute):
    resp = client.post(
        "/api/trident/run",
        json={
            "dataset_name": "brca",
            "wsi_dir": str(wsi_root / "missing"),
            "patch_encoder": "uni_v1",
        },
    )
    assert resp.status_code == 400


def test_run_400_when_the_wsi_dir_is_a_file(client, db, wsi_root, fake_execute):
    resp = client.post(
        "/api/trident/run",
        json={
            "dataset_name": "brca",
            "wsi_dir": str(wsi_root / "slide-001.svs"),
            "patch_encoder": "uni_v1",
        },
    )
    assert resp.status_code == 400


def test_run_403_when_the_wsi_dir_is_outside_the_roots(client, db, wsi_root, tmp_path, fake_execute):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    resp = client.post(
        "/api/trident/run",
        json={"dataset_name": "brca", "wsi_dir": str(outside), "patch_encoder": "uni_v1"},
    )
    assert resp.status_code == 403


def test_run_422_on_an_unsupported_encoder(client, db, wsi_root, fake_execute):
    resp = client.post(
        "/api/trident/run",
        json={"dataset_name": "brca", "wsi_dir": str(wsi_root), "patch_encoder": "made_up"},
    )
    assert resp.status_code == 422


def test_run_422_on_an_invalid_dataset_name(client, db, wsi_root, fake_execute):
    resp = client.post(
        "/api/trident/run",
        json={"dataset_name": "../escape", "wsi_dir": str(wsi_root), "patch_encoder": "uni_v1"},
    )
    assert resp.status_code == 422


# --- GET /api/trident/runs ------------------------------------------------


def _run_row(db, *, dataset="ds", offset=0) -> TridentRun:
    from datetime import timedelta

    row = TridentRun(
        id=str(uuid.uuid4()),
        created_at=datetime.utcnow() + timedelta(seconds=offset),
        dataset_name=dataset,
        wsi_dir="/wsi",
        patch_encoder="uni_v1",
        mag=20,
        patch_size=256,
        command="bash run_trident.sh",
        status="succeeded",
        output_dir="/feats",
    )
    db.add(row)
    db.commit()
    return row


def test_runs_are_listed_newest_first(client, db):
    older = _run_row(db, offset=-60)
    newer = _run_row(db, offset=0)
    assert [r["id"] for r in client.get("/api/trident/runs").json()] == [newer.id, older.id]


def test_runs_list_is_empty_on_a_fresh_database(client, db):
    assert client.get("/api/trident/runs").json() == []


def test_get_run_returns_the_row(client, db):
    row = _run_row(db)
    assert client.get(f"/api/trident/runs/{row.id}").json()["id"] == row.id


def test_get_run_404_for_an_unknown_id(client, db):
    assert client.get("/api/trident/runs/ghost").status_code == 404
