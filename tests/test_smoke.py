"""
Smoke tests. No network, no real database: the scoring helpers are pure
functions and the API test uses FastAPI's TestClient with the scheduler disabled
(see conftest.py).
"""
import datetime

import pytest

from app.services import score_markets as sm
from app.services.extract_entities import keywords, named_keywords


def _in_days(n):
    return (datetime.datetime.utcnow() + datetime.timedelta(days=n)).isoformat()


# ----------------------------------------------------------------- scoring core
def test_compute_factors_cheap_market_with_fresh_tier1_news():
    market = {
        "id": "m1",
        "title": "Will the US and Iran announce a deal before July?",
        "yes_price": 0.08,
        "liquidity": 12500.0,
        "end_date": _in_days(30),
        "resolution_text": "Resolves YES if an official deal is announced.",
    }
    # (relevance, source_tier, sentiment, recency_weight)
    matched = [(0.9, 1, 1.0, 1.0), (0.7, 2, -1.0, 0.8), (0.5, 1, 0.0, 0.5)]

    f = sm.compute_factors(market, matched)

    assert f["news_velocity"] == 34.5            # (1.0 + 0.8 + 0.5) * 15
    assert f["source_quality"] == 100.0          # best tier is 1
    assert f["sentiment_shift"] == 0.09          # (1.0 - 0.8 + 0) / 2.3
    assert f["price_dislocation"] == 31.7        # 34.5 * (1 - 0.08)
    assert f["liquidity_score"] == 100.0         # clamped
    assert f["time_decay"] == 100.0              # 30 days out
    assert f["resolution_risk"] == 0.0
    assert f["opportunity_score"] == 57.1
    assert 0.0 <= f["opportunity_score"] <= 100.0


def test_compute_factors_no_news_lottery_market_scores_zero():
    market = {
        "id": "m2",
        "title": "Will X happen?",
        "yes_price": 0.01,                       # lottery price
        "liquidity": 500.0,                      # thin book
        "end_date": _in_days(400),               # distant horizon
        "resolution_text": "x" * 500,            # long / complex rules
    }
    f = sm.compute_factors(market, [])

    assert f["news_velocity"] == 0.0
    assert f["source_quality"] == 0.0
    assert f["sentiment_shift"] == 0.0
    assert f["price_dislocation"] == 0.0
    assert f["time_decay"] == 25.0
    assert f["resolution_risk"] == 100.0         # 40 + 30 + 15 + 15
    assert f["opportunity_score"] == 0.0         # penalty dominates, clamped at 0


def test_compute_factors_handles_missing_fields():
    f = sm.compute_factors({"id": "m3"}, [])
    assert f["time_decay"] == 50.0               # unknown end date
    assert f["resolution_risk"] == 55.0          # yes<0.02 (40) + liq<1000 (15)
    assert set(f) == {
        "price_dislocation", "news_velocity", "sentiment_shift", "source_quality",
        "time_decay", "resolution_risk", "liquidity_score", "opportunity_score",
    }


def test_more_news_means_higher_opportunity():
    market = {"id": "m4", "yes_price": 0.10, "liquidity": 5000.0,
              "end_date": _in_days(20), "resolution_text": "short"}
    quiet = sm.compute_factors(market, [(0.5, 2, 0.0, 0.3)])
    busy = sm.compute_factors(market, [(0.5, 2, 0.0, 0.3)] * 6)
    assert busy["opportunity_score"] > quiet["opportunity_score"]


def test_build_alerts_rules():
    market = {"id": "m5", "yes_price": 0.08}
    f = {"news_velocity": 45.0, "source_quality": 100.0, "resolution_risk": 75.0}
    types = [a["alert_type"] for a in sm.build_alerts(market, f)]
    assert types == ["news_spike", "tier1", "risk"]
    for a in sm.build_alerts(market, f):
        assert a["severity"] in {"high", "medium", "low"}
        assert a["alert_text"]


def test_parse_dt_normalises_timezones_to_utc():
    assert sm._parse_dt("Sat, 11 Oct 2026 12:00:00 +0300") == datetime.datetime(2026, 10, 11, 9, 0, 0)
    assert sm._parse_dt("2026-10-11T12:00:00Z") == datetime.datetime(2026, 10, 11, 12, 0, 0)
    assert sm._parse_dt("not a date") is None


def test_ai_assess_is_noop_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert sm.ai_assess([({"id": "m1", "title": "t", "yes_price": 0.1}, ["headline"])]) == {}


# ----------------------------------------------------------------- entities
def test_keywords_pick_up_named_entities():
    kw = keywords("Iran and Israel agree to a ceasefire after North Korea missile talks")
    assert {"iran", "israel", "ceasefire", "north korea", "missile"} <= kw
    assert "after" not in kw                      # stop word
    assert "federal reserve" in named_keywords("Federal Reserve holds rates steady")


# ----------------------------------------------------------------- API
def test_api_boots_and_serves_demo_market():
    fastapi_testclient = pytest.importorskip("fastapi.testclient")
    from app.main import app

    with fastapi_testclient.TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}

        groups = client.get("/api/event-groups", params={"category": "all"}).json()
        ids = {m["id"] for g in groups for m in g["markets"]}
        assert "market_demo_1" in ids              # seeded on startup

        assert client.get("/api/scheduler/status").json()["running"] is False
        assert client.get("/").status_code == 200   # static dashboard
