"""Free-proxy pool for scraping failover (stdlib only — no extra dependencies).

Source list (IN proxies, refreshed upstream ~every 3h, many dead on arrival):
    https://raw.githubusercontent.com/proxifly/free-proxy-list/refs/heads/main/proxies/countries/IN/data.txt
One ``scheme://host:port`` per line; schemes are socks4 / socks5 / http / https.

Strategy (per user request):
1. Fetch the list (this module's ``fetch_proxy_list``).
2. Liveness-check every entry against ``http://checkip.amazonaws.com/`` and
   record round-trip latency.
3. Persist results in the ``proxies`` DB table ordered by latency; scrapers
   pick the fastest working proxy when our own IP gets HTTP 40x (403/429).

NOTE on ``https://`` entries: upstream uses that scheme to label anonymity
level, not transport — the proxy itself is still spoken to as a plain HTTP
proxy, so we normalize ``https://`` -> ``http://`` when dialing.
"""
from __future__ import annotations

import argparse
import itertools
import logging
import os
import re
import socket
import struct
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import sqlalchemy as sa
from sqlalchemy import text

log = logging.getLogger(__name__)

PROXY_LIST_URL = os.environ.get(
    "PROXY_LIST_URL",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/refs/heads/main/proxies/countries/IN/data.txt",
)
CHECK_HOST = os.environ.get("PROXY_CHECK_HOST", "checkip.amazonaws.com")
CHECK_PORT = int(os.environ.get("PROXY_CHECK_PORT", "80"))
CHECK_TIMEOUT = float(os.environ.get("PROXY_CHECK_TIMEOUT", "8.0"))
CHECK_WORKERS = int(os.environ.get("PROXY_CHECK_WORKERS", "20"))

_VALID = re.compile(r"^(socks4|socks5|https?)://([^:/?#]+):(\d+)$")
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}\s*$")

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS proxies (
    endpoint     TEXT PRIMARY KEY,
    scheme       TEXT NOT NULL,
    latency_ms   INTEGER,
    working      BOOLEAN DEFAULT FALSE,
    last_checked TIMESTAMPTZ,
    fail_count   INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_proxies_working_latency ON proxies (working, latency_ms);
"""


# ---------------------------------------------------------------- parsing ---

def parse_proxy_list(raw_text: str) -> list[str]:
    """Parse raw list text into deduped proxy URLs (order-preserving).

    Normalizes ``https://`` entries to ``http://`` (see module docstring).
    Skips blanks and malformed lines.
    """
    out: list[str] = []
    seen: set[str] = set()
    for line in raw_text.splitlines():
        line = line.strip()
        m = _VALID.match(line)
        if not m:
            continue
        scheme, host, port = m.groups()
        if scheme == "https":
            scheme = "http"
        endpoint = f"{scheme}://{host}:{port}"
        if endpoint not in seen:
            seen.add(endpoint)
            out.append(endpoint)
    return out


def fetch_proxy_list(url: str = PROXY_LIST_URL, timeout: float = 20.0) -> list[str]:
    """Download and parse the upstream proxy list."""
    req = urllib.request.Request(url, headers={"User-Agent": "APIx-MoSPI-Research/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
    proxies = parse_proxy_list(raw)
    log.info("fetched %d candidate proxies from %s", len(proxies), url)
    return proxies


# --------------------------------------------------------------- checking ---

def _recvn(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("proxy closed connection during handshake")
        buf += chunk
    return buf


def _split_endpoint(proxy_url: str) -> tuple[str, str, int]:
    m = _VALID.match(proxy_url)
    if not m:
        raise ValueError(f"bad proxy URL: {proxy_url}")
    scheme, host, port = m.groups()
    return scheme, host, int(port)


def _dial_socks(proxy_url: str, target_host: str, target_port: int, timeout: float) -> socket.socket:
    """Open a TCP tunnel to target_host:port through a SOCKS4/5 proxy (stdlib)."""
    _, phost, pport = _split_endpoint(proxy_url)
    scheme = proxy_url.split("://")[0]
    sock = socket.create_connection((phost, pport), timeout=timeout)
    sock.settimeout(timeout)
    try:
        if scheme == "socks5":
            sock.sendall(b"\x05\x01\x00")
            if _recvn(sock, 2) != b"\x05\x00":
                raise ConnectionError("SOCKS5: no-auth not accepted")
            req = b"\x05\x01\x00\x03" + bytes([len(target_host)]) + target_host.encode() \
                + struct.pack(">H", target_port)
            sock.sendall(req)
            rep = _recvn(sock, 4)
            if rep[1] != 0x00:
                raise ConnectionError(f"SOCKS5 connect failed: {rep[1]:#x}")
            atyp = rep[3]
            if atyp == 0x01:
                _recvn(sock, 4)
            elif atyp == 0x03:
                _recvn(sock, 1 + _recvn(sock, 1)[0])
            elif atyp == 0x04:
                _recvn(sock, 16)
            else:
                raise ConnectionError("SOCKS5: bad address type")
            _recvn(sock, 2)  # port
        else:  # socks4 (IPv4 only — resolve target locally)
            ip = socket.gethostbyname(target_host)
            sock.sendall(b"\x04\x01" + struct.pack(">H", target_port) + socket.inet_aton(ip) + b"\x00")
            if _recvn(sock, 8)[1] != 0x5A:
                raise ConnectionError("SOCKS4 connect rejected")
        return sock
    except Exception:
        sock.close()
        raise


def _dial_http_proxy(proxy_url: str, timeout: float) -> socket.socket:
    """Open TCP connection to an HTTP proxy (request itself verifies liveness)."""
    _, phost, pport = _split_endpoint(proxy_url)
    sock = socket.create_connection((phost, pport), timeout=timeout)
    sock.settimeout(timeout)
    return sock


def check_proxy(
    proxy_url: str,
    target_host: str = CHECK_HOST,
    target_port: int = CHECK_PORT,
    timeout: float = CHECK_TIMEOUT,
) -> float | None:
    """Check one proxy against checkip.amazonaws.com.

    Returns latency in milliseconds, or None if the proxy is dead/blocked.
    Success = HTTP 200 whose body is an IPv4 address (the proxy's egress IP).
    """
    start = time.monotonic()
    sock: socket.socket | None = None
    try:
        scheme = proxy_url.split("://")[0]
        if scheme in ("socks4", "socks5"):
            sock = _dial_socks(proxy_url, target_host, target_port, timeout)
            request = (
                f"GET / HTTP/1.0\r\nHost: {target_host}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode()
        else:
            sock = _dial_http_proxy(proxy_url, timeout)
            request = (
                f"GET http://{target_host}/ HTTP/1.0\r\nHost: {target_host}\r\n"
                f"Connection: close\r\n\r\n"
            ).encode()
        sock.sendall(request)
        resp = b""
        while len(resp) < 65536:
            chunk = sock.recv(4096)
            if not chunk:
                break
            resp += chunk
        latency_ms = (time.monotonic() - start) * 1000.0
        head, _, body = resp.partition(b"\r\n\r\n")
        status_line = head.split(b"\r\n", 1)[0] if head else b""
        if b"200" in status_line and _IPV4.match(body.decode("utf-8", errors="replace")):
            return latency_ms
        return None
    except Exception:
        return None
    finally:
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass


def rank_proxies(results: dict[str, float | None]) -> list[tuple[str, float]]:
    """Order check results by latency, fastest first; drop dead entries."""
    return sorted(
        ((url, lat) for url, lat in results.items() if lat is not None),
        key=lambda kv: kv[1],
    )


# ------------------------------------------------------------ persistence ---

def get_engine(url: str | None = None) -> sa.Engine:
    return sa.create_engine(
        url or os.environ.get("DATABASE_URL", "postgresql+psycopg://postgres:postgres@localhost:5432/apix")
    )


def ensure_proxy_table(engine: sa.Engine) -> None:
    """Create the proxies table if missing (also present in db/schema.sql)."""
    with engine.begin() as conn:
        for stmt in (CREATE_TABLE_SQL,):
            for part in [s.strip() for s in stmt.split(";") if s.strip()]:
                conn.execute(text(part))


def store_results(engine: sa.Engine, results: dict[str, float | None]) -> list[tuple[str, float]]:
    """Upsert check results; dead proxies marked not-working with fail_count+1.

    Returns the working proxies ordered by latency (fastest first).
    """
    ranked = rank_proxies(results)
    rows = [
        {
            "endpoint": url,
            "scheme": url.split("://")[0],
            "latency_ms": int(lat) if lat is not None else None,
            "working": lat is not None,
        }
        for url, lat in results.items()
    ]
    with engine.begin() as conn:
        if rows:
            conn.execute(
                text(
                    """INSERT INTO proxies (endpoint, scheme, latency_ms, working, last_checked, fail_count)
                    VALUES (:endpoint, :scheme, :latency_ms, :working, now(), 0)
                    ON CONFLICT (endpoint) DO UPDATE SET
                        scheme = EXCLUDED.scheme,
                        latency_ms = EXCLUDED.latency_ms,
                        working = EXCLUDED.working,
                        last_checked = now(),
                        fail_count = CASE WHEN EXCLUDED.working THEN 0
                                         ELSE proxies.fail_count + 1 END"""
                ),
                rows,
            )
        # Prune stale dead entries (unchecked >24h and not working).
        conn.execute(
            text("DELETE FROM proxies WHERE NOT working AND last_checked < now() - INTERVAL '24 hours'")
        )
    log.info("%d/%d proxies working", len(ranked), len(results))
    return ranked


def refresh_pool(
    database_url: str | None = None,
    proxy_list_url: str = PROXY_LIST_URL,
    max_workers: int = CHECK_WORKERS,
    timeout: float = CHECK_TIMEOUT,
    limit: int | None = None,
) -> list[tuple[str, float]]:
    """Full refresh: fetch list -> check all -> store ordered by latency."""
    proxies = fetch_proxy_list(proxy_list_url)
    if limit is not None:
        proxies = proxies[:limit]
    results: dict[str, float | None] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        latencies = pool.map(lambda p: check_proxy(p, timeout=timeout), proxies)
        for url, lat in zip(proxies, latencies):
            results[url] = lat
    engine = get_engine(database_url)
    try:
        ensure_proxy_table(engine)
        return store_results(engine, results)
    finally:
        engine.dispose()


def fastest_proxies(engine: sa.Engine, limit: int = 5) -> list[str]:
    """Fastest currently-working proxies, best first."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT endpoint FROM proxies WHERE working ORDER BY latency_ms ASC NULLS LAST LIMIT :n"),
            {"n": limit},
        ).all()
    return [r[0] for r in rows]


# ------------------------------------------------------------------ pool ---

class DbProxyPool:
    """Pluggable proxy pool (satisfies scraper.base.ProxyProvider).

    Round-robins across the top-N fastest working proxies so failover traffic
    is spread instead of hammering a single free proxy.
    """

    def __init__(self, database_url: str | None = None, top_n: int = 5):
        self.database_url = database_url
        self.top_n = top_n
        self._cycle = itertools.cycle(range(top_n))

    def get_proxy(self) -> str | None:
        """Return next fastest-working proxy, or None if the pool is empty."""
        try:
            engine = get_engine(self.database_url)
            try:
                candidates = fastest_proxies(engine, self.top_n)
            finally:
                engine.dispose()
        except Exception as exc:
            log.warning("proxy pool unreachable: %s", exc)
            return None
        if not candidates:
            return None
        return candidates[next(self._cycle) % len(candidates)]

    def report_bad(self, proxy_url: str) -> None:
        """Mark a proxy not-working (call when a request through it fails)."""
        try:
            engine = get_engine(self.database_url)
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE proxies SET working = FALSE, fail_count = fail_count + 1 "
                             "WHERE endpoint = :e"),
                        {"e": proxy_url},
                    )
            finally:
                engine.dispose()
        except Exception as exc:
            log.warning("report_bad failed: %s", exc)


# ------------------------------------------------------------------- cli ---

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Refresh the free-proxy pool (check vs checkip.amazonaws.com).")
    ap.add_argument("--limit", type=int, default=None, help="only check first N proxies (for testing)")
    ap.add_argument("--workers", type=int, default=CHECK_WORKERS)
    ap.add_argument("--timeout", type=float, default=CHECK_TIMEOUT)
    ap.add_argument("--list-url", default=PROXY_LIST_URL)
    args = ap.parse_args(argv)
    ranked = refresh_pool(
        proxy_list_url=args.list_url, max_workers=args.workers,
        timeout=args.timeout, limit=args.limit,
    )
    print(f"{len(ranked)} working proxies (fastest first):")
    for url, lat in ranked[:15]:
        print(f"  {lat:8.0f} ms  {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
