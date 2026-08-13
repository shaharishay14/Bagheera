"""The `resolve_within_roots` sandbox and the /api/fs browsing endpoints.

This module covers the project's only security boundary, so the negative cases
(traversal, symlink escape, absolute path outside the roots) matter as much as
the happy path.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.services.fs import is_at_root, list_directory, resolve_within_roots


@pytest.fixture()
def root(tmp_path, override_settings):
    """A single allowed root with a small tree inside it."""
    data = tmp_path / "data"
    (data / "sub").mkdir(parents=True)
    (data / "sub" / "leaf.txt").write_text("x")
    (data / ".hidden").write_text("secret")
    (data / "a.csv").write_text("slide_id\nS1\nS2\nS3\n")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secrets.txt").write_text("nope")
    override_settings(allowed_roots=[data.resolve()])
    return data


# --- resolve_within_roots -------------------------------------------------


def test_resolve_accepts_path_inside_root(root):
    assert resolve_within_roots(str(root / "sub" / "leaf.txt")) == (
        root / "sub" / "leaf.txt"
    ).resolve()


def test_resolve_accepts_the_root_itself(root):
    assert resolve_within_roots(str(root)) == root.resolve()


def test_resolve_rejects_path_outside_root(root, tmp_path):
    with pytest.raises(HTTPException) as exc:
        resolve_within_roots(str(tmp_path / "outside" / "secrets.txt"))
    assert exc.value.status_code == 403


def test_resolve_rejects_dotdot_traversal_out_of_root(root):
    with pytest.raises(HTTPException) as exc:
        resolve_within_roots(str(root / "sub" / ".." / ".." / "outside"))
    assert exc.value.status_code == 403


def test_resolve_collapses_harmless_dotdot_inside_root(root):
    # `sub/../a.csv` stays inside the root, so it resolves rather than 403s.
    assert resolve_within_roots(str(root / "sub" / ".." / "a.csv")) == (
        root / "a.csv"
    ).resolve()


def test_resolve_rejects_symlink_escaping_the_root(root, tmp_path):
    link = root / "escape"
    link.symlink_to(tmp_path / "outside")
    with pytest.raises(HTTPException) as exc:
        resolve_within_roots(str(link / "secrets.txt"))
    assert exc.value.status_code == 403


def test_resolve_500_when_no_roots_configured(override_settings):
    override_settings(allowed_roots=[])
    with pytest.raises(HTTPException) as exc:
        resolve_within_roots("/anything")
    assert exc.value.status_code == 500


def test_is_at_root_only_true_for_the_root_itself(root):
    assert is_at_root(root.resolve()) is True
    assert is_at_root((root / "sub").resolve()) is False


# --- list_directory -------------------------------------------------------


def test_list_directory_hides_dotfiles_by_default(root):
    _, _, entries, _ = list_directory(str(root))
    assert ".hidden" not in [e.name for e in entries]


def test_list_directory_show_hidden_includes_dotfiles(root):
    _, _, entries, _ = list_directory(str(root), show_hidden=True)
    assert ".hidden" in [e.name for e in entries]


def test_list_directory_dirs_only_filters_files(root):
    _, _, entries, _ = list_directory(str(root), dirs_only=True)
    assert [e.name for e in entries] == ["sub"]


def test_list_directory_sorts_dirs_first_then_name(root):
    (root / "b.csv").write_text("")
    _, _, entries, _ = list_directory(str(root))
    assert [e.name for e in entries] == ["sub", "a.csv", "b.csv"]


def test_list_directory_root_has_no_parent(root):
    target, parent, _, at_root = list_directory(str(root))
    assert target == root.resolve()
    assert parent is None
    assert at_root is True


def test_list_directory_subdir_exposes_parent(root):
    _, parent, _, at_root = list_directory(str(root / "sub"))
    assert parent == root.resolve()
    assert at_root is False


def test_list_directory_none_path_falls_back_to_first_root(root):
    target, _, _, at_root = list_directory(None)
    assert target == root.resolve()
    assert at_root is True


def test_list_directory_404_on_missing_path(root):
    with pytest.raises(HTTPException) as exc:
        list_directory(str(root / "nope"))
    assert exc.value.status_code == 404


def test_list_directory_400_when_target_is_a_file(root):
    with pytest.raises(HTTPException) as exc:
        list_directory(str(root / "a.csv"))
    assert exc.value.status_code == 400


def test_list_directory_entry_metadata(root):
    _, _, entries, _ = list_directory(str(root))
    by_name = {e.name: e for e in entries}
    assert by_name["sub"].is_dir is True
    assert by_name["sub"].size is None
    assert by_name["a.csv"].is_dir is False
    assert by_name["a.csv"].size == len("slide_id\nS1\nS2\nS3\n")
    assert by_name["a.csv"].mtime is not None


# --- GET /api/fs/roots ----------------------------------------------------


def test_roots_endpoint_reports_configured_roots(client, root):
    resp = client.get("/api/fs/roots")
    assert resp.status_code == 200
    assert resp.json()["roots"] == [str(root.resolve())]


# --- GET /api/fs/list -----------------------------------------------------


def test_list_endpoint_returns_entries_and_root_flag(client, root):
    resp = client.get("/api/fs/list", params={"path": str(root)})
    assert resp.status_code == 200
    body = resp.json()
    assert body["is_root"] is True
    assert body["parent"] is None
    assert "sub" in [e["name"] for e in body["entries"]]


def test_list_endpoint_dirs_only_filter(client, root):
    resp = client.get(
        "/api/fs/list", params={"path": str(root), "filter": "dirs_only"}
    )
    assert [e["name"] for e in resp.json()["entries"]] == ["sub"]


def test_list_endpoint_403_outside_roots(client, root, tmp_path):
    resp = client.get("/api/fs/list", params={"path": str(tmp_path / "outside")})
    assert resp.status_code == 403


# --- GET /api/fs/csv-count ------------------------------------------------


def test_csv_count_excludes_the_header_row(client, root):
    resp = client.get("/api/fs/csv-count", params={"path": str(root / "a.csv")})
    assert resp.status_code == 200
    assert resp.json()["rows"] == 3


def test_csv_count_400_when_path_is_a_directory(client, root):
    resp = client.get("/api/fs/csv-count", params={"path": str(root / "sub")})
    assert resp.status_code == 400


def test_csv_count_400_on_non_csv_suffix(client, root):
    resp = client.get(
        "/api/fs/csv-count", params={"path": str(root / "sub" / "leaf.txt")}
    )
    assert resp.status_code == 400


def test_csv_count_403_outside_roots(client, root, tmp_path):
    outside = tmp_path / "outside" / "x.csv"
    outside.write_text("a\n1\n")
    resp = client.get("/api/fs/csv-count", params={"path": str(outside)})
    assert resp.status_code == 403


# --- GET /api/fs/csv-inspect ----------------------------------------------


def test_csv_inspect_detects_slide_id_column_and_samples(client, root):
    resp = client.get("/api/fs/csv-inspect", params={"path": str(root / "a.csv")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["rows"] == 3
    assert body["columns"] == ["slide_id"]
    assert body["has_slide_id"] is True
    assert body["slide_id_column"] == "slide_id"
    assert body["tif_count"] == 0
    assert body["sample_ids"] == ["S1", "S2", "S3"]


def test_csv_inspect_counts_tif_suffixes_for_the_autofix_preview(client, root):
    csv_path = root / "tifs.csv"
    csv_path.write_text("case_id\nA.tif\nB.TIFF\nC\n")
    resp = client.get("/api/fs/csv-inspect", params={"path": str(csv_path)})
    body = resp.json()
    assert body["slide_id_column"] == "case_id"
    assert body["tif_count"] == 2


def test_csv_inspect_reports_missing_slide_id_column(client, root):
    csv_path = root / "nolabel.csv"
    csv_path.write_text("foo,bar\n1,2\n")
    resp = client.get("/api/fs/csv-inspect", params={"path": str(csv_path)})
    body = resp.json()
    assert body["has_slide_id"] is False
    assert body["slide_id_column"] is None
    assert body["sample_ids"] == []


def test_csv_inspect_caps_samples_at_five(client, root):
    csv_path = root / "many.csv"
    csv_path.write_text("slide_id\n" + "\n".join(f"S{i}" for i in range(20)) + "\n")
    resp = client.get("/api/fs/csv-inspect", params={"path": str(csv_path)})
    assert len(resp.json()["sample_ids"]) == 5


def test_csv_inspect_400_on_non_csv(client, root):
    resp = client.get(
        "/api/fs/csv-inspect", params={"path": str(root / "sub" / "leaf.txt")}
    )
    assert resp.status_code == 400
