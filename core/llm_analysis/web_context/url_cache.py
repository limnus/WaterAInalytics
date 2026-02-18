from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


@dataclass(frozen=True)
class UrlCacheEntry:
    url: str
    host: str
    retrieved_at_utc: str
    stored_at_epoch: int
    title: str | None
    sanitized_text: str
    content_hash: str
    flags: list[str]
    truncated: bool


def _url_key(url: str) -> str:
    h = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return h[:32]


def _now_epoch() -> int:
    return int(time.time())


def load_from_cache(cache_dir: Path, url: str, *, ttl_days: int) -> Optional[UrlCacheEntry]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _url_key(url)
    meta_path = cache_dir / f"{key}.json"
    txt_path = cache_dir / f"{key}.txt"
    if not meta_path.exists() or not txt_path.exists():
        return None

    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        stored_at = int(meta.get("stored_at_epoch") or 0)
        if ttl_days > 0:
            max_age = ttl_days * 86400
            if stored_at and (_now_epoch() - stored_at) > max_age:
                return None

        sanitized_text = txt_path.read_text(encoding="utf-8")
        return UrlCacheEntry(
            url=meta["url"],
            host=meta.get("host") or "",
            retrieved_at_utc=meta.get("retrieved_at_utc") or "",
            stored_at_epoch=stored_at,
            title=meta.get("title"),
            sanitized_text=sanitized_text,
            content_hash=meta.get("content_hash") or "",
            flags=list(meta.get("flags") or []),
            truncated=bool(meta.get("truncated") or False),
        )
    except Exception:
        return None


def save_to_cache(cache_dir: Path, entry: UrlCacheEntry) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _url_key(entry.url)
    meta_path = cache_dir / f"{key}.json"
    txt_path = cache_dir / f"{key}.txt"

    meta = {
        "url": entry.url,
        "host": entry.host,
        "retrieved_at_utc": entry.retrieved_at_utc,
        "stored_at_epoch": entry.stored_at_epoch,
        "title": entry.title,
        "content_hash": entry.content_hash,
        "flags": entry.flags,
        "truncated": entry.truncated,
    }
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    txt_path.write_text(entry.sanitized_text or "", encoding="utf-8")
