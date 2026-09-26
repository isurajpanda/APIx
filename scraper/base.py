"""Scraper base classes: politeness, retries, robots.txt, proxy hooks, kill-switch."""
from __future__ import annotations

import json
import logging
import random
import time
import urllib.robotparser as robotparser
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol

log = logging.getLogger(__name__)

USER_AGENTS = [
    "Mozilla/5.0 (X11; Linux x86_64) APIx-MoSPI-Research/1.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 APIx/1.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) APIx-Research-Bot/1.0 (+https://mospi.gov.in)",
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


def robots_allowed(domain_url: str, user_agent: str = "*", timeout: float = 5.0) -> bool:
    """Check robots.txt before scraping a domain. Returns True if allowed/unreachable."""
    import socket

    prev = socket.getdefaulttimeout()
    socket.setdefaulttimeout(timeout)
    try:
        rp = robotparser.RobotFileParser()
        base = domain_url.rstrip("/")
        rp.set_url(f"{base}/robots.txt")
        rp.read()
        return rp.can_fetch(user_agent, base + "/")
    except Exception as exc:  # network failure -> allow but log
        log.warning("robots.txt check failed for %s: %s (defaulting to allowed)", domain_url, exc)
        return True
    finally:
        socket.setdefaulttimeout(prev)


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

    def check_robots(self) -> bool:
        """Return False (and log) if robots.txt disallows this source."""
        if not self.config.respect_robots_txt or not self.start_url:
            return True
        domain = "/".join(self.start_url.split("/")[:3])
        allowed = robots_allowed(domain)
        if not allowed:
            log.warning("[%s] robots.txt disallows scraping %s — skipping", self.source, domain)
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
            time.sleep(self.config.backoff_base ** attempt)
        log.error("[%s] all retries exhausted: %s", self.source, last)
        return [self._quote(*args, status="failed", payload={"error": str(last)}, **kwargs)]

    def guarded_run(self, *args, proxy_pool: ProxyProvider | None = None, **kwargs) -> list[Quote]:
        """Kill-switch + robots gate around run_with_retry."""
        if not self.enabled:
            log.info("[%s] disabled via kill-switch — skipping", self.source)
            return []
        if not self.check_robots():
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
