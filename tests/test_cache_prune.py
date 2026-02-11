from __future__ import annotations

from pathlib import Path

from core.utils.fs_cache import prune_tree_to_max_bytes


def test_prune_tree_to_max_bytes_deletes_oldest(tmp_path: Path):
    root = tmp_path / "cache"
    root.mkdir()

    # Create 3 files with increasing mtimes
    files = []
    for i in range(3):
        p = root / f"f{i}.bin"
        p.write_bytes(b"x" * 100)
        files.append(p)

    # Touch mtimes to ensure ordering (oldest f0)
    for i, p in enumerate(files):
        p.touch()

    # Cap below total (300), but above 200 => delete at least one file
    res = prune_tree_to_max_bytes(root, max_bytes=210, protect_newest=0)
    assert res.bytes_before >= 300
    assert res.bytes_after <= 210
    assert res.deleted_files >= 1


def test_prune_protect_newest(tmp_path: Path):
    root = tmp_path / "cache"
    root.mkdir()

    # 5 files of 100 bytes
    for i in range(5):
        (root / f"f{i}.bin").write_bytes(b"x" * 100)

    # Protect newest 2 files; prune to 250 => should delete 3
    res = prune_tree_to_max_bytes(root, max_bytes=250, protect_newest=2)
    assert res.deleted_files >= 2
    # Ensure at least 2 files remain
    remaining = list(root.rglob("*.bin"))
    assert len(remaining) >= 2
