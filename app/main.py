"""
FastAPI entry point.

Serves the JSON API under /api/* and the static single-page dashboard from
app/static. On startup it creates the SQLite schema, seeds one demo market and
(unless SCHEDULER_ENABLED=0) starts the background refresh loop.
"""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import (
    APP_NAME,
    SCHEDULER_ENABLED,
    SCHEDULER_FIRST_DELAY_SEC,
    SCHEDULER_INTERVAL_SEC,
)
from app.db import (
    clear_demo_data,
    clear_news_data,
    clear_polymarket_data,
    create_tables,
    fetch_alerts_for_market,
    fetch_all_active_alerts,
    fetch_all_headlines,
    fetch_all_markets,
    fetch_grouped_events,
    fetch_headlines_for_market,
    fetch_markets_for_scoring,
    fetch_score_for_market,
    fetch_top_opportunities,
    seed_sample_data,
)
from app.services import scheduler
from app.services.extract_entities import market_query_terms
from app.services.fetch_news import fetch_all_news
from app.services.fetch_polymarket import (
    enrich_markets_from_search,
    refresh_polymarket_events,
)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    create_tables()
    seed_sample_data()
    # Background engine: markets -> categories -> news -> mispricing score + alerts.
    if SCHEDULER_ENABLED:
        scheduler.start(interval_sec=SCHEDULER_INTERVAL_SEC, first_delay=SCHEDULER_FIRST_DELAY_SEC)
    try:
        yield
    finally:
        scheduler.stop()


app = FastAPI(title=APP_NAME, lifespan=lifespan)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ----- markets ---------------------------------------------------------------
@app.get("/api/markets")
def get_markets(
    category: str = "politics_plus",
    min_price: float = 0.001,
    max_price: float = 0.20,
    min_liquidity: float = 0,
    search: str = "",
    sort_by: str = "liquidity",
):
    if search.strip():
        enrich_markets_from_search(search)

    return fetch_all_markets(
        category=category,
        min_price=min_price,
        max_price=max_price,
        min_liquidity=min_liquidity,
        search=search,
        sort_by=sort_by,
    )


@app.get("/api/event-groups")
def get_event_groups(
    category: str = "politics_plus",
    min_price: float = 0.001,
    max_price: float = 0.20,
    min_liquidity: float = 0,
    search: str = "",
    sort_by: str = "liquidity",
):
    if search.strip():
        enrich_markets_from_search(search)

    return fetch_grouped_events(
        category=category,
        min_price=min_price,
        max_price=max_price,
        min_liquidity=min_liquidity,
        search=search,
        sort_by=sort_by,
    )


@app.get("/api/headlines")
def get_headlines():
    return fetch_all_headlines()


@app.get("/api/markets/{market_id}/headlines")
def get_market_headlines(market_id: str):
    return fetch_headlines_for_market(market_id)


@app.get("/api/markets/{market_id}/score")
def get_market_score(market_id: str):
    return fetch_score_for_market(market_id)


@app.get("/api/markets/{market_id}/alerts")
def get_market_alerts(market_id: str):
    return fetch_alerts_for_market(market_id)


# ----- refresh / maintenance -------------------------------------------------
@app.post("/api/refresh/polymarket")
def refresh_polymarket():
    return refresh_polymarket_events(limit=200, max_pages=20)


@app.post("/api/refresh/news")
def refresh_news():
    mkts = fetch_markets_for_scoring(max_price=0.30, limit=400)
    qterms = market_query_terms(mkts, top=18)
    return fetch_all_news(market_queries=qterms)


@app.post("/api/refresh/all")
def refresh_all():
    """Run one full cycle synchronously: markets + categories + news + scoring."""
    return scheduler.run_once()


@app.get("/api/scheduler/status")
def scheduler_status():
    return scheduler.status()


@app.post("/api/clear-polymarket")
def clear_polymarket():
    clear_polymarket_data()
    return {"status": "all polymarket data cleared"}


@app.post("/api/clear-demo")
def clear_demo():
    clear_demo_data()
    return {"status": "demo data cleared"}


@app.post("/api/clear-news")
def clear_news():
    clear_news_data()
    return {"status": "news data cleared"}


# ----- signals ---------------------------------------------------------------
@app.get("/api/opportunities")
def opportunities(limit: int = 50):
    return fetch_top_opportunities(limit=limit)


@app.get("/api/alerts")
def alerts(limit: int = 80):
    return fetch_all_active_alerts(limit=limit)


# Static dashboard (must be mounted last so /api/* routes take precedence).
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
