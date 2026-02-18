from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import List, Optional, Tuple
from urllib.parse import urlparse, unquote, parse_qs

from ddgs import DDGS
import requests

from core.llm_analysis.config import AnalysisConfig
from core.llm_analysis.forecast_integration.models import ForecastContext
from core.llm_analysis.web_context.models import QueryPlan, SourceDoc, Snippet
from core.llm_analysis.web_context.normalize import normalize_html_to_text
from core.llm_analysis.web_context.url_cache import load_from_cache, save_to_cache, UrlCacheEntry
import hashlib
from pathlib import Path

from core.llm_analysis.cache.keying import stable_json_hash


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class _DDGLinksParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag != "a":
            return
        attr = dict(attrs)
        href = attr.get("href")
        if not href:
            return
        cls = (attr.get("class") or "")
        if "result__a" in cls or "result__url" in cls or href.startswith("/l/?") or href.startswith("http"):
            self.links.append(href)


def _extract_ddg_result_url(href: str) -> Optional[str]:
    if not href:
        return None

    if href.startswith("//"):
        href = "https:" + href

    if href.startswith("/l/?") or href.startswith("/l/"):
        href = "https://duckduckgo.com" + href

    if href.startswith("http://") or href.startswith("https://"):
        try:
            u = urlparse(href)
            qs = parse_qs(u.query)
            if "uddg" in qs and qs["uddg"]:
                return unquote(qs["uddg"][0])
        except Exception:
            pass
        return href

    return None


def _hostname(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""


def _is_bad_url(url: str) -> bool:
    u = (url or "").lower().strip()
    if not u:
        return True

    bad_hosts = (
        "www.youtube.com",
        "youtube.com",
        "m.youtube.com",
        "www.facebook.com",
        "facebook.com",
        "twitter.com",
        "x.com",
    )
    if _hostname(url) in bad_hosts:
        return True

    bad_prefixes = (
        "https://www.bing.com/aclick",
        "https://bing.com/aclick",
        "https://duckduckgo.com/l/",
        "https://duckduckgo.com/y.js",
        "https://r.search.yahoo.com/",
    )
    if any(u.startswith(p) for p in bad_prefixes):
        return True

    bad_ext = (".pdf", ".zip", ".mp4", ".mp3", ".jpg", ".jpeg", ".png", ".gif", ".webp")
    if any(u.endswith(ext) for ext in bad_ext):
        return True

    return False


def _playground_allowed_host(host: str) -> bool:
    """
    Playground safety/quality guardrail:
    only allow authoritative domains to reduce junk + limit prompt injection surface.
    """
    h = (host or "").lower().strip()
    if not h:
        return False

    # allowlist (minimal)
    if h.endswith(".usgs.gov") or h == "usgs.gov":
        return True
    if h.endswith(".noaa.gov") or h == "noaa.gov":
        return True
    if h == "weather.gov" or h.endswith(".weather.gov"):
        return True

    return False


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\\s*/?>", "\n", html)
    html = re.sub(r"(?is)</p\\s*>", "\n", html)
    html = re.sub(r"(?is)<.*?>", " ", html)
    text = re.sub(r"[ \t\r\f\v]+", " ", html)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _pick_snippets(text: str, max_snippets: int, max_chars: int) -> List[str]:
    if not text:
        return []

    text = text[:max_chars]
    parts = [p.strip() for p in text.split("\n") if len(p.strip()) >= 80]
    parts.sort(key=len, reverse=True)

    picked = []
    for p in parts:
        if len(picked) >= max_snippets:
            break
        picked.append(p[:1200])
    return picked


def ddg_search_urls(
    query: str,
    max_urls: int,
    session: requests.Session,  # kept for signature stability
    timeout_s: int = 20,
) -> List[str]:
    urls: List[str] = []
    seen = set()

    try:
        with DDGS(timeout=timeout_s) as ddgs:
            results = ddgs.text(query, max_results=min(max_urls * 2, 50))
            for r in results:
                u = (r.get("href") or r.get("url") or "").strip()
                if not u:
                    continue
                if not (u.startswith("http://") or u.startswith("https://")):
                    continue
                if u in seen:
                    continue
                seen.add(u)
                urls.append(u)
                if len(urls) >= max_urls:
                    break
    except Exception:
        return []

    return urls


def _extract_title_from_html(html: str) -> Optional[str]:
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    if not m:
        return None
    title = re.sub(r"\s+", " ", m.group(1)).strip()
    return title or None


def fetch_page_text(
    url: str,
    session: requests.Session,
    *,
    timeout_s: int = 20,
    max_chars: int = 12_000,
    url_cache_dir: Path | None = None,
    url_cache_ttl_days: int = 7,
) -> Tuple[str, Optional[str], List[str], bool, int, bool]:
    """
    Fetches a URL and returns a sanitized text representation.

    Returns:
      text, title, flags, truncated, char_count, cache_hit
    """
    # URL cache (optional)
    if url_cache_dir is not None:
        hit = load_from_cache(url_cache_dir, url, ttl_days=url_cache_ttl_days)
        if hit is not None:
            return hit.sanitized_text, hit.title, list(hit.flags), bool(hit.truncated), len(hit.sanitized_text or ""), True

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,pt-BR;q=0.8,pt;q=0.7",
        "Connection": "keep-alive",
    }
    r = session.get(url, headers=headers, timeout=timeout_s, allow_redirects=True)
    r.raise_for_status()

    ct = (r.headers.get("Content-Type") or "").lower()
    if ct and ("text/html" not in ct and "application/xhtml" not in ct):
        return "", None, ["non_html_content_type"], False, 0, False

    html = (r.text or "")[:2_000_000]
    norm = normalize_html_to_text(html, max_chars=max_chars)

    # Save to URL cache (optional)
    if url_cache_dir is not None and norm.text:
        host = (urlparse(url).netloc or "").lower()
        content_hash = hashlib.sha256((norm.text or "").encode("utf-8")).hexdigest()
        entry = UrlCacheEntry(
            url=url,
            host=host,
            retrieved_at_utc=_utc_now_iso(),
            stored_at_epoch=int(time.time()),
            title=norm.title,
            sanitized_text=norm.text,
            content_hash=content_hash,
            flags=list(norm.flags),
            truncated=bool(norm.truncated),
        )
        try:
            save_to_cache(url_cache_dir, entry)
        except Exception:
            # Cache must not break the run
            pass

    return norm.text, norm.title, list(norm.flags), bool(norm.truncated), int(norm.char_count), False



def _round_robin_by_host(candidate_urls: List[Tuple[str, str]], url_budget: int) -> List[Tuple[str, str]]:
    """
    Reorder candidate urls to alternate hosts (simple round-robin).
    This increases diversity and reduces the chance of spending the whole budget on one domain.
    """
    by_host = {}
    for q, u in candidate_urls:
        h = _hostname(u)
        by_host.setdefault(h, []).append((q, u))

    # keep deterministic ordering per host list, then interleave
    hosts = [h for h in by_host.keys() if h] + [h for h in by_host.keys() if not h]

    out: List[Tuple[str, str]] = []
    i = 0
    while len(out) < url_budget and hosts:
        h = hosts[i % len(hosts)]
        if by_host[h]:
            out.append(by_host[h].pop(0))
        if not by_host[h]:
            hosts.remove(h)
            if not hosts:
                break
            i = i % len(hosts)
            continue
        i += 1

    return out


def collect_web_context(
    cfg: AnalysisConfig,
    forecast_ctx: ForecastContext,
    query_plan: QueryPlan,
    cache_root: Path,
) -> Tuple[List[SourceDoc], List[Snippet], int, dict[str, str]]:
    max_pages = int(cfg.page_policy.max_pages)
    dedup = bool(cfg.page_policy.dedup_urls)

    sources: List[SourceDoc] = []
    snippets: List[Snippet] = []
    used_pages = 0

    seen_urls = set()
    mode = (getattr(cfg, "mode", "") or "").lower().strip()

    evidence_text_by_source_id: dict[str, str] = {}
    seen_content_hashes: set[str] = set()

    # URL-level cache (shared across runs)
    url_cache_dir = Path(cache_root) / "web_url_cache"
    ttl_days = 7
    try:
        if cfg.collector_opts and "url_cache_ttl_days" in cfg.collector_opts:
            ttl_days = int(cfg.collector_opts.get("url_cache_ttl_days") or ttl_days)
    except Exception:
        ttl_days = 7


    # NEW: host diversity controls
    host_counts = {}
    max_per_host_full = 4
    max_per_host_playground = 3

    with requests.Session() as sess:
        url_budget = max_pages * 3

        candidate_urls: List[Tuple[str, str]] = []
        for q in query_plan.queries:
            try:
                urls = ddg_search_urls(q, max_urls=min(20, url_budget), session=sess)
            except Exception:
                continue
            for u in urls:
                candidate_urls.append((q, u))
                if len(candidate_urls) >= url_budget:
                    break
            if len(candidate_urls) >= url_budget:
                break

        # NEW: reorder to diversify hosts
        candidate_urls = _round_robin_by_host(candidate_urls, url_budget=url_budget)

        for q, url in candidate_urls:
            if used_pages >= max_pages:
                break

            if _is_bad_url(url):
                continue

            host = _hostname(url)

            # Playground allowlist
            if mode == "playground":
                if not _playground_allowed_host(host):
                    continue

            # NEW: cap per host (applies to all modes)
            cap = max_per_host_playground if mode == "playground" else max_per_host_full
            if host:
                c = host_counts.get(host, 0)
                if c >= cap:
                    continue
                host_counts[host] = c + 1

            if dedup and url in seen_urls:
                continue
            seen_urls.add(url)

            try:
                text, title, flags, truncated, char_count, cache_hit = fetch_page_text(
                    url,
                    session=sess,
                    timeout_s=20,
                    max_chars=int(cfg.page_policy.max_chars_per_page),
                    url_cache_dir=url_cache_dir if cfg.use_cache else None,
                    url_cache_ttl_days=ttl_days,
                )
            except Exception:
                continue

            if not text:
                continue

            used_pages += 1
            retrieved_at = _utc_now_iso()

            # Deduplicate by normalized content hash to reduce near-duplicate sources
            content_hash = hashlib.sha256((text or "").encode("utf-8")).hexdigest()
            if content_hash in seen_content_hashes:
                continue
            seen_content_hashes.add(content_hash)


            source_id = stable_json_hash({"url": url, "retrieved_at": retrieved_at})[:12]
            sources.append(
                SourceDoc(
                    source_id=source_id,
                    url=url,
                    title=title,
                    publisher=host or None,
                    retrieved_at_utc=retrieved_at,
                    published_at_utc=None,
                    host=host or None,
                    content_hash=content_hash,
                    sanitized_char_count=int(char_count),
                    truncated=bool(truncated),
                    flags=list(flags) if flags else [],
                    cache_hit=bool(cache_hit),
                )
            )
            evidence_text_by_source_id[source_id] = text


            snips = _pick_snippets(
                text=text,
                max_snippets=int(cfg.page_policy.max_snippets_per_page),
                max_chars=int(cfg.page_policy.max_chars_per_page),
            )
            for i, s in enumerate(snips, start=1):
                snippet_id = stable_json_hash({"source_id": source_id, "i": i})[:12]
                snippets.append(
                    Snippet(
                        snippet_id=snippet_id,
                        source_id=source_id,
                        url=url,
                        text=s,
                        query=q,
                        start=None,
                        end=None,
                    )
                )

            time.sleep(0.2)

    return sources, snippets, used_pages, evidence_text_by_source_id
