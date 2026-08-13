"""Safe filesystem listing constrained to ALLOWED_ROOTS."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from fastapi import HTTPException, status

from app.config import settings
from app.models.schemas import FsEntry


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def resolve_within_roots(raw_path: str) -> Path:
    """Resolve ``raw_path`` and require it to live inside an allowed root.

    Resolves symlinks (``Path.resolve()``), so symlink escapes are blocked too.
    """
    if not settings.allowed_roots:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="No allowed roots configured. Set TRIDENT_ALLOWED_ROOTS.",
        )

    try:
        resolved = Path(raw_path).expanduser().resolve()
    except (OSError, RuntimeError) as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Bad path: {exc}")

    if not any(_is_within(resolved, root) or resolved == root for root in settings.allowed_roots):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path is outside the allowed roots.",
        )
    return resolved


def is_at_root(resolved: Path) -> bool:
    return any(resolved == root for root in settings.allowed_roots)


def list_directory(
    raw_path: str | None,
    *,
    show_hidden: bool = False,
    dirs_only: bool = False,
) -> tuple[Path, Path | None, list[FsEntry], bool]:
    """Return ``(path, parent, entries, is_root)`` for the requested directory.

    When ``raw_path`` is ``None`` we surface the first configured root. The
    frontend uses ``/api/fs/roots`` to discover the full list.
    """
    if raw_path is None:
        if not settings.allowed_roots:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="No allowed roots configured. Set TRIDENT_ALLOWED_ROOTS.",
            )
        target = settings.allowed_roots[0]
    else:
        target = resolve_within_roots(raw_path)

    try:
        if not target.exists():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found.")
        if not target.is_dir():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Not a directory.")
        raw_entries = list(target.iterdir())
    except PermissionError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied.")
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Path not found.")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list directory: {exc.strerror or exc}",
        )

    entries = list(_to_entries(raw_entries, show_hidden=show_hidden, dirs_only=dirs_only))
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))

    at_root = is_at_root(target)
    parent: Path | None = None if at_root else target.parent
    return target, parent, entries, at_root


def _to_entries(
    raw_entries: Iterable[Path], *, show_hidden: bool, dirs_only: bool
) -> Iterable[FsEntry]:
    for entry in raw_entries:
        if not show_hidden and entry.name.startswith("."):
            continue
        try:
            is_dir = entry.is_dir()
        except OSError:
            continue
        if dirs_only and not is_dir:
            continue
        size: int | None = None
        mtime: datetime | None = None
        try:
            stat = entry.stat()
            size = None if is_dir else stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime)
        except OSError:
            pass
        yield FsEntry(
            name=entry.name,
            path=str(entry),
            is_dir=is_dir,
            size=size,
            mtime=mtime,
        )
