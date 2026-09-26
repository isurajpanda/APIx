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

    def scrape(self, origin: str, destination: str, window: int) -> list[Quote]:
        if MOCK:
            return [mock_quote(self.source, origin, destination, window)]
        return self.fetch_live(origin, destination, window)

    def fetch_live(self, origin: str, destination: str, window: int) -> list[Quote]:
        raise NotImplementedError(
            f"{self.source}: live fetch not wired in prototype; set APIX_SCRAPER_MOCK=true"
        )


# --- Airline direct (Playwright / JS-rendered) ---
class IndigoScraper(MockableScraper):
    source = "indigo_direct"
    start_url = "https://www.goindigo.in"
    requires_js = True


class AirIndiaScraper(MockableScraper):
    source = "airindia_direct"
    start_url = "https://www.airindia.com"
    requires_js = True


class AirIndiaExpressScraper(MockableScraper):
    source = "airindia_express"
    start_url = "https://www.airindiaexpress.com"
    requires_js = True


class AkasaScraper(MockableScraper):
    source = "akasa_direct"
    start_url = "https://www.akasaair.com"
    requires_js = True


class SpiceJetScraper(MockableScraper):
    source = "spicejet_direct"
    start_url = "https://www.spicejet.com"
    requires_js = True


# --- OTAs (Scrapy / XHR-JSON preferred) ---
class MakeMyTripScraper(MockableScraper):
    source = "makemytrip"
    start_url = "https://www.makemytrip.com"
    requires_js = True  # search form is JS-driven; prefer internal XHR endpoint


class YatraScraper(MockableScraper):
    source = "yatra"
    start_url = "https://www.yatra.com"
    requires_js = False


class EaseMyTripScraper(MockableScraper):
    source = "easemytrip"
    start_url = "https://www.easemytrip.com"
    requires_js = False


class CleartripScraper(MockableScraper):
    source = "cleartrip"
    start_url = "https://www.cleartrip.com"
    requires_js = True


class IxigoScraper(MockableScraper):
    source = "ixigo"
    start_url = "https://www.ixigo.com"
    requires_js = True


class GoibiboScraper(MockableScraper):
    source = "goibibo"
    start_url = "https://www.goibibo.com"
    requires_js = True


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
