import requests

from app.config import POLYMARKET_BASE_URL
from app.db import upsert_event, upsert_market

GAMMA_SEARCH_URL = f"{POLYMARKET_BASE_URL}/public-search"
EVENTS_KEYSET_URL = f"{POLYMARKET_BASE_URL}/events/keyset"
EVENTS_BY_SLUG_URL = f"{POLYMARKET_BASE_URL}/events"


def fetch_active_events_page(limit=200, after_cursor=None):
    params = {
        "active": "true",
        "closed": "false",
        "archived": "false",
        "limit": limit,
    }
    if after_cursor:
        params["after_cursor"] = after_cursor

    response = requests.get(EVENTS_KEYSET_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def fetch_all_active_events(limit=200, max_pages=20):
    all_events = []
    next_cursor = None
    page_count = 0

    while page_count < max_pages:
        payload = fetch_active_events_page(limit=limit, after_cursor=next_cursor)

        if isinstance(payload, dict):
            events = payload.get("events", []) or payload.get("data", [])
            next_cursor = payload.get("next_cursor")
        else:
            events = payload
            next_cursor = None

        if not events:
            break

        all_events.extend(events)
        page_count += 1

        if not next_cursor:
            break

    return all_events


def fetch_events_standard(limit=200, max_pages=20):
    """Fallback path: the standard Gamma /events endpoint with offset pagination."""
    all_events = []
    for page in range(max_pages):
        params = {
            "active": "true", "closed": "false", "archived": "false",
            "limit": limit, "offset": page * limit,
            "order": "volume", "ascending": "false",
        }
        try:
            resp = requests.get(EVENTS_BY_SLUG_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            break
        if isinstance(data, list):
            events = data
        elif isinstance(data, dict):
            events = data.get("events") or data.get("data") or []
        else:
            events = []
        if not events:
            break
        all_events.extend(events)
        if len(events) < limit:
            break
    return all_events


def fetch_event_by_slug(slug: str):
    if not slug:
        return None

    response = requests.get(EVENTS_BY_SLUG_URL, params={"slug": slug}, timeout=30)
    response.raise_for_status()
    data = response.json()

    if isinstance(data, list) and data:
        return data[0]

    if isinstance(data, dict):
        events = data.get("events")
        if isinstance(events, list) and events:
            return events[0]

    return None


def search_polymarket(query: str):
    query = (query or "").strip()
    if not query:
        return {"events": [], "markets": [], "profiles": []}

    response = requests.get(
        GAMMA_SEARCH_URL,
        params={"q": query},
        timeout=30
    )
    response.raise_for_status()
    data = response.json()

    if not isinstance(data, dict):
        return {"events": [], "markets": [], "profiles": []}

    return {
        "events": data.get("events", []) or [],
        "markets": data.get("markets", []) or [],
        "profiles": data.get("profiles", []) or [],
    }


def fetch_events_with_fallback(limit=200, max_pages=20):
    """
    Try the keyset-paginated endpoint first; if it errors or returns nothing,
    fall back to the standard offset-paginated /events endpoint.
    """
    try:
        events = fetch_all_active_events(limit=limit, max_pages=max_pages)
    except Exception:
        events = []
    if not events:
        events = fetch_events_standard(limit=limit, max_pages=max_pages)
    return events


def refresh_polymarket_events(limit=200, max_pages=20):
    """Pull active events (+ nested markets) from Gamma and upsert them into SQLite."""
    events = fetch_events_with_fallback(limit=limit, max_pages=max_pages)

    saved_events = 0
    saved_markets = 0

    for event in events:
        event_id = event.get("id")
        if not event_id:
            continue

        upsert_event(event)
        saved_events += 1

        for market in event.get("markets", []) or []:
            upsert_market(market, str(event_id), event)
            saved_markets += 1

    return {
        "events_saved": saved_events,
        "markets_saved": saved_markets,
    }


def enrich_markets_from_search(query: str):
    results = search_polymarket(query)
    saved_events = 0
    saved_markets = 0

    for event_stub in results.get("events", []):
        slug = event_stub.get("slug")
        full_event = fetch_event_by_slug(slug) if slug else None
        event_obj = full_event or event_stub

        event_id = event_obj.get("id")
        if not event_id:
            continue

        upsert_event(event_obj)
        saved_events += 1

        for market in event_obj.get("markets", []) or []:
            upsert_market(market, str(event_id), event_obj)
            saved_markets += 1

    for market in results.get("markets", []):
        event_id = market.get("eventId") or market.get("event_id")
        if not event_id:
            related_events = market.get("events") or []
            if related_events and isinstance(related_events, list):
                first_event = related_events[0]
                event_id = first_event.get("id")
                if first_event.get("id"):
                    upsert_event(first_event)
                    saved_events += 1

        if event_id:
            event_context = {}
            related_events = market.get("events") or []
            if related_events and isinstance(related_events, list):
                event_context = related_events[0] or {}
                if event_context.get("id"):
                    upsert_event(event_context)
            upsert_market(market, str(event_id), event_context)
            saved_markets += 1

    return {
        "query": query,
        "events_saved": saved_events,
        "markets_saved": saved_markets,
    }