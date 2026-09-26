"""Form-flow + provider-API arrangement tests (no live network)."""
import datetime

from scraper import spiders
from scraper.base import ScraperConfig


def test_form_modules_expose_search_fns():
    from scraper.forms import (
        airindia,
        airindia_express,
        akasa,
        cleartrip,
        goibibo,
        indigo,
        ixigo,
        makemytrip,
        spicejet,
        yatra,
    )
    for mod, fn in [
        (spicejet, "search_spicejet"),
        (akasa, "search_akasa"),
        (indigo, "search_indigo"),
        (airindia, "search_airindia"),
        (yatra, "search_yatra"),
        (cleartrip, "search_cleartrip"),
        (makemytrip, "search_makemytrip"),
        (goibibo, "search_goibibo"),
        (airindia_express, "search_airindia_express"),
        (ixigo, "search_ixigo"),
    ]:
        assert callable(getattr(mod, fn)), mod.__name__
        assert mod.HOMEPAGE.startswith("https://")
        for attr in ("ORIGIN_SELECTORS", "DEST_SELECTORS", "DATE_SELECTORS", "SEARCH_SELECTORS"):
            assert getattr(mod, attr), f"{mod.__name__}.{attr} empty"
    assert cleartrip.ALLOWED_ENTRY and "results" in cleartrip.ALLOWED_ENTRY


def test_form_first_fallback_on_shifted_dom(monkeypatch):
    from scraper.base import SelectorNotFound
    import scraper.spiders as sp

    monkeypatch.setattr("scraper.forms.spicejet.search_spicejet",
                        lambda *a, **k: (_ for _ in ()).throw(SelectorNotFound("spicejet_direct", "x")))
    sentinel = [sp.mock_quote("spicejet_direct", "DEL", "BOM", 7)]
    monkeypatch.setattr(sp.MockableScraper, "fetch_live", lambda self, o, d, w: sentinel)
    out = sp.SpiceJetScraper(ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                                             enabled_sources={"spicejet_direct": True})
                             ).fetch_live("DEL", "BOM", 7)
    assert out is sentinel


def test_yatra_parked_never_touches_challenged_xhr(monkeypatch):
    import inspect
    from scraper.spiders import YatraScraper
    src = inspect.getsource(YatraScraper.fetch_live)
    assert "dom2/trigger" not in src  # challenged endpoint must not be fetched
    assert "_parked_via_api" in src
    monkeypatch.delenv("YATRA_API_KEY", raising=False)
    monkeypatch.delenv("YATRA_API_URL", raising=False)
    monkeypatch.setattr(spiders, "MOCK", False)
    try:
        q = YatraScraper(ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                                       enabled_sources={"yatra": True})).scrape("DEL", "BOM", 7)[0]
        assert q.status == "failed" and q.raw_payload.get("parked") is True
    finally:
        import os
        monkeypatch.setattr(spiders, "MOCK",
                            os.environ.get("APIX_SCRAPER_MOCK", "true").lower() == "true")


def test_parked_providers_record_no_data_without_keys(monkeypatch):
    for prefix in ("MMT", "GOIBIBO", "AIX", "YATRA"):
        monkeypatch.delenv(f"{prefix}_API_KEY", raising=False)
        monkeypatch.delenv(f"{prefix}_API_URL", raising=False)
    monkeypatch.setattr(spiders, "MOCK", False)
    try:
        cfg = lambda s: ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                                              enabled_sources={s: True})
        for cls, prefix in [(spiders.MakeMyTripScraper, "MMT"), (spiders.GoibiboScraper, "GOIBIBO"),
                            (spiders.AirIndiaExpressScraper, "AIX"),
                            (spiders.YatraScraper, "YATRA")]:
            q = cls(cfg(cls.source)).scrape("DEL", "BOM", 7)[0]
            assert q.status == "failed" and q.raw_payload.get("parked") is True, cls.source
    finally:
        import os
        monkeypatch.setattr(spiders, "MOCK",
                            os.environ.get("APIX_SCRAPER_MOCK", "true").lower() == "true")


def test_mock_path_unaffected_by_wiring():
    import scraper.spiders as sp
    sp.MOCK = True
    try:
        for cls in sp.ALL_SCRAPERS:
            cfg = ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                                   enabled_sources={cls.source: True})
            q = cls(cfg).scrape("DEL", "BOM", 7)[0]
            assert q.status == "success" and q.raw_payload.get("total_fare", 0) > 0, cls.source
    finally:
        import os
        sp.MOCK = os.environ.get("APIX_SCRAPER_MOCK", "true").lower() == "true"


def test_cleartrip_form_first_flow(monkeypatch):
    import scraper.spiders as sp
    from scraper.base import SelectorNotFound

    fake_payload = {"total_fare": 4800.0, "n_fares_seen": 5, "live": True}
    monkeypatch.setattr("scraper.forms.cleartrip.search_cleartrip",
                        lambda *a, **k: fake_payload)
    monkeypatch.setattr(sp, "MOCK", False)
    try:
        q = sp.CleartripScraper(ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                                              enabled_sources={"cleartrip": True})
                                ).fetch_live("DEL", "BOM", 7)[0]
        assert q.status == "success" and q.raw_payload["total_fare"] == 4800.0

        # Also verify fallback to deep link on SelectorNotFound
        monkeypatch.setattr("scraper.forms.cleartrip.search_cleartrip",
                            lambda *a, **k: (_ for _ in ()).throw(SelectorNotFound("cleartrip", "x")))
        sentinel = [sp.mock_quote("cleartrip", "DEL", "BOM", 7)]
        monkeypatch.setattr(sp.MockableScraper, "fetch_live", lambda self, o, d, w: sentinel)
        out = sp.CleartripScraper(ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                                                enabled_sources={"cleartrip": True})
                                  ).fetch_live("DEL", "BOM", 7)
        assert out is sentinel
    finally:
        import os
        sp.MOCK = os.environ.get("APIX_SCRAPER_MOCK", "true").lower() == "true"


def test_parked_providers_can_scrape_when_enabled(monkeypatch):
    import scraper.spiders as sp

    monkeypatch.setenv("APIX_SCRAPE_PARKED", "true")
    monkeypatch.setattr(sp, "MOCK", False)
    fake_payload = {"total_fare": 5100.0, "n_fares_seen": 3, "live": True}
    monkeypatch.setattr("scraper.forms.makemytrip.search_makemytrip", lambda *a, **k: fake_payload)
    monkeypatch.setattr("scraper.forms.goibibo.search_goibibo", lambda *a, **k: fake_payload)
    monkeypatch.setattr("scraper.forms.airindia_express.search_airindia_express", lambda *a, **k: fake_payload)
    monkeypatch.setattr("scraper.forms.yatra.search_yatra", lambda *a, **k: fake_payload)

    try:
        cfg = lambda s: ScraperConfig(delay_seconds=0, respect_robots_txt=False, enabled_sources={s: True})
        for cls in [sp.MakeMyTripScraper, sp.GoibiboScraper, sp.AirIndiaExpressScraper,
                    sp.YatraScraper]:
            q = cls(cfg(cls.source)).fetch_live("DEL", "BOM", 7)[0]
            assert q.status == "success" and q.raw_payload["total_fare"] == 5100.0, cls.source
    finally:
        import os
        monkeypatch.delenv("APIX_SCRAPE_PARKED", raising=False)
        sp.MOCK = os.environ.get("APIX_SCRAPER_MOCK", "true").lower() == "true"


def test_ixigo_has_no_scrape_backdoor(monkeypatch):
    """Ixigo stays on the official-API path even with APIX_SCRAPE_PARKED=true
    (robots.txt disallows /search/result/ + reCAPTCHA gate — no exceptions)."""
    import inspect
    import scraper.spiders as sp
    from scraper.spiders import IxigoScraper

    assert "APIX_SCRAPE_PARKED" not in inspect.getsource(IxigoScraper.fetch_live)
    assert "ixigo_api" in inspect.getsource(IxigoScraper.fetch_live)
    monkeypatch.setenv("APIX_SCRAPE_PARKED", "true")
    monkeypatch.delenv("IXIGO_API_KEY", raising=False)
    monkeypatch.delenv("IXIGO_API_URL", raising=False)
    monkeypatch.setattr(sp, "MOCK", False)
    try:
        q = IxigoScraper(ScraperConfig(delay_seconds=0, respect_robots_txt=False,
                                       enabled_sources={"ixigo": True})).fetch_live("DEL", "BOM", 7)[0]
        assert q.status == "failed" and q.raw_payload.get("parked") is True
    finally:
        monkeypatch.delenv("APIX_SCRAPE_PARKED", raising=False)
        import os
        sp.MOCK = os.environ.get("APIX_SCRAPER_MOCK", "true").lower() == "true"


def test_dismiss_popups_uses_valid_css():
    """_dismiss_popups runs via raw document.querySelectorAll: Playwright-only
    syntax (:has-text) throws there and silently skips every rule (this exact
    bug left Air India's OneTrust banner up and blocked form clicks)."""
    import inspect
    from scraper.forms import _common
    src = inspect.getsource(_common._dismiss_popups)
    assert ":has-text" not in src
    assert "onetrust-accept-btn-handler" in src


def test_resolve_emt_fares_requires_fare_elements():
    """Fee/coupon soup with no price/listing-class match must be SoldOut,
    not a fake SUCCESS (2026-10-04 run returned suspect Rs 1,662 this way)."""
    import pytest
    from scraper.base import SoldOut
    from scraper.emt import resolve_emt_fares

    class StubPage:
        def __init__(self, html, scoped):
            self._html = html
            self._scoped = scoped

        def content(self):
            return self._html

        def query_selector(self, sel):
            return None

        def evaluate(self, _js, scopes=None):
            return list(self._scoped)

    fee_html = "<div>cancellation fee Rs 1,500, flat Rs 1,662 off coupon \u20b91662</div>"
    with pytest.raises(SoldOut):
        resolve_emt_fares(StubPage(fee_html, scoped=[]))
    cheapest, n = resolve_emt_fares(StubPage("<div class='price'>\u20b95,900</div>", scoped=[5900.0, 6200.0]))
    assert cheapest == 5900.0 and n == 2

