"""Live audit: attempt one real fare quote per source and report per-platform status.

Usage:
    APIX_SCRAPER_MOCK=false ./venv/bin/python -m scraper.audit DEL BOM --window 7
    ./venv/bin/python -m scraper.audit --all-routes   # all 6 basket routes x 11 sources
    ./venv/bin/python -m scraper.audit --routes DEL-BOM,BLR-HYD --only easemytrip,akasa_direct

Forces live mode regardless of APIX_SCRAPER_MOCK. Each row shows whether the
platform is scrapable right now (success + fare), blocked (403/429/CAPTCHA),
or needs selector/URL calibration (failed). Robots-parked sources are reported
as ROBOTS_PARKED and never fetched — there is no flag that fetches a
robots-disallowed page. Exit code 0 if >=1 source works.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import scraper.spiders as spiders
from scraper.base import ScraperConfig

spiders.MOCK = False  # audit is always live

ROUTES = ["DEL-BOM", "DEL-BLR", "BOM-BLR", "DEL-CCU", "BLR-HYD", "MAA-DEL"]


def audit_one(origin: str, destination: str, window: int, pool=None,
                only: list[str] | None = None,
                report_gate: bool = False) -> list[dict]:
    # The robots gate is ALWAYS enforced inside guarded_run; there is no
    # parameter that fetches a robots-disallowed page.
    cfg = ScraperConfig(delay_seconds=2.0, respect_robots_txt=True,
                        enabled_sources={c.source: True for c in spiders.ALL_SCRAPERS})
    rows = []
    classes = [c for c in spiders.ALL_SCRAPERS if not only or c.source in only]
    for cls in classes:
        spider = cls(cfg)
        url = spider.search_url(origin, destination,
                                __import__("datetime").date.today() +
                                __import__("datetime").timedelta(days=window)) \
            if spider.SEARCH_URL else "(no SEARCH_URL)"
        gate = None
        if report_gate:
            try:
                gate = "allowed" if spider.check_robots(
                    spider.robots_target(origin, destination, window)) else "parked"
            except Exception:
                gate = "unknown"
            if gate == "parked":
                # Report the gate decision WITHOUT fetching the disallowed page.
                rows.append({"source": spider.source, "status": "ROBOTS_PARKED",
                             "fare": None, "detail": "robots_disallowed (not fetched)",
                             "url": url, "confidence": spider.CONFIDENCE, "gate": gate})
                continue
        try:
            quotes = spider.guarded_run(origin, destination, window, proxy_pool=pool)
            q = quotes[0] if quotes else None
            if q and q.status == "success":
                rows.append({"source": spider.source, "status": "SUCCESS",
                             "fare": q.raw_payload.get("total_fare"),
                             "detail": f"seen={q.raw_payload.get('n_fares_seen')}"})
            else:
                rows.append({"source": spider.source, "status": (q.status if q else "no-quote").upper(),
                             "fare": None, "detail": str((q.raw_payload if q else {}))[:100]})
        except Exception as exc:  # noqa: BLE001 — audit must never crash
            rows.append({"source": spider.source, "status": "ERROR", "fare": None, "detail": str(exc)[:100]})
        rows[-1]["url"] = url
        rows[-1]["confidence"] = spider.CONFIDENCE
        if report_gate:
            rows[-1]["gate"] = gate
    return rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Audit live scrapability per platform.")
    ap.add_argument("origin", nargs="?", default="DEL")
    ap.add_argument("destination", nargs="?", default="BOM")
    ap.add_argument("--window", type=int, default=7)
    ap.add_argument("--all-routes", action="store_true")
    ap.add_argument("--with-proxies", action="store_true",
                    help="refresh a small proxy pool first and fail over via fastest proxy on 40x")
    ap.add_argument("--ignore-robots", action="store_true",
                    help="also show each source's robots-gate decision; disallowed "
                         "pages are still NEVER fetched (reported as ROBOTS_PARKED)")
    ap.add_argument("--routes", default=None,
                    help="comma-separated airport combos, e.g. DEL-BOM,BLR-HYD "
                         "(overrides origin/destination/--all-routes)")
    ap.add_argument("--only", default=None,
                    help="comma-separated sources, e.g. easemytrip,akasa_direct")
    args = ap.parse_args(argv)

    pool = None
    if args.with_proxies:
        from scraper.proxies import DbProxyPool, refresh_pool
        print("refreshing proxy pool (first 40 candidates)...")
        ranked = refresh_pool(limit=40)
        print(f"{len(ranked)} working proxies")
        pool = DbProxyPool()

    if args.routes:
        routes = [r.strip().upper() for r in args.routes.split(",") if r.strip()]
    else:
        routes = ROUTES if args.all_routes else [f"{args.origin}-{args.destination}"]
    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
    if only:
        known = {c.source for c in spiders.ALL_SCRAPERS}
        unknown = [s for s in only if s not in known]
        if unknown:
            print(f"unknown sources: {', '.join(unknown)} (known: {', '.join(sorted(known))})")
            return 2
    ok = 0
    for r in routes:
        o, d = r.split("-")
        print(f"\n=== {o}-{d} T+{args.window} ===")
        print(f"{'source':<18}{'status':<16}{'fare':<10}detail")
        for row in audit_one(o, d, args.window, pool=pool, only=only,
                             report_gate=args.ignore_robots):
            if row["status"] == "SUCCESS":
                ok += 1
            extra = f" gate={row['gate']}" if "gate" in row else ""
            print(f"{row['source']:<18}{row['status']:<16}{str(row['fare']):<10}{row['detail']}{extra}")
    print(f"\n{ok} successful live quotes.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
