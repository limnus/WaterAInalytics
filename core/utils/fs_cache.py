"""Filesystem cache helpers (v0.3.0).

This module is intentionally small and dependency-light.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class CacheCleanupResult:
    scanned_files: int
    deleted_files: int
    deleted_dirs: int
    bytes_freed: int


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def cleanup_tree_older_than(
    root: str | Path,
    *,
    older_than_days: int = 30,
    now: datetime | None = None,
) -> CacheCleanupResult:
    """Delete files under *root* older than N days (by mtime).

    Notes
    -----
    - Directories are removed if empty after file deletions.
    - Errors are ignored (best-effort cleanup).
    """
    root_p = Path(root)
    if now is None:
        now = datetime.now(timezone.utc)

    threshold = now - timedelta(days=int(older_than_days))

    scanned = 0
    deleted_files = 0
    deleted_dirs = 0
    freed = 0

    for f in _iter_files(root_p):
        scanned += 1
        try:
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
        except Exception:
            continue

        if mtime >= threshold:
            continue

        try:
            freed += int(f.stat().st_size)
        except Exception:
            pass

        try:
            f.unlink(missing_ok=True)
            deleted_files += 1
        except Exception:
            # best effort
            continue

    # Remove empty dirs bottom-up
    if root_p.exists():
        for d in sorted([p for p in root_p.rglob("*") if p.is_dir()], reverse=True):
            try:
                if not any(d.iterdir()):
                    d.rmdir()
                    deleted_dirs += 1
            except Exception:
                continue

    return CacheCleanupResult(
        scanned_files=scanned,
        deleted_files=deleted_files,
        deleted_dirs=deleted_dirs,
        bytes_freed=freed,
    )
