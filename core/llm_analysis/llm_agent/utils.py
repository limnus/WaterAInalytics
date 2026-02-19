from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def sha256_text(s: str) -> str:
    h = hashlib.sha256()
    h.update(s.encode("utf-8"))
    return h.hexdigest()


def sha256_json(obj: Any) -> str:
    # Stable JSON encoding: sorted keys, no whitespace
    s = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256_text(s)


def clamp_text(s: str, max_chars: int) -> str:
    s = s or ""
    if len(s) <= max_chars:
        return s
    return s[: max_chars - 20] + "\n\n[TRUNCATED]"


def safe_json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2)


def try_parse_json(s: str) -> Dict[str, Any] | None:
    try:
        return json.loads(s)
    except Exception:
        return None
