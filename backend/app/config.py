"""Runtime configuration loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _parse_roots(raw: str | None) -> list[Path]:
    if not raw:
        # Local-dev fallback: user's home directory. Document loudly that production must override.
        return [Path.home().resolve()]
    roots: list[Path] = []
    for chunk in raw.split(":"):
        chunk = chunk.strip()
        if not chunk:
            continue
        roots.append(Path(chunk).expanduser().resolve())
    return roots


def _resolve_dir(raw: str | None, default: str) -> Path:
    value = (raw or default).strip()
    return Path(value).expanduser().resolve()


@dataclass(frozen=True)
class Settings:
    allowed_roots: list[Path] = field(default_factory=list)
    trident_repo_path: str = ""
    trident_python: str = "python"
    panther_repo_path: str = ""
    db_path: str = "./bagheera.db"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])

    # New for inference + viz cache
    datasets_splits_root: Path = field(default_factory=lambda: Path("./datasets_splits").resolve())
    viz_cache_root: Path = field(default_factory=lambda: Path("./viz_cache").resolve())
    inference_root: Path = field(default_factory=lambda: Path("./inference_outputs").resolve())


def load_settings() -> Settings:
    panther_repo_path = os.environ.get("PANTHER_REPO_PATH", "")
    default_splits_root = (
        str(Path(panther_repo_path) / "src" / "datasets_splits")
        if panther_repo_path
        else "./datasets_splits"
    )
    return Settings(
        allowed_roots=_parse_roots(os.environ.get("TRIDENT_ALLOWED_ROOTS")),
        trident_repo_path=os.environ.get("TRIDENT_REPO_PATH", ""),
        trident_python=os.environ.get("TRIDENT_PYTHON", "python"),
        panther_repo_path=panther_repo_path,
        db_path=os.environ.get("BAGHEERA_DB_PATH", "./bagheera.db"),
        datasets_splits_root=_resolve_dir(
            os.environ.get("DATASETS_SPLITS_ROOT"), default_splits_root
        ),
        viz_cache_root=_resolve_dir(os.environ.get("VIZ_CACHE_ROOT"), "./viz_cache"),
        inference_root=_resolve_dir(os.environ.get("INFERENCE_ROOT"), "./inference_outputs"),
    )


settings = load_settings()


def ensure_storage_dirs() -> None:
    """Create the cache directories at boot if they don't exist."""
    for d in (settings.viz_cache_root, settings.inference_root):
        d.mkdir(parents=True, exist_ok=True)
    (settings.viz_cache_root / "job_logs").mkdir(parents=True, exist_ok=True)


# TODO: add an /api/admin/cleanup endpoint (or scripts/cleanup.py) that
# purges old job logs and orphaned viz/inference outputs once these dirs
# start growing past comfort. For now, both grow unbounded — operators
# should periodically prune by hand (`find ./viz_cache/job_logs -mtime +30
# -delete` and similar) or wire up a cron.
