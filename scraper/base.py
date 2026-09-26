"""Scraper base classes: politeness, retries, robots.txt, proxy hooks, kill-switch."""
from __future__ import annotations

import json
import logging
import os
import random
import time
import urllib.robotparser as robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
]

STATUSES = ("success", "failed", "sold_out", "captcha_blocked")


class ProxyProvider(Protocol):
    """Pluggable proxy pool interface. Swap stub for a real pool in production."""

    def get_proxy(self) -> str | None: ...


class NullProxyProvider:
    """Stub: no proxy (direct connection). Acceptable for prototype."""

    def get_proxy(self) -> str | None:
        return None


@dataclass
class Quote:
    """One raw fare quote destined for the raw_fare_quotes staging table."""

    source: str
    origin: str
    destination: str
    carrier: str | None
    advance_purchase_window: int
    scrape_timestamp: datetime
    raw_payload: dict[str, Any]
    status: str = "success"


@dataclass
class ScraperConfig:
    delay_seconds: float = 2.0
    max_retries: int = 3
    backoff_base: float = 2.0
    respect_robots_txt: bool = True
    enabled_sources: dict[str, bool] = field(default_factory=dict)


_ROBOTS_CACHE: dict[str, tuple[float, list[str] | None]] = {}
ROBOTS_CACHE_TTL = 6 * 3600.0
_ROBOTS_CACHE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".robots_cache.json")


def _robots_cache_load() -> None:
    """Load the on-disk robots.txt body cache into memory (TTL-filtered)."""
    try:
        with open(_ROBOTS_CACHE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        now = time.monotonic()
        _ROBOTS_CACHE.update(
            {k: (v[0], v[1]) for k, v in data.items()
             if isinstance(v, list) and len(v) == 2 and now - v[0] < ROBOTS_CACHE_TTL}
        )
    except Exception:
        pass


def _robots_cache_save() -> None:
    try:
        with open(_ROBOTS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump({k: [v[0], v[1]] for k, v in _ROBOTS_CACHE.items()}, f)
    except Exception:
        pass


def _fetch_robots_body(base: str, timeout: float) -> tuple[list[str] | None, bool]:
    """Fetch a host's robots.txt with a browser UA, cached per host for 6h.

    Returns ``(body, from_cache)``: body is the robots.txt lines, or ``None``
    when the fetch failed. A full scrape cycle issues hundreds of runs but only
    a handful of unique hosts — without this cache every run re-downloads
    robots.txt (up to a 10s timeout each for walled hosts), which is both slow
    and needlessly impolite. The cache is persisted to ``.robots_cache.json``
    so restarts don't re-pay the cost either. Failures are cached as ``None``
    so a known-dead host never triggers a repeat network fetch.
    """
    from urllib.request import Request, urlopen

    _robots_cache_load()
    now = time.monotonic()
    hit = _ROBOTS_CACHE.get(base)
    if hit and now - hit[0] < ROBOTS_CACHE_TTL:
        return hit[1], True
    body: list[str] | None = None
    try:
        # Fetch with a stock browser UA: bot-walled hosts (e.g. Ixigo)
        # 403 Python-urllib, which RobotFileParser would treat as
        # disallow-all. A real UA gets the real robots.txt.
        req = Request(f"{base}/robots.txt", headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/126.0.0.0 Safari/537.36",
        })
        with urlopen(req, timeout=timeout) as r:
            body = r.read(100000).decode("utf-8", errors="ignore").splitlines()
    except Exception:
        body = None
    _ROBOTS_CACHE[base] = (now, body)
    _robots_cache_save()
    return body, False


def robots_allowed(page_url: str, user_agent: str = "*", timeout: float = 3.0) -> bool:
    """Check robots.txt for the exact page URL (path-aware, not domain-root only).

    Returns True if allowed/unreachable. A robots.txt that disallows the search
    path (e.g. Ixigo ``/search/result/``) correctly returns False even when the
    homepage itself is allowed.
    """
    import socket
    from urllib.parse import urlparse

    prev = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        parsed = urlparse(page_url)
        base = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else page_url.rstrip("/")
        rp = robotparser.RobotFileParser()
        rp.set_url(f"{base}/robots.txt")
        body, from_cache = _fetch_robots_body(base, timeout)
        if body:
            try:
                rp.parse(body)
            except Exception:
                rp.read()  # fallback to default fetch
        elif body is None and not from_cache:
            # Fresh fetch failure — one fallback attempt with the default UA.
            # A cached failure (None from cache) skips this entirely.
            try:
                rp.read()
            except Exception:
                rp.parse([])  # both fetches failed: empty rules = allow (fail open)
        else:
            # Cached failure or empty body: no rules = allow all (fail open).
            # parse([]) matters — a completely unparsed parser answers
            # can_fetch() = False (disallow-all), which would wrongly park
            # every walled host. Never hit the network on this path.
            rp.parse([])
        try:
            if not rp.can_fetch(user_agent, page_url):
                return False
        except Exception:
            pass
        # Safety net: stdlib RobotFileParser mishandles some real-world files
        # (e.g. Ixigo's `Disallow: *-lp-*` lines drop the `*` group, leaving
        # default_entry None and can_fetch() True for everything). Do a minimal
        # manual prefix check of the `User-agent: *` group so a disallowed
        # search path can never slip through.
        if body and _manual_star_disallowed(body, urlparse(page_url).path or "/"):
            return False
        return True
    except Exception as exc:  # network failure -> allow but log
        log.warning("robots.txt check failed for %s: %s (defaulting to allowed)", page_url, exc)
        return True
    finally:
        socket.setdefaulttimeout(prev)


def _manual_star_disallowed(robots_lines: list[str], path: str) -> bool:
    """Minimal `User-agent: *` Disallow prefix check (stdlib-parser safety net).

    Handles plain prefixes (``/search/result/``), trailing-``*`` prefixes and
    ``$`` end-anchors; ignores non-prefix wildcard lines (``*-lp-*``) which
    only apply to URL patterns, not to the path being tested here.
    """
    import fnmatch

    in_star = False
    for raw in robots_lines:
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            if not line:
                continue
            continue
        key, _, val = line.partition(":")
        key, val = key.strip().lower(), val.strip()
        if key == "user-agent":
            in_star = val == "*"
        elif key == "disallow" and in_star and val:
            if not val.startswith("/"):
                continue  # pattern fragment (e.g. *-lp-*), not a path prefix
            if val.endswith("$"):
                if path == val[:-1] or path.rstrip("/") == val[:-1].rstrip("/"):
                    return True
            elif val.endswith("*"):
                if path.startswith(val[:-1]):
                    return True
            else:
                if path.startswith(val):
                    return True
    _ = fnmatch  # reserved for full wildcard support if needed later
    return False


class BaseScraper(ABC):
    """Common behaviour for all source scrapers (Scrapy or Playwright subclasses)."""

    source: str = "base"
    start_url: str = ""
    requires_js: bool = False

    def __init__(self, config: ScraperConfig, proxy_provider: ProxyProvider | None = None):
        self.config = config
        self.proxy = proxy_provider or NullProxyProvider()
        self._proxy: str | None = None  # active failover proxy (set after a 40x)

    def proxy_for_playwright(self) -> dict[str, str] | None:
        """Proxy option for ``playwright launch(proxy=...)``; supports socks4/5/http."""
        return {"server": self._proxy} if self._proxy else None

    def proxy_dict(self) -> dict[str, str] | None:
        """Requests-style ``{"http": ..., "https": ...}`` mapping for the active proxy."""
        if not self._proxy:
            return None
        return {"http": self._proxy, "https": self._proxy}

    @property
    def enabled(self) -> bool:
        """Kill-switch: disabled source returns False instantly."""
        return self.config.enabled_sources.get(self.source, True)

    def pick_user_agent(self) -> str:
        """Rotate User-Agents per request."""
        return random.choice(USER_AGENTS)

    def polite_wait(self) -> None:
        time.sleep(self.config.delay_seconds)

    def robots_target(self, *args, **kwargs) -> str:
        """Exact URL the run will fetch (path-aware robots check). Overridden below."""
        return self.start_url

    def check_robots(self, target_url: str | None = None) -> bool:
        """Return False (and log) if robots.txt disallows the target URL."""
        if not self.config.respect_robots_txt:
            return True
        url = target_url or self.start_url
        if not url:
            return True
        allowed = robots_allowed(url)
        if not allowed:
            log.warning("[%s] robots.txt disallows scraping %s — skipping", self.source, url)
        return allowed

    def run_with_retry(self, *args, proxy_pool: ProxyProvider | None = None, **kwargs) -> list[Quote]:
        """Retry with exponential backoff; CAPTCHA/sold-out are graceful statuses, not crashes.

        On HTTP 40x (``BlockedByStatus`` — our IP is blocked/rate-limited), fail
        over once to the fastest proxy from ``proxy_pool`` (or ``self.proxy``
        if it yields one) and retry through it. Live spider implementations
        must route via ``self.proxy_for_playwright()`` / ``self.proxy_dict()``
        for the retry to actually use the proxy.
        """
        pool = proxy_pool or (self.proxy if not isinstance(self.proxy, NullProxyProvider) else None)
        failed_over = False
        last: Exception | None = None
        for attempt in range(self.config.max_retries):
            try:
                return self.scrape(*args, **kwargs)
            except CaptchaBlocked as exc:
                log.warning("[%s] CAPTCHA blocked: %s", self.source, exc)
                return [self._quote(*args, status="captcha_blocked", payload={"error": str(exc)}, **kwargs)]
            except SoldOut as exc:
                log.info("[%s] sold out: %s", self.source, exc)
                return [self._quote(*args, status="sold_out", payload={"info": str(exc)}, **kwargs)]
            except BlockedByStatus as exc:
                last = exc
                if 400 <= exc.status < 500 and not failed_over and pool is not None:
                    nxt = pool.get_proxy()
                    if nxt:
                        failed_over = True
                        self._proxy = nxt
                        log.warning(
                            "[%s] HTTP %d from own IP — failing over to proxy %s",
                            self.source, exc.status, nxt,
                        )
                        continue
                log.warning("[%s] blocked (HTTP %d), no proxy failover available", self.source, exc.status)
            except SelectorNotFound as exc:
                log.warning("[%s] selector not found (site changed?): %s", self.source, exc)
                last = exc
            except Exception as exc:  # noqa: BLE001
                log.warning("[%s] attempt %d failed: %s", self.source, attempt + 1, exc)
                last = exc
            if attempt < self.config.max_retries - 1:
                time.sleep(self.config.backoff_base ** attempt)
        log.error("[%s] all retries exhausted: %s", self.source, last)
        return [self._quote(*args, status="failed", payload={"error": str(last)}, **kwargs)]

    def guarded_run(self, *args, proxy_pool: ProxyProvider | None = None, **kwargs) -> list[Quote]:
        """Kill-switch + path-aware robots gate around run_with_retry."""
        if not self.enabled:
            log.info("[%s] disabled via kill-switch — skipping", self.source)
            return []
        try:
            target = self.robots_target(*args, **kwargs)
        except Exception:
            target = self.start_url
        if not self.check_robots(target):
            return [self._quote(*args, status="failed", payload={"error": "robots_disallowed"}, **kwargs)]
        self.polite_wait()
        return self.run_with_retry(*args, proxy_pool=proxy_pool, **kwargs)

    def _quote(self, origin, destination, window, status="success", payload=None, **_) -> Quote:
        return Quote(
            source=self.source,
            origin=origin,
            destination=destination,
            carrier=None,
            advance_purchase_window=window,
            scrape_timestamp=datetime.now(timezone.utc),
            raw_payload=payload or {},
            status=status,
        )

    @abstractmethod
    def scrape(self, origin: str, destination: str, window: int) -> list[Quote]:
        """Fetch quotes for one route+window. Subclasses use Scrapy or Playwright here."""
        raise NotImplementedError


class CaptchaBlocked(Exception):
    pass


class SoldOut(Exception):
    pass


class BlockedByStatus(Exception):
    """HTTP 4xx returned for our own IP (e.g. 403 Forbidden, 429 Too Many Requests).

    Spider implementations should raise this when a response status indicates
    IP-based blocking. ``BaseScraper`` then fails over to a pooled proxy and
    retries once through it instead of hammering the site directly.
    """

    def __init__(self, status: int, url: str = ""):
        super().__init__(f"HTTP {status} for {url}")
        self.status = status
        self.url = url


class SelectorNotFound(Exception):
    """Raised when a CSS/XPath selector no longer matches (site structure changed)."""

    def __init__(self, spider: str, selector: str):
        super().__init__(f"spider={spider} selector={selector!r} not found")
        self.spider = spider
        self.selector = selector
