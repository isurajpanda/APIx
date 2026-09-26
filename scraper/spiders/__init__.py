"""Source scrapers. Each module = one source (own DOM/anti-bot posture).

Prototype mode: live scraping functions are stubbed behind `MOCK=true` (default),
returning deterministic synthetic quotes so the full pipeline is demoable even when
sites block bots. Set MOCK=false to attempt real fetching (Playwright/Scrapy paths).
"""
from __future__ import annotations

import hashlib
import os
import random
from datetime import datetime, timezone

from scraper.base import BaseScraper, Quote

MOCK = os.environ.get("APIX_SCRAPER_MOCK", "true").lower() == "true"

# Representative base fares (INR) per route for mock generation.
BASE_FARES = {
    ("DEL", "BOM"): 5500,
    ("DEL", "BLR"): 6200,
    ("BOM", "BLR"): 4200,
    ("DEL", "CCU"): 5800,
    ("BLR", "HYD"): 3200,
    ("MAA", "DEL"): 6400,
}

CARRIERS = {
    "indigo_direct": "6E",
    "airindia_direct": "AI",
    "airindia_express": "IX",
    "akasa_direct": "QP",
    "spicejet_direct": "SG",
    "makemytrip": "6E",
    "yatra": "AI",
    "easemytrip": "QP",
    "cleartrip": "SG",
    "ixigo": "6E",
    "goibibo": "AI",
}


def mock_quote(source: str, origin: str, destination: str, window: int) -> Quote:
    """Deterministic mock fare: base + lead-time markup + hash jitter."""
    base = BASE_FARES.get((origin, destination), 5000)
    # Lead-time curve: last-minute (T+1) is pricier; T+45 cheapest.
    markup = {1: 1.45, 7: 1.25, 15: 1.10, 30: 1.0, 45: 0.92}.get(window, 1.0)
    seed = int(hashlib.md5(f"{source}{origin}{destination}{window}".encode()).hexdigest()[:8], 16)
    jitter = 0.95 + (seed % 100) / 1000.0  # 0.95–1.05
    total = round(base * markup * jitter, 2)
    taxes = round(total * 0.18, 2)
    payload = {
        "total_fare": total,
        "base_fare": round(total - taxes - 300, 2),
        "taxes": taxes,
        "udf": 200.0,
        "convenience_fee": 100.0,
        "currency": "INR",
        "mock": True,
    }
    return Quote(
        source=source,
        origin=origin,
        destination=destination,
        carrier=CARRIERS.get(source, "6E"),
        advance_purchase_window=window,
        scrape_timestamp=datetime.now(timezone.utc),
        raw_payload=payload,
        status="success",
    )


class MockableScraper(BaseScraper):
    """JS/Scrapy subclass hook: real fetch when MOCK=false, mock otherwise."""

    # Live-search config (calibrated best-effort; audit reports per-source status).
    # URL template vars: {o} {d} origin/dest, {dd} {mm} {yyyy} flight date parts,
    # {yyyymmdd} {ddmmyyyy} compact forms. CONFIDENCE: 'known' vs 'experimental'.
    SEARCH_URL: str = ""
    SELECTORS: list[str] = ["body"]
    CONFIDENCE: str = "experimental"

    def search_url(self, origin: str, destination: str, flight_date) -> str:
        return self.SEARCH_URL.format(
            o=origin, d=destination,
            dd=f"{flight_date.day:02d}", mm=f"{flight_date.month:02d}", yyyy=flight_date.year,
            yyyymmdd=flight_date.strftime("%Y%m%d"), ddmmyyyy=flight_date.strftime("%d%m%Y"),
        )

    def robots_target(self, origin: str = "", destination: str = "", window: int = 7, **_) -> str:
        """Exact search URL for the robots check (falls back to homepage)."""
        try:
            from datetime import date, timedelta
            if self.SEARCH_URL and origin and destination:
                return self.search_url(origin, destination, date.today() + timedelta(days=int(window)))
        except Exception:
            pass
        return self.start_url

    def scrape(self, origin: str, destination: str, window: int) -> list[Quote]:
        if MOCK:
            return [mock_quote(self.source, origin, destination, window)]
        return self.fetch_live(origin, destination, window)

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        """Real Playwright fetch: search URL -> cheapest visible fare."""
        from datetime import date, timedelta
        from scraper.live import REAL_CHROME_UA, fetch_search_result

        if not self.SEARCH_URL:
            raise NotImplementedError(f"{self.source}: no SEARCH_URL configured")
        flight_date = date.today() + timedelta(days=window)
        url = self.search_url(origin, destination, flight_date)
        payload = fetch_search_result(
            self.source, url, self.SELECTORS, REAL_CHROME_UA,
            proxy=self.proxy_for_playwright(),
        )
        return [Quote(
            source=self.source, origin=origin, destination=destination,
            carrier=CARRIERS.get(self.source, "6E"),
            advance_purchase_window=window,
            scrape_timestamp=datetime.now(timezone.utc),
            raw_payload=payload, status="success",
        )]


# --- Airline direct (Playwright / JS-rendered) ---
# Form-first pattern: homepage form modules in scraper/forms/ (EMT pattern);
# single fallback to the deep link only when the DOM shifts (SelectorNotFound).
def _form_first(source: str, form_fn, fallback_fn, origin: str, destination: str,
                window: int, proxy) -> list["Quote"]:
    from datetime import date, timedelta

    from scraper.base import SelectorNotFound

    flight_date = date.today() + timedelta(days=window)
    try:
        payload = form_fn(origin, destination, flight_date, proxy=proxy)
        return [Quote(source=source, origin=origin, destination=destination,
                      carrier=CARRIERS.get(source, "6E"),
                      advance_purchase_window=window,
                      scrape_timestamp=datetime.now(timezone.utc),
                      raw_payload=payload, status="success")]
    except SelectorNotFound:
        # DOM shifted — one fallback hit on the deep link, then honest status.
        return fallback_fn(origin, destination, window)
    # CaptchaBlocked / SoldOut / BlockedByStatus propagate to run_with_retry
    # for proper captcha_blocked / sold_out / proxy-failover handling.


def _parked_via_api(source: str, prefix: str, origin: str, destination: str,
                    window: int) -> list["Quote"]:
    """Parked providers: official API stub or honest no_data — never scraping."""
    from datetime import date, timedelta

    from scraper.provider_apis import fetch_official_quote

    flight_date = date.today() + timedelta(days=window)
    total, payload = fetch_official_quote(prefix, origin, destination, flight_date.isoformat())
    if total is None:
        return [Quote(source=source, origin=origin, destination=destination,
                      carrier=CARRIERS.get(source, "6E"),
                      advance_purchase_window=window,
                      scrape_timestamp=datetime.now(timezone.utc),
                      raw_payload=payload, status="failed")]
    return [Quote(source=source, origin=origin, destination=destination,
                  carrier=CARRIERS.get(source, "6E"),
                  advance_purchase_window=window,
                  scrape_timestamp=datetime.now(timezone.utc),
                  raw_payload=payload, status="success")]


class IndigoScraper(MockableScraper):
    source = "indigo_direct"
    start_url = "https://www.goindigo.in"
    requires_js = True
    # EXPERIMENTAL: IndiGo booking is a JS app; deep-link pattern unverified.
    SEARCH_URL = ("https://www.goindigo.in/booking/search-flight.html?origin={o}&destination={d}"
                  "&departureDate={dd}-{mm}-{yyyy}&adults=1&children=0&infants=0&tripType=OneWay")

    def robots_target(self, *args, **_) -> str:
        return self.start_url  # live path drives the homepage form, not the deep link

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        from scraper.forms.indigo import search_indigo
        return _form_first(self.source, search_indigo,
                           lambda o, d, w: MockableScraper.fetch_live(self, o, d, w),
                           origin, destination, window, self.proxy_for_playwright())


class AirIndiaScraper(MockableScraper):
    """Homepage form only (scraper/forms/airindia.py). The guessed deep-link
    pattern 404s, so there is no deep-link fallback. Bundled Chromium gets
    TLS-hung on this host — set APIX_PLAYWRIGHT_CHANNEL=chrome."""

    source = "airindia_direct"
    start_url = "https://www.airindia.com"
    requires_js = True
    SEARCH_URL = ("https://www.airindia.com/in/en/book-flights.html?origin={o}&destination={d}"
                  "&departureDate={yyyy}-{mm}-{dd}&adults=1&tripType=oneway")

    def robots_target(self, *args, **_) -> str:
        return self.start_url  # form path only; deep link unverified (404s)

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        from datetime import date, timedelta

        from scraper.forms.airindia import search_airindia

        flight_date = date.today() + timedelta(days=window)
        payload = search_airindia(origin, destination, flight_date,
                                  proxy=self.proxy_for_playwright())
        return [Quote(
            source=self.source, origin=origin, destination=destination,
            carrier=CARRIERS.get(self.source, "AI"),
            advance_purchase_window=window,
            scrape_timestamp=datetime.now(timezone.utc),
            raw_payload=payload, status="success",
        )]


class AirIndiaExpressScraper(MockableScraper):
    """PARKED: reCAPTCHA Enterprise on homepage — official API only, never CAPTCHA solving."""

    source = "airindia_express"
    start_url = "https://www.airindiaexpress.com"
    requires_js = True
    SEARCH_URL = ("https://www.airindiaexpress.com/book/search?origin={o}&destination={d}"
                  "&depart={yyyy}-{mm}-{dd}&adult=1")

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        if os.environ.get("APIX_SCRAPE_PARKED", "").lower() in ("true", "1"):
            from scraper.forms.airindia_express import search_airindia_express
            return _form_first(self.source, search_airindia_express,
                               lambda o, d, w: MockableScraper.fetch_live(self, o, d, w),
                               origin, destination, window, self.proxy_for_playwright())
        return _parked_via_api(self.source, "AIX", origin, destination, window)


class AkasaScraper(MockableScraper):
    source = "akasa_direct"
    start_url = "https://www.akasaair.com"
    requires_js = True
    SEARCH_URL = ("https://www.akasaair.com/search-flight?origin={o}&destination={d}"
                  "&departure={yyyy}-{mm}-{dd}&adult=1")

    def robots_target(self, *args, **_) -> str:
        return self.start_url

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        from scraper.forms.akasa import search_akasa
        return _form_first(self.source, search_akasa,
                           lambda o, d, w: MockableScraper.fetch_live(self, o, d, w),
                           origin, destination, window, self.proxy_for_playwright())


class SpiceJetScraper(MockableScraper):
    source = "spicejet_direct"
    start_url = "https://www.spicejet.com"
    requires_js = True
    SEARCH_URL = ("https://www.spicejet.com/Search.aspx?origin={o}&destination={d}"
                  "&departDate={dd}/{mm}/{yyyy}&adults=1&children=0&infants=0")

    def robots_target(self, *args, **_) -> str:
        return self.start_url

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        from scraper.forms.spicejet import search_spicejet
        return _form_first(self.source, search_spicejet,
                           lambda o, d, w: MockableScraper.fetch_live(self, o, d, w),
                           origin, destination, window, self.proxy_for_playwright())


# --- OTAs (Scrapy / XHR-JSON preferred) ---
class MakeMyTripScraper(MockableScraper):
    """PARKED for scraping by default (TLS-reset/bot-wall) — affiliate API preferred.
    Set APIX_SCRAPE_PARKED=true to attempt live form scraping."""

    source = "makemytrip"
    start_url = "https://www.makemytrip.com"
    requires_js = True  # search form is JS-driven; prefer internal XHR endpoint
    CONFIDENCE = "known"
    SEARCH_URL = ("https://www.makemytrip.com/flight/search?itinerary={o}-{d}-{dd}/{mm}/{yyyy}"
                  "&tripType=O&paxType=A-1_C-0_I-0&cabinClass=E")
    SELECTORS = ["div.fare-summary", "span.actual-price", "div.priceSection", "body"]

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        if os.environ.get("APIX_SCRAPE_PARKED", "").lower() in ("true", "1"):
            from scraper.forms.makemytrip import search_makemytrip
            return _form_first(self.source, search_makemytrip,
                               lambda o, d, w: MockableScraper.fetch_live(self, o, d, w),
                               origin, destination, window, self.proxy_for_playwright())
        return _parked_via_api(self.source, "MMT", origin, destination, window)


class YatraScraper(MockableScraper):
    """PARKED for scraping by default: official affiliate API preferred.
    Set APIX_SCRAPE_PARKED=true to attempt the homepage form ONLY
    (scraper/forms/yatra.py) — the PerimeterX-challenged XHR trigger is never
    fetched, so there is deliberately no deep-link fallback here."""

    source = "yatra"
    start_url = "https://www.yatra.com"
    requires_js = False
    CONFIDENCE = "known"
    SEARCH_URL = ("https://flight.yatra.com/air-search-ui/dom2/trigger?ADT=1&CHD=0&INF=0&class=Economy"
                  "&destination={d}&destinationCountry=IN&flexi=0&flight_depart_date={dd}%2F{mm}%2F{yyyy}"
                  "&hb=0&noOfSegments=1&origin={o}&originCountry=IN&type=O&version=1.1&viewName=normal")
    SELECTORS = ["div.flight-price", "span.fare", "body"]

    def robots_target(self, *args, **_) -> str:
        return self.start_url

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        if os.environ.get("APIX_SCRAPE_PARKED", "").lower() in ("true", "1"):
            from datetime import date, timedelta

            from scraper.forms.yatra import search_yatra

            flight_date = date.today() + timedelta(days=window)
            payload = search_yatra(origin, destination, flight_date,
                                   proxy=self.proxy_for_playwright())
            return [Quote(
                source=self.source, origin=origin, destination=destination,
                carrier=CARRIERS.get(self.source, "AI"),
                advance_purchase_window=window,
                scrape_timestamp=datetime.now(timezone.utc),
                raw_payload=payload, status="success",
            )]
        return _parked_via_api(self.source, "YATRA", origin, destination, window)


class EaseMyTripScraper(MockableScraper):
    source = "easemytrip"
    start_url = "https://www.easemytrip.com"
    requires_js = False
    CONFIDENCE = "known"  # form-driven flow proven (see scraper/emt.py)
    SEARCH_URL = ("https://flight.easemytrip.com/FlightList/Index?srch={o}-{o}-A%7C{d}-{d}-A%7C"
                  "{mm}%2F{dd}%2F{yyyy}-A%7C1_0_0")
    SELECTORS = ["div.price", "span.fare-amt", "body"]

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        """Form-driven live search (deep links land on an idle shell)."""
        from datetime import date, timedelta
        from scraper.emt import search_easymytrip

        flight_date = date.today() + timedelta(days=window)
        payload = search_easymytrip(origin, destination, flight_date,
                                    proxy=self.proxy_for_playwright())
        return [Quote(
            source=self.source, origin=origin, destination=destination,
            carrier=CARRIERS.get(self.source, "QP"),
            advance_purchase_window=window,
            scrape_timestamp=datetime.now(timezone.utc),
            raw_payload=payload, status="success",
        )]


class CleartripScraper(MockableScraper):
    source = "cleartrip"
    start_url = "https://www.cleartrip.com"
    requires_js = True
    SEARCH_URL = ("https://www.cleartrip.com/flights/results?from={o}&to={d}"
                  "&depart_date={dd}%2F{mm}%2F{yyyy}&adults=1&childs=0&infants=0&class=Economy")
    # Fare-element selectors ONLY (no "body" catch-all): page-wide parsing picks
    # up fee text ("Rs 1,500 cancellation fee") and would fake a SUCCESS —
    # resolve_fares() requires a fare-element hit for these selectors.
    SELECTORS = ["[class*=fareCard i]", "[class*=fare-card i]", "div[class*=fare i]",
                 "span[class*=price i]", "[data-testid*=fare i]", "[data-testid*=price i]",
                 "div[class*=tuple i]", "div[class*=flight-card i]"]

    def robots_target(self, *args, **_) -> str:
        return self.start_url

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        from scraper.forms.cleartrip import search_cleartrip
        return _form_first(self.source, search_cleartrip,
                           lambda o, d, w: MockableScraper.fetch_live(self, o, d, w),
                           origin, destination, window, self.proxy_for_playwright())


class IxigoScraper(MockableScraper):
    """Ixigo is PARKED for scraping — no exceptions, no env-flag backdoor:
    robots.txt disallows /search/result/ and the flow is reCAPTCHA-gated.
    Live path uses the official API hook only (scraper/ixigo_api.py); never
    Playwright scraping. SEARCH_URL is retained so the path-aware robots gate
    keeps returning robots_disallowed as a second line of defense."""

    source = "ixigo"
    start_url = "https://www.ixigo.com"
    requires_js = True
    SEARCH_URL = "https://www.ixigo.com/search/result/flight/{o}/{d}/{ddmmyyyy}/1/0/0/e/1?mon=true"
    SELECTORS = ["div.fare", "div.price", "body"]

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        from datetime import date, timedelta

        from scraper.ixigo_api import fetch_official_quote

        flight_date = date.today() + timedelta(days=window)
        total, payload = fetch_official_quote(origin, destination, flight_date.isoformat())
        if total is None:
            # Parked: record no_data (pipeline excludes it) — never a fake fare.
            return [Quote(
                source=self.source, origin=origin, destination=destination,
                carrier=CARRIERS.get(self.source, "6E"),
                advance_purchase_window=window,
                scrape_timestamp=datetime.now(timezone.utc),
                raw_payload=payload, status="failed",
            )]
        return [Quote(
            source=self.source, origin=origin, destination=destination,
            carrier=CARRIERS.get(self.source, "6E"),
            advance_purchase_window=window,
            scrape_timestamp=datetime.now(timezone.utc),
            raw_payload=payload, status="success",
        )]


class GoibiboScraper(MockableScraper):
    """PARKED for scraping by default (challenge shell + timeouts) — affiliate API preferred.
    Set APIX_SCRAPE_PARKED=true to attempt live form scraping."""

    source = "goibibo"
    start_url = "https://www.goibibo.com"
    requires_js = True
    CONFIDENCE = "known"
    SEARCH_URL = "https://www.goibibo.com/flights/air-{o}-{d}-{yyyymmdd}--1-0-0-E-D/"
    SELECTORS = ["div.fareCard", "span.price", "body"]

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        if os.environ.get("APIX_SCRAPE_PARKED", "").lower() in ("true", "1"):
            from scraper.forms.goibibo import search_goibibo
            return _form_first(self.source, search_goibibo,
                               lambda o, d, w: MockableScraper.fetch_live(self, o, d, w),
                               origin, destination, window, self.proxy_for_playwright())
        return _parked_via_api(self.source, "GOIBIBO", origin, destination, window)


ALL_SCRAPERS = [
    IndigoScraper,
    AirIndiaScraper,
    AirIndiaExpressScraper,
    AkasaScraper,
    SpiceJetScraper,
    MakeMyTripScraper,
    YatraScraper,
    EaseMyTripScraper,
    CleartripScraper,
    IxigoScraper,
    GoibiboScraper,
]
