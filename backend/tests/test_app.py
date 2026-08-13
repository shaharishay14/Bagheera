"""Application wiring: health, CORS, router registration, storage bootstrap.

Also the guard that keeps the server bootable on a laptop: importing the app
must never pull in torch / openslide / h5py.
"""
from __future__ import annotations

import sys

import pytest

from app.main import app


def test_health_reports_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.parametrize(
    "prefix",
    [
        "/api/fs",
        "/api/datasets",
        "/api/trident",
        "/api/panther",
        "/api/runs",
        "/api/splits",
        "/api/model-groups",
        "/api/models",
        "/api/prototype-labels",
        "/api/model-notes",
        "/api/inferences",
        "/api/jobs",
        "/api/queue",
        "/api/viz",
        "/api/slide-thumbnail",
    ],
)
def test_every_resource_is_mounted(prefix):
    assert any(route.path.startswith(prefix) for route in app.routes), prefix


def test_the_openapi_schema_builds():
    """A response_model mismatch anywhere surfaces here rather than at runtime."""
    schema = app.openapi()
    assert schema["info"]["title"] == "Bagheera"
    assert "/api/health" in schema["paths"]


def test_cors_preflight_allows_the_configured_origin(client):
    from app.config import settings

    origin = settings.cors_origins[0]
    resp = client.options(
        "/api/health",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.status_code == 200
    assert resp.headers["access-control-allow-origin"] == origin


def test_ensure_storage_dirs_creates_the_cache_roots(tmp_path, override_settings):
    from app.config import ensure_storage_dirs

    viz = tmp_path / "viz_cache"
    inf = tmp_path / "inference_outputs"
    override_settings(viz_cache_root=viz, inference_root=inf)

    ensure_storage_dirs()
    assert viz.is_dir()
    assert inf.is_dir()
    assert (viz / "job_logs").is_dir()


def test_ensure_storage_dirs_is_idempotent(tmp_path, override_settings):
    from app.config import ensure_storage_dirs

    override_settings(
        viz_cache_root=tmp_path / "viz", inference_root=tmp_path / "inf"
    )
    ensure_storage_dirs()
    ensure_storage_dirs()  # must not raise


@pytest.mark.parametrize("heavy", ["torch", "openslide", "h5py", "umap", "matplotlib"])
def test_importing_the_app_does_not_pull_in_ml_dependencies(heavy):
    """The lazy-import convention: the server must boot without GPU deps."""
    assert heavy not in sys.modules, f"{heavy} was imported at module scope"


def test_settings_parse_a_colon_separated_root_list(monkeypatch, tmp_path):
    from app.config import load_settings

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    monkeypatch.setenv("TRIDENT_ALLOWED_ROOTS", f"{a}:{b}")
    assert load_settings().allowed_roots == [a.resolve(), b.resolve()]


def test_settings_ignore_empty_entries_in_the_root_list(monkeypatch, tmp_path):
    from app.config import load_settings

    monkeypatch.setenv("TRIDENT_ALLOWED_ROOTS", f"{tmp_path}::  :")
    assert load_settings().allowed_roots == [tmp_path.resolve()]


def test_settings_fall_back_to_home_when_no_roots_are_configured(monkeypatch):
    from pathlib import Path

    from app.config import load_settings

    monkeypatch.delenv("TRIDENT_ALLOWED_ROOTS", raising=False)
    assert load_settings().allowed_roots == [Path.home().resolve()]


def test_splits_root_defaults_under_the_panther_repo(monkeypatch, tmp_path):
    from app.config import load_settings

    monkeypatch.setenv("PANTHER_REPO_PATH", str(tmp_path / "PANTHER"))
    monkeypatch.delenv("DATASETS_SPLITS_ROOT", raising=False)
    settings = load_settings()
    assert settings.datasets_splits_root == (tmp_path / "PANTHER" / "src" / "datasets_splits")


def test_an_explicit_splits_root_overrides_the_panther_default(monkeypatch, tmp_path):
    from app.config import load_settings

    monkeypatch.setenv("PANTHER_REPO_PATH", str(tmp_path / "PANTHER"))
    monkeypatch.setenv("DATASETS_SPLITS_ROOT", str(tmp_path / "elsewhere"))
    assert load_settings().datasets_splits_root == (tmp_path / "elsewhere").resolve()
