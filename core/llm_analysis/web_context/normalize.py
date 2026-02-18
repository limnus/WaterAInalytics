from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import List, Optional, Tuple


_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?(previous|prior)\s+instructions",
    r"disregard\s+(all\s+)?(previous|prior)\s+instructions",
    r"system\s+prompt",
    r"developer\s+message",
    r"you\s+are\s+chatgpt",
    r"jailbreak",
    r"do\s+not\s+follow\s+the\s+above",
    r"follow\s+these\s+instructions",
    r"execute\s+the\s+following",
    r"tool\s+call",
    r"function\s+call",
]


@dataclass(frozen=True)
class NormalizedDoc:
    text: str
    title: Optional[str]
    flags: List[str]
    truncated: bool
    char_count: int


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: List[str] = []
        self._in_script_style = 0
        self._in_title = 0
        self._title_chunks: List[str] = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t in ("script", "style", "noscript"):
            self._in_script_style += 1
        if t == "title":
            self._in_title += 1

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ("script", "style", "noscript") and self._in_script_style > 0:
            self._in_script_style -= 1
        if t == "title" and self._in_title > 0:
            self._in_title -= 1

    def handle_data(self, data):
        if not data:
            return
        if self._in_title > 0:
            self._title_chunks.append(data)
            return
        if self._in_script_style > 0:
            return
        self._chunks.append(data)

    def get_text(self) -> str:
        return " ".join(self._chunks)

    def get_title(self) -> Optional[str]:
        title = " ".join(self._title_chunks)
        title = re.sub(r"\s+", " ", title).strip()
        return title or None


def _truncate_head_tail(text: str, max_chars: int) -> Tuple[str, bool]:
    if max_chars <= 0:
        return "", bool(text)
    if len(text) <= max_chars:
        return text, False
    # Stable head+tail to keep both context and references/footer
    head = int(max_chars * 0.66)
    tail = max_chars - head
    truncated = text[:head].rstrip() + "\n…\n" + text[-tail:].lstrip()
    return truncated, True


def detect_prompt_injection(text: str) -> List[str]:
    if not text:
        return []
    lower = text.lower()
    flags: List[str] = []
    for pat in _INJECTION_PATTERNS:
        if re.search(pat, lower, flags=re.IGNORECASE):
            flags.append("prompt_injection_suspected")
            break
    # Additional heuristic: references to roles/prompts/tools often correlate with injection
    if re.search(r"\b(system|developer|assistant)\b.{0,40}\b(prompt|instruction)\b", lower):
        if "prompt_injection_suspected" not in flags:
            flags.append("prompt_injection_suspected")
    return flags


def normalize_html_to_text(
    html: str,
    *,
    max_chars: int = 12_000,
) -> NormalizedDoc:
    html = html or ""
    html = html[:2_000_000]  # hard cap for safety

    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        # best-effort: strip tags
        raw = re.sub(r"<[^>]+>", " ", html)
        raw = re.sub(r"\s+", " ", raw).strip()
        text, truncated = _truncate_head_tail(raw, max_chars=max_chars)
        flags = detect_prompt_injection(text)
        return NormalizedDoc(text=text, title=None, flags=flags + ["html_parse_fallback"], truncated=truncated, char_count=len(text))

    raw_text = parser.get_text()
    raw_text = re.sub(r"\s+", " ", raw_text).strip()

    # Re-insert some structure cues: split on sentence-ish punctuation to reduce mega-paragraphs
    raw_text = re.sub(r"([\.\!\?])\s+", r"\1\n", raw_text)

    text, truncated = _truncate_head_tail(raw_text, max_chars=max_chars)
    flags = detect_prompt_injection(text)

    return NormalizedDoc(
        text=text,
        title=parser.get_title(),
        flags=flags,
        truncated=truncated,
        char_count=len(text),
    )
