"""Tests: proxy list parsing/ranking, 40x -> proxy failover, DB persistence."""
import pytest

from scraper.base import BlockedByStatus, ProxyProvider, ScraperConfig
from scraper.spiders import MockableScraper
from scraper.proxies import parse_proxy_list, rank_proxies

SAMPLE = """
socks5://1.2.3.4:1080
socks4://5.6.7.8:5678
https://9.9.9.9:443
http://8.8.8.8:8080

not-a-proxy
socks5://1.2.3.4:1080
"""


def test_parse_proxy_list():
    out = parse_proxy_list(SAMPLE)
    # dup removed, junk/blank skipped, https:// normalized to http://
    assert out == [
        "socks5://1.2.3.4:1080",
        "socks4://5.6.7.8:5678",
        "http://9.9.9.9:443",
        "http://8.8.8.8:8080",
    ]


def test_rank_proxies_orders_by_latency_and_drops_dead():
    results = {"a": 300.0, "b": None, "c": 50.0, "d": 150.0}
    assert rank_proxies(results) == [("c", 50.0), ("d", 150.0), ("a", 300.0)]


class StubPool(ProxyProvider):
    def __init__(self):
        self.calls = 0

    def get_proxy(self):
        self.calls += 1
        return "http://9.9.9.9:8080"


class FlakySpider(MockableScraper):
    source = "flaky_test"
    start_url = ""

    def scrape(self, origin, destination, window):
        if self._proxy is None:
            raise BlockedByStatus(403, url="https://example.com/search")
        assert self.proxy_for_playwright() == {"server": "http://9.9.9.9:8080"}
        assert self.proxy_dict() == {"http": "http://9.9.9.9:8080", "https": "http://9.9.9.9:8080"}
        from scraper.spiders import mock_quote
        return [mock_quote(self.source, origin, destination, window)]


def test_40x_fails_over_to_proxy_once():
    cfg = ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                        enabled_sources={"flaky_test": True})
    pool = StubPool()
    quotes = FlakySpider(cfg).guarded_run("DEL", "BOM", 7, proxy_pool=pool)
    assert quotes and quotes[0].status == "success"
    assert pool.calls == 1  # exactly one failover, not a retry storm


def test_40x_without_pool_returns_failed():
    cfg = ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                        enabled_sources={"flaky_test": True})
    quotes = FlakySpider(cfg).guarded_run("DEL", "BOM", 7)
    assert quotes and quotes[0].status == "failed"


def test_proxy_db_roundtrip():
    """Upsert + fastest-first ordering (needs local Postgres; skipped otherwise)."""
    import sqlalchemy as sa
    from sqlalchemy import text

    try:
        eng = sa.create_engine("postgresql+psycopg://postgres:postgres@localhost:5432/postgres",
                               connect_args={"connect_timeout": 2})
        with eng.connect():
            pass
    except Exception:
        pytest.skip("no local Postgres available")
        return
    from scraper.proxies import ensure_proxy_table, fastest_proxies, store_results
    try:
        ensure_proxy_table(eng)
        with eng.begin() as c:
            c.execute(text("DELETE FROM proxies WHERE endpoint LIKE 'test://%'"))
        store_results(eng, {"test://slow:1": 900.0, "test://fast:2": 100.0, "test://dead:3": None})
        assert fastest_proxies(eng, 5)[:2] == ["test://fast:2", "test://slow:1"]
    finally:
        with eng.begin() as c:
            c.execute(text("DELETE FROM proxies WHERE endpoint LIKE 'test://%'"))
        eng.dispose()
