"""Filesystem cache helpers (v0.3.0).

This module is intentionally small and dependency-light.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


def _safe_stat_size(p: Path) -> int:
    try:
        return int(p.stat().st_size)
    except Exception:
        return 0


@dataclass(frozen=True)
class CacheCleanupResult:
    scanned_files: int
    deleted_files: int
    deleted_dirs: int
    bytes_freed: int


@dataclass(frozen=True)
class CachePruneResult:
    scanned_files: int
    deleted_files: int
    deleted_dirs: int
    bytes_freed: int
    bytes_before: int
    bytes_after: int


def _iter_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return
    for p in root.rglob("*"):
        if p.is_file():
            yield p


def prune_tree_to_max_bytes(
    root: str | Path,
    *,
    max_bytes: int,
    protect_newest: int = 0,
) -> CachePruneResult:
    """Best-effort pruning to keep a cache tree under a maximum size.

    Strategy
    --------
    - Compute total size of all files under *root*.
    - If above *max_bytes*, delete the oldest files first (by mtime), keeping
      the newest *protect_newest* files.
    - Remove empty directories bottom-up.

    Notes
    -----
    - This is intended for *cache* folders (e.g., iv_cache). It is not suitable
      for curated training datasets.
    - Errors are ignored (best-effort).
    """
    root_p = Path(root)
    if max_bytes <= 0:
        return CachePruneResult(0, 0, 0, 0, 0, 0)

    files = list(_iter_files(root_p))
    scanned = len(files)

    sizes = {f: _safe_stat_size(f) for f in files}
    total = sum(sizes.values())
    bytes_before = total

    deleted_files = 0
    deleted_dirs = 0
    freed = 0

    if total <= max_bytes:
        return CachePruneResult(
            scanned_files=scanned,
            deleted_files=0,
            deleted_dirs=0,
            bytes_freed=0,
            bytes_before=bytes_before,
            bytes_after=bytes_before,
        )

    # Oldest-first deletion, optionally protecting newest N
    def _mtime(p: Path) -> float:
        try:
            return float(p.stat().st_mtime)
        except Exception:
            return 0.0

    files_sorted = sorted(files, key=_mtime)  # oldest -> newest
    if protect_newest > 0 and protect_newest < len(files_sorted):
        candidates = files_sorted[: -int(protect_newest)]
    else:
        candidates = files_sorted

    for f in candidates:
        if total <= max_bytes:
            break
        sz = sizes.get(f, 0)
        try:
            f.unlink(missing_ok=True)
            deleted_files += 1
            freed += sz
            total -= sz
        except Exception:
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

    bytes_after = max(0, total)
    return CachePruneResult(
        scanned_files=scanned,
        deleted_files=deleted_files,
        deleted_dirs=deleted_dirs,
        bytes_freed=freed,
        bytes_before=bytes_before,
        bytes_after=bytes_after,
    )


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
