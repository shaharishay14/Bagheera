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


@dataclass(frozen=True)
class Settings:
    allowed_roots: list[Path] = field(default_factory=list)
    trident_repo_path: str = ""
    trident_python: str = "python"
    panther_repo_path: str = ""
    db_path: str = "./bagheera.db"
    cors_origins: list[str] = field(default_factory=lambda: ["http://localhost:5173"])


def load_settings() -> Settings:
    return Settings(
        allowed_roots=_parse_roots(os.environ.get("TRIDENT_ALLOWED_ROOTS")),
        trident_repo_path=os.environ.get("TRIDENT_REPO_PATH", ""),
        trident_python=os.environ.get("TRIDENT_PYTHON", "python"),
        panther_repo_path=os.environ.get("PANTHER_REPO_PATH", ""),
        db_path=os.environ.get("BAGHEERA_DB_PATH", "./bagheera.db"),
    )


settings = load_settings()
