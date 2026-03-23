from __future__ import annotations

import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ENV_PATH = PROJECT_ROOT / ".env"

_INLINE_COMMENT_RE = re.compile(r"\s+#.*$")


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def _parse_env_line(raw_line: str) -> tuple[str, str] | None:
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.startswith("export "):
        line = line[len("export "):].strip()
    if "=" not in line:
        return None

    key, value = line.split("=", 1)
    key = key.strip()
    if not key:
        return None

    value = value.strip()
    if value and value[0] not in {'"', "'"}:
        value = _INLINE_COMMENT_RE.sub("", value).rstrip()
    value = _strip_quotes(value)
    return key, value


@lru_cache(maxsize=4)
def load_project_env(env_path: str | Path | None = None, *, override: bool = False) -> Path:
    """Load key/value pairs from the project .env file into os.environ.

    The loader is intentionally lightweight to avoid adding a dependency on
    python-dotenv at this stage.
    """
    path = Path(env_path) if env_path else DEFAULT_ENV_PATH
    if not path.exists() or not path.is_file():
        return path

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        parsed = _parse_env_line(raw_line)
        if parsed is None:
            continue
        key, value = parsed
        if override or key not in os.environ:
            os.environ[key] = value
    return path


@dataclass(frozen=True)
class RuntimeSettings:
    auth_admin_initial_password: str
    auth_admin_reset_password: str
    playground_report_truncation_ratio: float
    session_timeout_minutes: int
    station_context_enrichment_enabled: bool
    station_context_timeout_s: int
    station_context_cache_days: int


def _get_float(name: str, default: float, *, min_value: float, max_value: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))




def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")

def _get_int(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return max(min_value, min(max_value, value))


@lru_cache(maxsize=1)
def get_runtime_settings() -> RuntimeSettings:
    load_project_env()
    return RuntimeSettings(
        auth_admin_initial_password=os.getenv("AUTH_ADMIN_INITIAL_PASSWORD", "").strip(),
        auth_admin_reset_password=os.getenv("AUTH_ADMIN_RESET_PASSWORD", "").strip(),
        playground_report_truncation_ratio=_get_float(
            "PLAYGROUND_REPORT_TRUNCATION_RATIO",
            0.60,
            min_value=0.05,
            max_value=1.00,
        ),
        session_timeout_minutes=_get_int(
            "SESSION_TIMEOUT_MINUTES",
            60,
            min_value=5,
            max_value=24 * 60,
        ),
        station_context_enrichment_enabled=_get_bool("STATION_CONTEXT_ENRICHMENT_ENABLED", True),
        station_context_timeout_s=_get_int(
            "STATION_CONTEXT_TIMEOUT_S",
            15,
            min_value=3,
            max_value=120,
        ),
        station_context_cache_days=_get_int(
            "STATION_CONTEXT_CACHE_DAYS",
            14,
            min_value=1,
            max_value=180,
        ),
    )
