"""SpiceJet homepage form flow (robots open; suggestion endpoint was dead on
datacenter IP — retry on residential). Never touches /api/v1 (disallowed)."""
from __future__ import annotations

from datetime import date

HOMEPAGE = "https://www.spicejet.com/"
# Calibrated 2026-10-04 via live DOM dump: React-Native-Web inputs carry no
# name/id/placeholder; the first two visible inputs are From/To. Date field
# placeholder is 'DD/MM/YYYY' (hidden until the picker opens — date fill is
# best-effort; the search still runs on the default date).
ORIGIN_SELECTORS = [
    "[data-testid*='to-testID-origin']",
    "div[data-testid*='origin'] input",
    "input[placeholder*='From' i]",
    "input:visible >> nth=0",
]
DEST_SELECTORS = [
    "[data-testid*='to-testID-destination']",
    "div[data-testid*='destination'] input",
    "input[placeholder*='To' i]",
    "input:visible >> nth=1",
]
DATE_SELECTORS = [
    "[data-testid*='departure-date']",
    "input[placeholder='DD/MM/YYYY']",
    "input[placeholder*='Depart' i]",
    "input[name*='depart' i]",
]
SEARCH_SELECTORS = [
    "[data-testid*='home-page-flight-cta']",
    "div[role='button']:has-text('Search Flight')",
    "button:has-text('Search Flight')",
    "button[type='submit']",
    "input[type='submit']",
    "button:has-text('Search')",
    "div[role='button']:has-text('Search')",
    "[class*=search i][class*=btn i]",
]


def search_spicejet(origin: str, destination: str, flight_date: date,
                    proxy: dict | None = None) -> dict:
    from scraper.forms._common import form_search
    return form_search("spicejet_direct", HOMEPAGE, origin, destination, flight_date,
                       ORIGIN_SELECTORS, DEST_SELECTORS, DATE_SELECTORS,
                       SEARCH_SELECTORS, proxy=proxy)
