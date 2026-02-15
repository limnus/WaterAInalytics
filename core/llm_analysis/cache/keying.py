from __future__ import annotations

import hashlib
import json
from typing import Any, Dict


def stable_json_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def stable_json_hash(obj: Any, algo: str = "sha256") -> str:
    s = stable_json_dumps(obj).encode("utf-8")
    h = hashlib.new(algo)
    h.update(s)
    return h.hexdigest()


def build_cache_key(payload: Dict[str, Any]) -> str:
    return stable_json_hash(payload)
