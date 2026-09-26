"""Compliant per-provider arrangements: allowed entry points + next steps.

This registry is the answer to "what about the other providers": each source
gets ONE sanctioned live path that honours robots.txt, never solves CAPTCHAs,
and never defeats PerimeterX/Akamai/Datadome. Status values:

* ``live``      — working form flow today (EaseMyTrip).
* ``scaffold``  — homepage/search shell loads HTTP 200 with no block markers
  from a residential IP; needs an EMT-style form module (see scraper/emt.py).
* ``api_only``  — scraping disallowed or hard-gated; official NDC / affiliate
  API partnership required (Ixigo, Air India Express, MMT/Goibibo).
* ``parked``    — hard gate; no live hits until the gate clears.

To add a provider: copy the EaseMyTrip pattern (homepage form -> airport
pickers -> date fill -> search click -> scoped fare parse in scraper/live.py),
register the entry here, and flip its ``enabled_sources`` flag in
``scraper/routes.yaml``. Kill-switch stays instant: set the flag false.
"""
from __future__ import annotations

PROVIDERS: dict[str, dict[str, str]] = {
    "easemytrip": {
        "status": "live",
        "entry": "homepage form (scraper/emt.py)",
        "robots": "allowed (only /flight-search/listing* disallowed)",
        "next": "none — in production",
    },
    "spicejet_direct": {
        "status": "form_scaffold",
        "entry": "homepage form scraper/forms/spicejet.py (React-Native test IDs + positional inputs; robots open; never /api/v1)",
        "robots": "allowed",
        "next": "form submits with multi-currency (₹, Rs, INR) parsing and non-blocking SPA submit",
    },
    "akasa_direct": {
        "status": "live",
        "entry": "homepage form scraper/forms/akasa.py (proven 2026-10-04: DEL-BOM T+7 Rs 3,500, 25 fares)",
        "robots": "allowed",
        "next": "none — in production; monitor for DOM drift",
    },
    "cleartrip": {
        "status": "form_scaffold",
        "entry": "homepage form scraper/forms/cleartrip.py with deep link fallback (/flights/results allowed; never /flights/search*)",
        "robots": "allowed for /flights/results and homepage",
        "next": "form-first flow with scoped-first fare extraction and popup dismissal",
    },
    "indigo_direct": {
        "status": "form_scaffold",
        "entry": "homepage form scraper/forms/indigo.py (stock Chromium: submits, no priced fares; real Chrome: widget doesn't render — flaky bot-gating)",
        "robots": "homepage allowed (CLI fetch times out; fail-open)",
        "next": "gating is client-flaky — NDC/API partnership recommended over more DOM work",
    },
    "airindia_direct": {
        "status": "form_scaffold",
        "entry": "homepage form scraper/forms/airindia.py, form-only (deep link 404s). Self-selects real Chrome (preferred_channel); bundled Chromium gets TLS-hung",
        "robots": "homepage allowed (CLI fetch times out; fail-open)",
        "next": "form SUBMITS (OneTrust + combobox fixes 2026-10-04) but results carry no priced fares — official API likely required",
    },
    "yatra": {
        "status": "api_only",
        "entry": "affiliate API default via scraper/provider_apis.py (YATRA_*); APIX_SCRAPE_PARKED=true attempts the homepage form ONLY (no deep-link fallback — XHR trigger never fetched; stale under Diya-AI redesign)",
        "robots": "homepage reachable, no mappable classic form",
        "next": "affiliate partnership; never hit the challenged XHR trigger",
    },
    "ixigo": {
        "status": "api_only",
        "entry": "official API ONLY via scraper/ixigo_api.py — no form path, no env backdoor (forms/ixigo.py archived, unwired)",
        "robots": "DISALLOWED /search/result/ + /api/ (gate parks it)",
        "next": "Ixigo API partnership (IXIGO_API_KEY); scraping stays parked",
    },
    "airindia_express": {
        "status": "api_only",
        "entry": "official API default via scraper/provider_apis.py (AIX_*); form flow available in scraper/forms/airindia_express.py (APIX_SCRAPE_PARKED=true)",
        "robots": "n/a (CAPTCHA gate)",
        "next": "AIX API/NDC partnership or opt-in live form scrape via APIX_SCRAPE_PARKED=true",
    },
    "makemytrip": {
        "status": "api_only",
        "entry": "affiliate API default via scraper/provider_apis.py (MMT_*); form flow available in scraper/forms/makemytrip.py (APIX_SCRAPE_PARKED=true)",
        "robots": "homepage TLS-blocks automation",
        "next": "MMT affiliate partnership or opt-in live form scrape via APIX_SCRAPE_PARKED=true",
    },
    "goibibo": {
        "status": "api_only",
        "entry": "affiliate API default via scraper/provider_apis.py (GOIBIBO_*); form flow available in scraper/forms/goibibo.py (APIX_SCRAPE_PARKED=true)",
        "robots": "challenge-validation shell + timeouts",
        "next": "Goibibo affiliate partnership or opt-in live form scrape via APIX_SCRAPE_PARKED=true",
    },
}


def get_provider(source: str) -> dict[str, str]:
    """Return the arrangement record for a source (unknown -> parked)."""
    return PROVIDERS.get(source, {"status": "parked", "entry": "unknown", "robots": "unknown", "next": "triage"})
