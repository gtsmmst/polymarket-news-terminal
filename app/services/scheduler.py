"""
scheduler.py - the terminal's background loop.

Every INTERVAL: pull Polymarket markets -> refine categories -> pull news
(GDELT + RSS, queries derived from market entities) -> compute mispricing
scores and alerts. A plain daemon thread, no external dependencies.
Started from main.py on application startup.
"""
import time
import threading
import datetime
import traceback

from app.services.fetch_polymarket import refresh_polymarket_events
from app.services.fetch_news import fetch_all_news
from app.services.classify_markets import refine_categories
from app.services.extract_entities import market_query_terms
from app.services import score_markets
from app.db import fetch_markets_for_scoring

_state = {"running": False, "last_run": None, "last_result": None, "runs": 0}


def run_once():
    """One full cycle. Each step is wrapped in try/except so a partial failure does not abort the rest."""
    res = {"started": datetime.datetime.utcnow().isoformat()}
    try:
        res["polymarket"] = refresh_polymarket_events(limit=200, max_pages=12)
    except Exception as e:
        res["polymarket_error"] = str(e)
    try:
        res["categories"] = refine_categories()
    except Exception as e:
        res["categories_error"] = str(e)
    try:
        mkts = fetch_markets_for_scoring(max_price=0.30, limit=400)
        qterms = market_query_terms(mkts, top=18)
        res["news"] = fetch_all_news(market_queries=qterms)
    except Exception as e:
        res["news_error"] = str(e)
    try:
        res["score"] = score_markets.run(max_price=0.30, use_ai=True)
    except Exception as e:
        res["score_error"] = str(e)
    res["finished"] = datetime.datetime.utcnow().isoformat()
    _state["last_run"] = res["finished"]
    _state["last_result"] = res
    _state["runs"] += 1
    return res


def _loop(interval_sec, first_delay):
    time.sleep(first_delay)
    while _state["running"]:
        try:
            run_once()
        except Exception:
            traceback.print_exc()
        for _ in range(interval_sec):
            if not _state["running"]:
                break
            time.sleep(1)


def start(interval_sec=900, first_delay=8):
    if _state["running"]:
        return
    _state["running"] = True
    threading.Thread(target=_loop, args=(interval_sec, first_delay), daemon=True).start()


def stop():
    _state["running"] = False


def status():
    return dict(_state)
