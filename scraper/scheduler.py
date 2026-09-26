"""APScheduler daily scrape cycle. Runs as a long-lived process (systemd/Procfile).

Schedule configurable via SCRAPE_CRON env (cron expression, default daily 02:00 IST).
No broker needed — BackgroundScheduler runs in-process.
"""
from __future__ import annotations

import logging
import os
from datetime import date, datetime, timedelta, timezone

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from scraper.base import ScraperConfig
from scraper.proxies import DbProxyPool, refresh_pool
from scraper.spiders import ALL_SCRAPERS
from scraper.store import get_engine, write_raw_quotes

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)


def load_basket(path: str | None = None) -> dict:
    path = path or os.path.join(os.path.dirname(__file__), "routes.yaml")
    with open(path) as f:
        return yaml.safe_load(f)


def run_cycle() -> int:
    """One full scrape cycle over all routes x windows x sources. Returns quote count.

    A shared DbProxyPool is passed to every scraper: direct requests go out on
    our own IP first, and only HTTP 40x responses fail over to the fastest
    checked proxy (see scraper.base.BlockedByStatus).
    """
    basket = load_basket()
    politeness = basket.get("politeness", {})
    cfg = ScraperConfig(
        delay_seconds=float(politeness.get("delay_seconds", 2.0)),
        respect_robots_txt=bool(politeness.get("respect_robots_txt", True)),
        enabled_sources=basket.get("enabled_sources", {}),
    )
    pool = DbProxyPool()
    engine = get_engine()
    total = 0
    for r in basket["routes"]:
        for window in basket["advance_windows"]:
            for cls in ALL_SCRAPERS:
                scraper = cls(cfg)
                quotes = scraper.guarded_run(r["origin"], r["destination"], window, proxy_pool=pool)
                total += write_raw_quotes(engine, quotes)
    log.info("scrape cycle complete: %d quotes", total)
    return total


def refresh_proxies_cycle() -> int:
    """Re-fetch the upstream list and re-check all proxies (every ~3h)."""
    ranked = refresh_pool()
    log.info("proxy refresh complete: %d working", len(ranked))
    return len(ranked)


def parse_cron(expr: str) -> CronTrigger:
    """Parse 'M H * * *' cron expression into a CronTrigger."""
    minute, hour, day, month, dow = expr.split()
    return CronTrigger(minute=minute, hour=hour, day=day, month=month, day_of_week=dow)


def main() -> None:
    cron_expr = os.environ.get("SCRAPE_CRON", "0 2 * * *")
    proxy_hours = int(os.environ.get("PROXY_REFRESH_HOURS", "3"))
    sched = BlockingScheduler()
    sched.add_job(run_cycle, parse_cron(cron_expr), id="daily_scrape")
    # Proxy list refreshes upstream ~every 3h, so re-check on the same cadence.
    # First run happens immediately at startup (background thread), then every N hours.
    sched.add_job(
        refresh_proxies_cycle, "interval", hours=proxy_hours, id="proxy_refresh",
        max_instances=1, coalesce=True,
        next_run_time=datetime.now(timezone.utc),
    )
    log.info("scheduler started: scrape cron %s, proxy refresh every %dh", cron_expr, proxy_hours)
    sched.start()


if __name__ == "__main__":
    import sys

    if "--once" in sys.argv:
        run_cycle()
    else:
        main()
