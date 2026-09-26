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
class IndigoScraper(MockableScraper):
    source = "indigo_direct"
    start_url = "https://www.goindigo.in"
    requires_js = True
    # EXPERIMENTAL: IndiGo booking is a JS app; deep-link pattern unverified.
    SEARCH_URL = ("https://www.goindigo.in/booking/search-flight.html?origin={o}&destination={d}"
                  "&departureDate={dd}-{mm}-{yyyy}&adults=1&children=0&infants=0&tripType=OneWay")


class AirIndiaScraper(MockableScraper):
    source = "airindia_direct"
    start_url = "https://www.airindia.com"
    requires_js = True
    SEARCH_URL = ("https://www.airindia.com/in/en/book-flights.html?origin={o}&destination={d}"
                  "&departureDate={yyyy}-{mm}-{dd}&adults=1&tripType=oneway")


class AirIndiaExpressScraper(MockableScraper):
    source = "airindia_express"
    start_url = "https://www.airindiaexpress.com"
    requires_js = True
    SEARCH_URL = ("https://www.airindiaexpress.com/book/search?origin={o}&destination={d}"
                  "&depart={yyyy}-{mm}-{dd}&adult=1")


class AkasaScraper(MockableScraper):
    source = "akasa_direct"
    start_url = "https://www.akasaair.com"
    requires_js = True
    SEARCH_URL = ("https://www.akasaair.com/search-flight?origin={o}&destination={d}"
                  "&departure={yyyy}-{mm}-{dd}&adult=1")


class SpiceJetScraper(MockableScraper):
    source = "spicejet_direct"
    start_url = "https://www.spicejet.com"
    requires_js = True
    SEARCH_URL = ("https://www.spicejet.com/Search.aspx?origin={o}&destination={d}"
                  "&departDate={dd}/{mm}/{yyyy}&adults=1&children=0&infants=0")


# --- OTAs (Scrapy / XHR-JSON preferred) ---
class MakeMyTripScraper(MockableScraper):
    source = "makemytrip"
    start_url = "https://www.makemytrip.com"
    requires_js = True  # search form is JS-driven; prefer internal XHR endpoint
    CONFIDENCE = "known"
    SEARCH_URL = ("https://www.makemytrip.com/flight/search?itinerary={o}-{d}-{dd}/{mm}/{yyyy}"
                  "&tripType=O&paxType=A-1_C-0_I-0&cabinClass=E")
    SELECTORS = ["div.fare-summary", "span.actual-price", "div.priceSection", "body"]


class YatraScraper(MockableScraper):
    source = "yatra"
    start_url = "https://www.yatra.com"
    requires_js = False
    CONFIDENCE = "known"
    SEARCH_URL = ("https://flight.yatra.com/air-search-ui/dom2/trigger?ADT=1&CHD=0&INF=0&class=Economy"
                  "&destination={d}&destinationCountry=IN&flexi=0&flight_depart_date={dd}%2F{mm}%2F{yyyy}"
                  "&hb=0&noOfSegments=1&origin={o}&originCountry=IN&type=O&version=1.1&viewName=normal")
    SELECTORS = ["div.flight-price", "span.fare", "body"]


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
    SELECTORS = ["div.fare", "span.price", "body"]


class IxigoScraper(MockableScraper):
    source = "ixigo"
    start_url = "https://www.ixigo.com"
    requires_js = True
    SEARCH_URL = "https://www.ixigo.com/search/result/flight/{o}/{d}/{ddmmyyyy}/1/0/0/e/1?mon=true"
    SELECTORS = ["div.fare", "div.price", "body"]


class GoibiboScraper(MockableScraper):
    source = "goibibo"
    start_url = "https://www.goibibo.com"
    requires_js = True
    CONFIDENCE = "known"
    SEARCH_URL = "https://www.goibibo.com/flights/air-{o}-{d}-{yyyymmdd}--1-0-0-E-D/"
    SELECTORS = ["div.fareCard", "span.price", "body"]


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
