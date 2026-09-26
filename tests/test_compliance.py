"""Compliance tests: path-aware robots gate, Ixigo parked, provider registry."""
import os

from scraper import spiders
from scraper.base import ScraperConfig, robots_allowed
from scraper.form_flows import PROVIDERS, get_provider


def test_robots_check_is_path_aware(monkeypatch):
    seen = {}

    def fake_can_fetch(self, ua, url):
        seen["url"] = url
        return "/search/result/" not in url

    monkeypatch.setattr("scraper.base.robotparser.RobotFileParser.can_fetch", fake_can_fetch)
    monkeypatch.setattr("scraper.base.robotparser.RobotFileParser.read", lambda self: None)
    assert robots_allowed("https://www.ixigo.com/") is True
    assert robots_allowed("https://www.ixigo.com/search/result/flight/DEL/BOM/03102026/1/0/0/e/1?mon=true") is False
    assert "ixigo.com" in seen["url"]


def test_ixigo_search_url_is_robots_disallowed(monkeypatch):
    import datetime

    def fake_can_fetch(self, ua, url):
        return "/search/result/" not in url

    monkeypatch.setattr("scraper.base.robotparser.RobotFileParser.can_fetch", fake_can_fetch)
    monkeypatch.setattr("scraper.base.robotparser.RobotFileParser.read", lambda self: None)
    cfg = ScraperConfig(delay_seconds=0, respect_robots_txt=True,
                        enabled_sources={"ixigo": True})
    quotes = spiders.IxigoScraper(cfg).guarded_run("DEL", "BOM", 7)
    assert quotes
    assert quotes[0].status == "failed"
    assert quotes[0].raw_payload.get("error") == "robots_disallowed"


def test_ixigo_live_never_scrapes_without_api_key(monkeypatch):
    monkeypatch.delenv("IXIGO_API_KEY", raising=False)
    monkeypatch.delenv("IXIGO_API_URL", raising=False)
    spiders.MOCK = False
    try:
        cfg = ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                            enabled_sources={"ixigo": True})
        quotes = spiders.IxigoScraper(cfg).scrape("DEL", "BOM", 7)
        assert quotes and quotes[0].status == "failed"
        assert quotes[0].raw_payload.get("parked") is True
    finally:
        spiders.MOCK = os.environ.get("APIX_SCRAPER_MOCK", "true").lower() == "true"


def test_provider_registry_covers_all_spiders():
    sources = {c.source for c in spiders.ALL_SCRAPERS}
    assert sources <= set(PROVIDERS)
    assert get_provider("ixigo")["status"] == "api_only"
    assert get_provider("easemytrip")["status"] == "live"
    assert get_provider("akasa_direct")["status"] == "live"
    assert get_provider("yatra")["status"] == "api_only"
    assert get_provider("nope")["status"] == "parked"
