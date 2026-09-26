"""APScheduler daily scrape cycle. Runs as a long-lived process (systemd/Procfile).

Schedule configurable via SCRAPE_CRON env (cron expression, default daily 02:00 IST).
No broker needed — BackgroundScheduler runs in-process.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import date, datetime, timedelta, timezone

import yaml
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from scraper.base import ScraperConfig
from scraper.proxies import DbProxyPool, refresh_pool
from scraper.spiders import ALL_SCRAPERS, MOCK
from scraper.store import get_engine, write_raw_quotes

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass


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
    # Politeness delays exist to rate-limit LIVE hits; mock mode touches no
    # network, so sleeping 2s x 330 runs (~11 min) would be pure waste.
    delay = 0.0 if MOCK else float(politeness.get("delay_seconds", 2.0))
    cfg = ScraperConfig(
        delay_seconds=delay,
        respect_robots_txt=bool(politeness.get("respect_robots_txt", True)),
        enabled_sources=basket.get("enabled_sources", {}),
    )
    pool = DbProxyPool()
    engine = get_engine()
    routes = basket["routes"]
    windows = basket["advance_windows"]
    n_jobs = len(routes) * len(windows) * len(ALL_SCRAPERS)
    log.info(
        "scrape cycle starting: %d routes x %d windows x %d sources = %d jobs (mock=%s, delay=%.1fs)",
        len(routes), len(windows), len(ALL_SCRAPERS), n_jobs, MOCK, delay,
    )
    total = 0
    done = 0
    t_start = time.monotonic()
    for r in routes:
        for window in windows:
            for cls in ALL_SCRAPERS:
                scraper = cls(cfg)
                label = f"{r['origin']}-{r['destination']} T+{window} [{scraper.source}]"
                try:
                    t0 = time.monotonic()
                    quotes = scraper.guarded_run(r["origin"], r["destination"], window, proxy_pool=pool)
                    try:
                        n_written = write_raw_quotes(engine, quotes)
                    except Exception as exc:  # noqa: BLE001 — keep going on a write failure
                        log.error("[%s] write to raw_fare_quotes failed: %s", scraper.source, exc)
                        n_written = 0
                    total += n_written
                    done += 1
                    log.info(
                        "%s done in %.1fs: %d quotes written (%d/%d jobs, %.0f%%)",
                        label, time.monotonic() - t0, n_written, done, n_jobs,
                        100.0 * done / n_jobs,
                    )
                except Exception as exc:  # noqa: BLE001 — one bad source must not kill the cycle
                    done += 1
                    log.exception("%s scrape crashed, skipping: %s", label, exc)
    log.info(
        "scrape cycle complete: %d quotes in %.1fs", total, time.monotonic() - t_start
    )
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
