"""Calibration tests: scoped-first fare resolution, client-reject retry, selectors."""
import pytest

from scraper.base import SelectorNotFound, SoldOut
from scraper.live import _is_client_reject, resolve_fares


class StubPage:
    def __init__(self, html, scoped_vals, matched):
        self._html = html
        self._scoped = scoped_vals
        self._matched = matched

    def content(self):
        return self._html

    def query_selector(self, sel):
        return object() if sel in self._matched else None

    def evaluate(self, _js, scopes=None):
        return list(self._scoped)


FEE_HTML = "<div>cancellation fee Rs 1,500 and Rs 5,000 off coupon \u20b91500</div>"


def test_scoped_first_rejects_fee_text_as_success():
    page = StubPage(FEE_HTML, scoped_vals=[], matched=["div[class*=fare i]"])
    with pytest.raises(SoldOut):
        resolve_fares(page, "cleartrip", ["div[class*=fare i]", "span[class*=price i]"])


def test_scoped_first_accepts_genuine_fare_elements():
    page = StubPage(FEE_HTML, scoped_vals=[5200.0, 6100.0], matched=["div[class*=fare i]"])
    cheapest, n = resolve_fares(page, "cleartrip", ["div[class*=fare i]", "span[class*=price i]"])
    assert cheapest == 5200.0 and n == 2


def test_scoped_first_reports_missing_selectors():
    page = StubPage(FEE_HTML, scoped_vals=[], matched=[])
    with pytest.raises(SelectorNotFound):
        resolve_fares(page, "cleartrip", ["div[class*=fare i]"])


def test_body_fallback_path_unchanged():
    page = StubPage("<div>only \u20b95500 here</div>", scoped_vals=[], matched=["body"])
    cheapest, n = resolve_fares(page, "spicejet_direct", ["body"])
    assert cheapest == 5500.0 and n == 1


def test_client_reject_detection():
    assert _is_client_reject(Exception("Page.goto: net::ERR_CONNECTION_RESET at https://x/"))
    assert _is_client_reject(Exception("net::ERR_EMPTY_RESPONSE"))
    assert not _is_client_reject(Exception("Timeout 60000ms exceeded"))
    assert not _is_client_reject(Exception("something else"))


def test_launch_browser_forced_channel(monkeypatch):
    from scraper.live import launch_browser
    monkeypatch.setenv("APIX_PLAYWRIGHT_CHANNEL", "chrome")
    seen = {}

    class FakeChromium:
        def launch(self, **kw):
            seen.update(kw)
            assert kw.get("channel") == "chrome"
            return "BROWSER"

    class FakeP:
        chromium = FakeChromium()

    browser, via = launch_browser(FakeP(), proxy=None)
    assert browser == "BROWSER" and via is True


def test_calibrated_selectors():
    from scraper.forms import akasa, spicejet
    from scraper.spiders import CleartripScraper
    assert "input[name='From']" in akasa.ORIGIN_SELECTORS
    assert "input[name='To']" in akasa.DEST_SELECTORS
    assert any("nth=" in s for s in spicejet.ORIGIN_SELECTORS + spicejet.DEST_SELECTORS)
    assert all(s.strip().lower() != "body" for s in CleartripScraper.SELECTORS)
