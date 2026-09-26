"""API + scraper unit/integration tests (mocked DB where noted)."""
import os

os.environ.setdefault("APIX_API_KEY", "test-key")

from fastapi.testclient import TestClient

from backend.main import app
from scraper.base import ScraperConfig
from scraper.spiders import IndigoScraper

client = TestClient(app)
AUTH = {"X-API-Key": "test-key"}


def test_health_no_auth():
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and "status" in r.json()


def test_auth_rejected():
    assert client.get("/api/v1/index/daily").status_code == 401


def test_daily_weekly_monthly_routes_heatmap_elasticity():
    for p in ["daily", "weekly", "monthly"]:
        r = client.get(f"/api/v1/index/{p}", headers=AUTH)
        assert r.status_code == 200 and len(r.json()["series"]) > 0
    assert len(client.get("/api/v1/routes", headers=AUTH).json()["routes"]) == 6
    assert len(client.get("/api/v1/fares/heatmap", headers=AUTH).json()["heatmap"]) == 6
    r = client.get("/api/v1/fares/elasticity/1", headers=AUTH)
    assert [p["window"] for p in r.json()["curve"]] == [1, 7, 15, 30, 45]
    assert client.get("/api/v1/fares/elasticity/99", headers=AUTH).status_code == 404


def test_scraper_mock_and_killswitch():
    cfg = ScraperConfig(enabled_sources={"indigo_direct": True}, delay_seconds=0,
                        respect_robots_txt=False)
    quotes = IndigoScraper(cfg).guarded_run("DEL", "BOM", 7)
    assert quotes and quotes[0].status == "success" and quotes[0].raw_payload["total_fare"] > 0
    off = ScraperConfig(enabled_sources={"indigo_direct": False})
    assert IndigoScraper(off).guarded_run("DEL", "BOM", 7) == []
