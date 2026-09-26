"""Pricing-correctness tests: homepage banners/coupons must never parse as fares.

Fixtures mirror strings actually observed live (Akasa homepage marketing,
coupon/fee mentions, flight numbers, times) vs genuine result-card content.
"""
import pytest

from scraper.live import (
    CARD_SCOPES,
    PRICE_SCOPES,
    _offer_ok,
    extract_card_fares,
    parse_fares,
    parse_scoped_fares,
    resolve_fares,
    verify_navigated,
)
from scraper.base import SelectorNotFound, SoldOut

# Observed on the Akasa homepage shell (no search performed): marketing copy
# that the old page-wide min() reported as a Rs 3,500 "fare".
HOMEPAGE_BANNERS = """
<div class="hero">Fares starting Rs 3,500 on select routes. Flat Rs 5,000 off
on HDFC cards. Cancellation fee Rs 1,500 applies. Flight 6E 2034 departs 14:30.
<br/>Fares starting 11,816 on international sectors. Save up to Rs 2,000 today.</div>
"""

# Genuine results page: three flight cards + one coupon banner.
RESULTS_PAGE = """
<div class="results">
  <div class="flight-card"><span class="airline">Akasa QP 1321</span>
    <span class="fare-price">Rs 5,200</span><span>Total incl. taxes</span></div>
  <div class="flight-card"><span class="airline">IndiGo 6E 2034</span>
    <span class="fare-price">Rs 6,100</span></div>
  <div class="flight-card"><span class="airline">SpiceJet SG 881</span>
    <span class="fare-price">Rs 5,800</span></div>
  <div class="offer-banner">Flat Rs 500 off with code FLYHIGH. Save Rs 2,000!</div>
</div>
"""


class FakePage:
    """Minimal page stub executing the SAME rule shape as the browser JS.

    evaluate() receives the arg dicts used by parse_scoped_fares /
    extract_card_fares; card/price matching is substring-based over canned
    (class, text) blocks — enough to prove branching, not a DOM engine.
    """

    def __init__(self, blocks, html=""):
        # blocks: list of (class_attr, inner_text)
        self.blocks = blocks
        self._html = html

    def content(self):
        return self._html

    def query_selector(self, sel):
        import re
        key = sel.strip().lower()
        if key == "body":
            return object() if self.blocks else None
        m = re.search(r"\*=\s*['\"]?([\w-]+)", key)
        frag = m.group(1).lower() if m else key
        for cls, _txt in self.blocks:
            if frag in cls.lower():
                return object()
        return None

    def evaluate(self, _js, args):
        import re
        from scraper.live import OFFER_WINDOW
        scopes = args.get("scopes") or args.get("priceScopes") or []
        only_cards = "cardScopes" in args
        rupee = re.compile(r"(?:\u20b9|Rs\.?|INR)\s?([\d,]{3,})", re.IGNORECASE)
        cards = []
        if only_cards:
            for cls, txt in self.blocks:
                low = cls.lower()
                if any(k in low for k in ("card", "result", "itinerar", "journey", "listing-card")):
                    cards.append((cls, txt))
            out = []
            for _cls, txt in cards:
                for m in rupee.finditer(txt):
                    v = float(m.group(1).replace(",", ""))
                    if v < 1500:
                        continue
                    win = txt[max(0, m.start() - OFFER_WINDOW): m.end() + OFFER_WINDOW]
                    if not _offer_ok(win):
                        continue
                    out.append(v)
                    break
            return sorted(out)
        out = []
        for s in scopes:
            frag = (re.search(r"\*=\s*['\"]?([\w-]+)", s.lower()).group(1)
                    if re.search(r"\*=\s*['\"]?([\w-]+)", s.lower()) else s.lower())
            for cls, txt in self.blocks:
                if frag not in cls.lower():
                    continue
                for m in rupee.finditer(txt):
                    v = float(m.group(1).replace(",", ""))
                    if v < 1500:
                        continue
                    win = txt[max(0, m.start() - OFFER_WINDOW): m.end() + OFFER_WINDOW]
                    if not _offer_ok(win):
                        continue
                    out.append(v)
        return sorted(out)


def test_offer_windows():
    assert not _offer_ok("flat Rs 3,000 off with code")
    assert not _offer_ok("Rs 1,500 cancellation fee applies")
    assert not _offer_ok("Fares starting Rs 3,500 today")
    assert not _offer_ok("Save Rs 2,000 on this route")
    assert _offer_ok("Total Rs 5,200 incl. taxes")
    assert _offer_ok("QP 1321 Rs 5,200 non-stop")


def test_homepage_banners_parse_to_nothing():
    # No genuine fare on this shell: coupons, fees, "starting" copy, flight
    # number 2034 / time fragments must not surface (flight numbers carry no
    # currency marker; fee/coupon windows are offer-filtered).
    assert parse_fares(HOMEPAGE_BANNERS) == []


def test_genuine_totals_survive_filter():
    fares = parse_fares("Total Rs 5,200 incl. taxes. Also Rs 6,100 and Rs 5,800.")
    assert fares == [5200.0, 5800.0, 6100.0]


def test_scoped_drops_flight_numbers_and_times():
    page = FakePage([("fare-price", "6E 2034 departs 14:30"), ("fare-price", "Rs 5,200")],
                    html="x")
    assert parse_scoped_fares(page, ["fare-price"]) == [5200.0]


def test_card_extraction_ignores_offer_banner():
    page = FakePage([
        ("flight-card", "Akasa QP 1321 Rs 5,200 Total incl. taxes"),
        ("flight-card", "IndiGo 6E 2034 Rs 6,100"),
        ("flight-card", "SpiceJet SG 881 Rs 5,800"),
        ("offer-banner", "Flat Rs 500 off with code FLYHIGH"),
    ])
    cards = extract_card_fares(page)
    assert cards == [5200.0, 5800.0, 6100.0]


def test_no_cards_means_no_fares():
    page = FakePage([("hero", "Fares starting Rs 3,500")])
    assert extract_card_fares(page) == []


def test_verify_navigated():
    assert verify_navigated("https://x.com/results?from=DEL", "https://x.com/")
    assert verify_navigated("https://x.com/results", "https://x.com")
    assert not verify_navigated("https://x.com/", "https://x.com/")
    assert not verify_navigated("https://x.com/?a=1", "https://x.com/")


def test_resolve_prefers_cards_over_fee_rows():
    page = FakePage([
        ("flight-card", "QP 1321 Rs 5,200"),
        ("flight-card", "6E 2034 Rs 6,100"),
        ("fare-row", "cancellation fee Rs 1,500"),
    ], html="fee Rs 1,500 Rs 5,200")
    cheapest, n = resolve_fares(page, "cleartrip",
                                ["[class*=fare-row i]"], CARD_SCOPES)
    assert cheapest == 5200.0 and n == 2


def test_resolve_soldout_without_cards_or_fares():
    # fare-row element exists but holds no fare (fee-only row) -> SoldOut;
    # selector matching nothing at all -> SelectorNotFound.
    page = FakePage([("fare-row", "cancellation policy only"),
                     ("hero", "Fares starting Rs 3,500")], html="starting Rs 3,500")
    with pytest.raises(SoldOut):
        resolve_fares(page, "spicejet_direct", ["[class*=fare-row i]"], CARD_SCOPES)
    with pytest.raises(SelectorNotFound):
        resolve_fares(page, "spicejet_direct", ["[class*=nope-zzz i]"], CARD_SCOPES)


def test_audit_only_rejects_unknown_sources_without_network():
    from scraper.audit import main
    assert main(["--only", "nope-zzz"]) == 2
