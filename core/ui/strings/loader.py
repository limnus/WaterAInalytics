"""core/ui/strings/loader.py

Simple i18n loader:
- Persist language selection in .config/lang.txt
- Provide get_lang(), set_lang(), get_strings(), SUPPORTED

Run self-test:
  python -m core.ui.strings.loader
  python core/ui/strings/loader.py
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Allow running as a script: ensure project root on sys.path
ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONFIG_DIR = Path(".config")
LANG_FILE = CONFIG_DIR / "lang.txt"

SUPPORTED = {
    "en": ("English", "core.ui.strings.en"),
    "fr": ("Français", "core.ui.strings.fr"),
    "pt_br": ("Português (Brasil)", "core.ui.strings.pt_br"),
}

DEFAULT_LANG = "en"


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def get_lang() -> str:
    _ensure_config_dir()
    if LANG_FILE.exists():
        code = LANG_FILE.read_text(encoding="utf-8").strip()
        if code in SUPPORTED:
            return code
    return DEFAULT_LANG


def set_lang(code: str) -> None:
    if code not in SUPPORTED:
        raise ValueError(f"Unsupported language: {code}")
    _ensure_config_dir()
    LANG_FILE.write_text(code, encoding="utf-8")


def import_strings(code: str) -> Any:
    import importlib
    mod_path = SUPPORTED[code][1]
    return importlib.import_module(mod_path)


@dataclass(frozen=True)
class Strings:
    m: Any
    def __getattr__(self, item: str) -> Any:
        return getattr(self.m, item)


def get_strings() -> Strings:
    code = get_lang()
    return Strings(import_strings(code))


def _self_test() -> int:
    print("Running core/ui/strings/loader.py self-test...")
    old = get_lang()
    try:
        for code in SUPPORTED.keys():
            set_lang(code)
            assert get_lang() == code
            s = get_strings()
            assert hasattr(s, "APP_TITLE")
            assert hasattr(s, "BTN_LOGIN")
            assert hasattr(s, "INFO_LOADING")
    finally:
        set_lang(old)
    print("Self-test PASSED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(_self_test())
