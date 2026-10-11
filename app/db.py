import os
import sqlite3
import datetime

from app.config import DATABASE_PATH


def get_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def create_tables():
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events (
        id TEXT PRIMARY KEY,
        title TEXT,
        slug TEXT,
        tags TEXT,
        start_date TEXT,
        end_date TEXT,
        last_updated TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS markets (
        id TEXT PRIMARY KEY,
        event_id TEXT,
        title TEXT,
        slug TEXT,
        category TEXT,
        yes_price REAL,
        no_price REAL,
        spread REAL,
        liquidity REAL,
        volume_24h REAL,
        end_date TEXT,
        resolution_text TEXT,
        last_updated TEXT,
        FOREIGN KEY (event_id) REFERENCES events (id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS headlines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_name TEXT,
        source_tier INTEGER,
        title TEXT,
        url TEXT,
        published_at TEXT,
        sentiment REAL,
        summary TEXT,
        raw_text_hash TEXT
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS market_headlines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT,
        headline_id INTEGER,
        relevance_score REAL,
        matched_by TEXT,
        FOREIGN KEY (market_id) REFERENCES markets (id),
        FOREIGN KEY (headline_id) REFERENCES headlines (id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS market_scores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT,
        price_dislocation REAL,
        news_velocity REAL,
        sentiment_shift REAL,
        source_quality REAL,
        time_decay REAL,
        resolution_risk REAL,
        liquidity_score REAL,
        opportunity_score REAL,
        updated_at TEXT,
        FOREIGN KEY (market_id) REFERENCES markets (id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT,
        alert_type TEXT,
        alert_text TEXT,
        severity TEXT,
        created_at TEXT,
        is_active INTEGER DEFAULT 1,
        FOREIGN KEY (market_id) REFERENCES markets (id)
    )
    """)

    conn.commit()
    conn.close()


def seed_sample_data():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) AS count FROM markets")
    market_count = cursor.fetchone()["count"]

    if market_count == 0:
        now = datetime.datetime.utcnow().isoformat()

        cursor.execute("""
        INSERT INTO events (id, title, slug, tags, start_date, end_date, last_updated)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            "event_demo_1",
            "US-Iran diplomacy demo event",
            "us-iran-diplomacy-demo-event",
            "politics,iran,usa,diplomacy",
            now,
            "2026-12-31T23:59:59",
            now
        ))

        cursor.execute("""
        INSERT INTO markets (
            id, event_id, title, slug, category, yes_price, no_price, spread,
            liquidity, volume_24h, end_date, resolution_text, last_updated
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "market_demo_1",
            "event_demo_1",
            "US and Iran strike a deal before July?",
            "us-iran-deal-before-july-demo",
            "politics",
            0.08,
            0.92,
            0.02,
            12500.0,
            3400.0,
            "2026-06-30T23:59:59",
            "Resolves YES if an official deal is announced before July 1, 2026.",
            now
        ))

    conn.commit()
    conn.close()


def clear_demo_data():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM alerts WHERE market_id LIKE 'market_demo_%'")
    cursor.execute("DELETE FROM market_scores WHERE market_id LIKE 'market_demo_%'")
    cursor.execute("DELETE FROM market_headlines WHERE market_id LIKE 'market_demo_%'")
    cursor.execute("DELETE FROM headlines WHERE raw_text_hash LIKE 'demo_hash_%'")
    cursor.execute("DELETE FROM markets WHERE id LIKE 'market_demo_%'")
    cursor.execute("DELETE FROM events WHERE id LIKE 'event_demo_%'")
    conn.commit()
    conn.close()


def clear_polymarket_data():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM market_headlines")
    cursor.execute("DELETE FROM market_scores")
    cursor.execute("DELETE FROM alerts")
    cursor.execute("DELETE FROM markets WHERE id NOT LIKE 'market_demo_%'")
    cursor.execute("DELETE FROM events WHERE id NOT LIKE 'event_demo_%'")
    conn.commit()
    conn.close()


def fetch_all_markets(category="politics_plus", min_price=0.001, max_price=0.20, min_liquidity=0, search="", sort_by="liquidity"):
    conn = get_connection()
    cursor = conn.cursor()

    allowed_sort_fields = {
        "liquidity": "m.liquidity DESC, m.volume_24h DESC, m.last_updated DESC",
        "volume": "m.volume_24h DESC, m.liquidity DESC, m.last_updated DESC",
        "price_asc": "m.yes_price ASC, m.liquidity DESC, m.last_updated DESC",
        "price_desc": "m.yes_price DESC, m.liquidity DESC, m.last_updated DESC",
        "newest": "m.last_updated DESC, m.liquidity DESC, m.volume_24h DESC",
    }
    order_clause = allowed_sort_fields.get(sort_by, allowed_sort_fields["liquidity"])

    search_term = f"%{(search or '').lower()}%"
    params = [min_price, max_price, min_liquidity]

    category_clause = ""
    if category == "politics_plus":
        category_clause = "AND lower(m.category) IN ('politics', 'geopolitics')"
    elif category != "all":
        category_clause = "AND lower(m.category) = ?"
        params.append(category.lower())

    query = f"""
    SELECT
        m.id,
        m.event_id,
        m.title,
        m.slug,
        m.category,
        m.yes_price,
        m.no_price,
        m.spread,
        m.liquidity,
        m.volume_24h,
        m.end_date,
        m.resolution_text,
        m.last_updated,
        e.slug AS event_slug,
        e.title AS event_title,
        e.tags AS event_tags
    FROM markets m
    LEFT JOIN events e ON m.event_id = e.id
    WHERE m.yes_price >= ?
      AND m.yes_price <= ?
      AND m.liquidity >= ?
      {category_clause}
      AND (
        lower(m.title) LIKE ?
        OR lower(m.slug) LIKE ?
        OR lower(COALESCE(m.resolution_text, '')) LIKE ?
        OR lower(COALESCE(e.title, '')) LIKE ?
        OR lower(COALESCE(e.tags, '')) LIKE ?
        OR lower(COALESCE(m.category, '')) LIKE ?
      )
    ORDER BY {order_clause}
    """

    params.extend([search_term, search_term, search_term, search_term, search_term, search_term])
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def fetch_grouped_events(category="politics_plus", min_price=0.001, max_price=0.20, min_liquidity=0, search="", sort_by="liquidity"):
    conn = get_connection()
    cursor = conn.cursor()

    search_term = f"%{(search or '').lower()}%"
    params = [min_price, max_price, min_liquidity]

    category_clause = ""
    if category == "politics_plus":
        category_clause = "AND lower(m.category) IN ('politics', 'geopolitics')"
    elif category != "all":
        category_clause = "AND lower(m.category) = ?"
        params.append(category.lower())

    market_order_sql = {
        "liquidity": "m.liquidity DESC, m.volume_24h DESC, m.last_updated DESC",
        "volume": "m.volume_24h DESC, m.liquidity DESC, m.last_updated DESC",
        "price_asc": "m.yes_price ASC, m.liquidity DESC, m.last_updated DESC",
        "price_desc": "m.yes_price DESC, m.liquidity DESC, m.last_updated DESC",
        "newest": "m.last_updated DESC, m.liquidity DESC, m.volume_24h DESC",
        "opportunity": "COALESCE(s.opportunity_score,0) DESC, m.liquidity DESC",
    }.get(sort_by, "m.liquidity DESC, m.volume_24h DESC, m.last_updated DESC")

    query = f"""
    SELECT
        e.id AS event_id,
        e.title AS event_title,
        e.slug AS event_slug,
        e.tags AS event_tags,
        m.id AS market_id,
        m.title AS market_title,
        m.slug AS market_slug,
        m.category,
        m.yes_price,
        m.no_price,
        m.spread,
        m.liquidity,
        m.volume_24h,
        m.end_date,
        m.resolution_text,
        m.last_updated,
        s.opportunity_score,
        s.news_velocity
    FROM markets m
    LEFT JOIN events e ON m.event_id = e.id
    LEFT JOIN market_scores s ON s.market_id = m.id
    WHERE m.yes_price >= ?
      AND m.yes_price <= ?
      AND m.liquidity >= ?
      {category_clause}
      AND (
        lower(m.title) LIKE ?
        OR lower(m.slug) LIKE ?
        OR lower(COALESCE(m.resolution_text, '')) LIKE ?
        OR lower(COALESCE(e.title, '')) LIKE ?
        OR lower(COALESCE(e.tags, '')) LIKE ?
        OR lower(COALESCE(m.category, '')) LIKE ?
      )
    ORDER BY {market_order_sql}
    """

    params.extend([search_term, search_term, search_term, search_term, search_term, search_term])
    cursor.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()

    grouped = {}

    for row in rows:
        fallback_group_key = row["event_slug"] or f"market-only::{row['market_id']}"
        group_key = row["event_id"] or fallback_group_key

        if group_key not in grouped:
            grouped[group_key] = {
                "event_id": group_key,
                "event_title": row["event_title"] or row["market_title"],
                "event_slug": row["event_slug"] or row["market_slug"],
                "event_tags": row["event_tags"],
                "category": row["category"],
                "market_count": 0,
                "total_liquidity": 0.0,
                "total_volume_24h": 0.0,
                "min_yes_price": None,
                "max_yes_price": None,
                "max_opportunity": 0.0,
                "markets": [],
            }

        event_obj = grouped[group_key]
        yes_price = row["yes_price"] if row["yes_price"] is not None else 0.0
        liquidity = row["liquidity"] if row["liquidity"] is not None else 0.0
        volume_24h = row["volume_24h"] if row["volume_24h"] is not None else 0.0

        event_obj["market_count"] += 1
        event_obj["total_liquidity"] += liquidity
        event_obj["total_volume_24h"] += volume_24h
        event_obj["min_yes_price"] = yes_price if event_obj["min_yes_price"] is None else min(event_obj["min_yes_price"], yes_price)
        event_obj["max_yes_price"] = yes_price if event_obj["max_yes_price"] is None else max(event_obj["max_yes_price"], yes_price)
        _op = row["opportunity_score"] or 0.0
        if _op > event_obj["max_opportunity"]:
            event_obj["max_opportunity"] = _op

        event_obj["markets"].append({
            "id": row["market_id"],
            "event_id": row["event_id"] or group_key,
            "title": row["market_title"],
            "slug": row["market_slug"],
            "category": row["category"],
            "yes_price": row["yes_price"],
            "no_price": row["no_price"],
            "spread": row["spread"],
            "liquidity": row["liquidity"],
            "volume_24h": row["volume_24h"],
            "end_date": row["end_date"],
            "resolution_text": row["resolution_text"],
            "last_updated": row["last_updated"],
            "event_slug": row["event_slug"] or row["market_slug"],
            "event_title": row["event_title"] or row["market_title"],
            "event_tags": row["event_tags"],
            "opportunity_score": row["opportunity_score"],
            "news_velocity": row["news_velocity"],
        })

    grouped_list = list(grouped.values())

    if sort_by == "opportunity":
        grouped_list.sort(key=lambda x: x.get("max_opportunity", 0.0), reverse=True)
    elif sort_by == "volume":
        grouped_list.sort(key=lambda x: x["total_volume_24h"], reverse=True)
    elif sort_by == "price_asc":
        grouped_list.sort(key=lambda x: x["min_yes_price"] if x["min_yes_price"] is not None else 999)
    elif sort_by == "price_desc":
        grouped_list.sort(key=lambda x: x["max_yes_price"] if x["max_yes_price"] is not None else -1, reverse=True)
    elif sort_by == "newest":
        grouped_list.sort(
            key=lambda x: max((m["last_updated"] or "") for m in x["markets"]) if x["markets"] else "",
            reverse=True
        )
    else:
        grouped_list.sort(key=lambda x: x["total_liquidity"], reverse=True)

    return grouped_list


def fetch_all_headlines():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, source_name, source_tier, title, url, published_at, sentiment, summary
    FROM headlines
    ORDER BY published_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def fetch_headlines_for_market(market_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT h.id, h.source_name, h.source_tier, h.title, h.url, h.published_at, h.sentiment, h.summary,
           mh.relevance_score, mh.matched_by
    FROM market_headlines mh
    JOIN headlines h ON mh.headline_id = h.id
    WHERE mh.market_id = ?
    ORDER BY h.published_at DESC
    """, (market_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def fetch_score_for_market(market_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT market_id, price_dislocation, news_velocity, sentiment_shift, source_quality,
           time_decay, resolution_risk, liquidity_score, opportunity_score, updated_at
    FROM market_scores
    WHERE market_id = ?
    ORDER BY updated_at DESC
    LIMIT 1
    """, (market_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def fetch_alerts_for_market(market_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    SELECT id, market_id, alert_type, alert_text, severity, created_at, is_active
    FROM alerts
    WHERE market_id = ? AND is_active = 1
    ORDER BY created_at DESC
    """, (market_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def normalize_float(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def infer_category(market, event):
    text_parts = [
        str(market.get("question", "")),
        str(market.get("title", "")),
        str(market.get("description", "")),
        str(event.get("title", "")),
        str(event.get("slug", "")),
    ]

    tags = event.get("tags", [])
    if isinstance(tags, list):
        for tag in tags:
            if isinstance(tag, dict):
                text_parts.append(str(tag.get("label", "")))
                text_parts.append(str(tag.get("slug", "")))
            else:
                text_parts.append(str(tag))

    haystack = " ".join(text_parts).lower()
    politics_keywords = [
        "election", "president", "prime minister", "congress", "senate", "house",
        "government", "white house", "supreme court", "court", "minister",
        "parliament", "campaign", "vote", "voting", "ballot", "trump", "biden",
        "netanyahu", "iran", "israel", "china", "taiwan", "russia", "ukraine",
        "palestine", "gaza", "cuba", "sanctions", "ceasefire", "war", "peace deal",
        "diplomatic", "tariff", "nato", "military"
    ]

    for keyword in politics_keywords:
        if keyword in haystack:
            return "politics"

    return "other"


def upsert_event(event):
    if not event or not event.get("id"):
        return

    conn = get_connection()
    cursor = conn.cursor()

    event_id = str(event.get("id"))
    title = event.get("title") or event.get("ticker") or "Untitled Event"
    slug = event.get("slug")

    tags = ""
    raw_tags = event.get("tags", [])
    if isinstance(raw_tags, list):
        tag_parts = []
        for tag in raw_tags:
            if isinstance(tag, dict):
                tag_parts.append(tag.get("label", "") or tag.get("slug", ""))
            else:
                tag_parts.append(str(tag))
        tags = ",".join([t for t in tag_parts if t])

    start_date = event.get("startDate") or event.get("startDateIso")
    end_date = event.get("endDate") or event.get("endDateIso")
    last_updated = event.get("updatedAt") or event.get("createdAt")

    cursor.execute("""
    INSERT OR REPLACE INTO events (id, title, slug, tags, start_date, end_date, last_updated)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (event_id, title, slug, tags, start_date, end_date, last_updated))

    conn.commit()
    conn.close()


def upsert_market(market, event_id=None, event=None):
    if not market or not market.get("id"):
        return

    if event is None:
        event = {}

    inferred_event_id = event_id or market.get("eventId") or market.get("event_id")
    if not inferred_event_id:
        related_events = market.get("events") or []
        if related_events and isinstance(related_events, list):
            first_event = related_events[0]
            inferred_event_id = first_event.get("id")
            if first_event.get("id"):
                upsert_event(first_event)
                event = first_event

    conn = get_connection()
    cursor = conn.cursor()

    market_id = str(market.get("id"))
    title = market.get("question") or market.get("title") or "Untitled Market"
    slug = market.get("slug")
    category = infer_category(market, event)

    yes_price = normalize_float(market.get("lastTradePrice"), default=None)
    if yes_price is None:
        outcome_prices = market.get("outcomePrices")
        if isinstance(outcome_prices, str):
            try:
                import json
                parsed = json.loads(outcome_prices)
                if isinstance(parsed, list) and parsed:
                    yes_price = normalize_float(parsed[0], default=0.0)
            except Exception:
                yes_price = 0.0
        elif isinstance(outcome_prices, list) and outcome_prices:
            yes_price = normalize_float(outcome_prices[0], default=0.0)
        else:
            yes_price = normalize_float(market.get("bestBid"), default=0.0)

    no_price = 1.0 - yes_price if yes_price is not None else 0.0

    best_bid = normalize_float(market.get("bestBid"), default=yes_price or 0.0)
    best_ask = normalize_float(market.get("bestAsk"), default=yes_price or 0.0)
    spread = abs(best_ask - best_bid)

    liquidity = normalize_float(
        market.get("liquidityNum"),
        default=normalize_float(market.get("liquidityClob"), default=normalize_float(market.get("liquidity"), default=0.0))
    )
    volume_24h = normalize_float(
        market.get("volume24hr"),
        default=normalize_float(market.get("volume24hrClob"), default=0.0)
    )
    end_date = market.get("endDate") or market.get("endDateIso")
    resolution_text = market.get("description") or market.get("resolutionSource")
    last_updated = market.get("updatedAt") or market.get("createdAt")

    cursor.execute("""
    INSERT OR REPLACE INTO markets (
        id, event_id, title, slug, category, yes_price, no_price, spread,
        liquidity, volume_24h, end_date, resolution_text, last_updated
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        market_id,
        str(inferred_event_id) if inferred_event_id else None,
        title,
        slug,
        category,
        yes_price or 0.0,
        no_price,
        spread,
        liquidity,
        volume_24h,
        end_date,
        resolution_text,
        last_updated
    ))

    conn.commit()
    conn.close()


# ===========================================================================
#  NEWS ENGINE — write helpers (headlines / links / scores / alerts)
#  Pipeline support: headlines -> matching -> scoring -> alerts.
# ===========================================================================
import hashlib


def _now_iso():
    return datetime.datetime.utcnow().isoformat()


def upsert_headline(source_name, source_tier, title, url, published_at, sentiment=0.0, summary=""):
    """Insert a headline if it is new (keyed by a hash of url + title). Returns its id."""
    key = (url or "") + "|" + (title or "")
    h = hashlib.sha1(key.encode("utf-8", "replace")).hexdigest()
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM headlines WHERE raw_text_hash = ?", (h,))
    row = cursor.fetchone()
    if row:
        hid = row["id"]
    else:
        cursor.execute(
            """INSERT INTO headlines
               (source_name, source_tier, title, url, published_at, sentiment, summary, raw_text_hash)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (source_name, int(source_tier or 3), title, url, published_at,
             float(sentiment or 0.0), summary, h),
        )
        hid = cursor.lastrowid
    conn.commit()
    conn.close()
    return hid


def fetch_markets_for_scoring(max_price=0.30, limit=600):
    """Candidate markets for scoring (cheap / mid-priced, excluding the demo market)."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT m.id, m.title, m.category, m.yes_price, m.no_price, m.spread, m.liquidity,
                  m.volume_24h, m.end_date, m.resolution_text,
                  e.title AS event_title, e.tags AS event_tags
           FROM markets m
           LEFT JOIN events e ON m.event_id = e.id
           WHERE m.id NOT LIKE 'market_demo_%'
             AND m.yes_price IS NOT NULL AND m.yes_price >= 0 AND m.yes_price <= ?
           ORDER BY m.liquidity DESC
           LIMIT ?""",
        (max_price, limit),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def recent_headlines(limit=3000):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT id, source_name, source_tier, title, url, published_at, sentiment, summary
           FROM headlines ORDER BY id DESC LIMIT ?""",
        (limit,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def replace_market_headlines(market_id, links):
    """links: list of (headline_id, relevance_score, matched_by). Replaces the market's headline links."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM market_headlines WHERE market_id = ?", (market_id,))
    for hid, rel, mb in links:
        cursor.execute(
            """INSERT INTO market_headlines (market_id, headline_id, relevance_score, matched_by)
               VALUES (?, ?, ?, ?)""",
            (market_id, hid, float(rel), mb),
        )
    conn.commit()
    conn.close()


def replace_market_score(market_id, f):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM market_scores WHERE market_id = ?", (market_id,))
    cursor.execute(
        """INSERT INTO market_scores
           (market_id, price_dislocation, news_velocity, sentiment_shift, source_quality,
            time_decay, resolution_risk, liquidity_score, opportunity_score, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (market_id, f.get("price_dislocation", 0.0), f.get("news_velocity", 0.0),
         f.get("sentiment_shift", 0.0), f.get("source_quality", 0.0), f.get("time_decay", 0.0),
         f.get("resolution_risk", 0.0), f.get("liquidity_score", 0.0),
         f.get("opportunity_score", 0.0), _now_iso()),
    )
    conn.commit()
    conn.close()


def set_alerts_for_market(market_id, alerts):
    """alerts: list of dict(alert_type, alert_text, severity). Deactivates old alerts, inserts the new ones as active."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE alerts SET is_active = 0 WHERE market_id = ?", (market_id,))
    for a in alerts:
        cursor.execute(
            """INSERT INTO alerts (market_id, alert_type, alert_text, severity, created_at, is_active)
               VALUES (?, ?, ?, ?, ?, 1)""",
            (market_id, a.get("alert_type", "signal"), a.get("alert_text", ""),
             a.get("severity", "info"), _now_iso()),
        )
    conn.commit()
    conn.close()


def fetch_top_opportunities(limit=50, min_score=1.0):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT m.id, m.title, m.category, m.yes_price, m.liquidity, m.end_date,
                  e.slug AS event_slug,
                  s.opportunity_score, s.news_velocity, s.price_dislocation,
                  s.source_quality, s.sentiment_shift, s.updated_at
           FROM market_scores s
           JOIN markets m ON m.id = s.market_id
           LEFT JOIN events e ON e.id = m.event_id
           WHERE s.opportunity_score >= ?
           ORDER BY s.opportunity_score DESC
           LIMIT ?""",
        (min_score, limit),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def fetch_all_active_alerts(limit=80):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT a.id, a.market_id, a.alert_type, a.alert_text, a.severity, a.created_at,
                  m.title AS market_title, m.yes_price, e.slug AS event_slug
           FROM alerts a
           JOIN markets m ON m.id = a.market_id
           LEFT JOIN events e ON e.id = m.event_id
           WHERE a.is_active = 1
           ORDER BY CASE a.severity WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
                    a.created_at DESC
           LIMIT ?""",
        (limit,),
    )
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def set_market_category(market_id, category):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE markets SET category = ? WHERE id = ?", (category, market_id))
    conn.commit()
    conn.close()


def all_markets_brief():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """SELECT m.id, m.title, m.resolution_text, m.category, e.title AS event_title, e.tags AS event_tags
           FROM markets m LEFT JOIN events e ON e.id = m.event_id
           WHERE m.id NOT LIKE 'market_demo_%'""")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


def clear_news_data():
    conn = get_connection()
    cursor = conn.cursor()
    for t in ("market_headlines", "market_scores", "alerts", "headlines"):
        cursor.execute(f"DELETE FROM {t}")
    conn.commit()
    conn.close()