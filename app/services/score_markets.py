"""
score_markets.py - the mispricing engine (core of the terminal).

For every cheap / mid-priced market it:
  1) matches recent headlines on NAMED entities (country / leader / org / topic),
  2) computes a multi-factor score:
       price_dislocation - cheap price + lots of fresh news = potentially underpriced,
       news_velocity     - volume and freshness of relevant headlines,
       source_quality    - best source tier among matches (wires > other),
       sentiment_shift   - recency-weighted net sentiment of matched headlines,
       time_decay        - whether the resolution horizon is convenient,
       resolution_risk   - distant horizon / lottery price / complex rules / thin book,
       liquidity_score   - whether a position of reasonable size fits,
       opportunity_score - weighted total, clamped to 0..100,
  3) writes headline links, the score row and ALERTS to the database.

Optional: if ANTHROPIC_API_KEY is set, an LLM estimates fair probability and
importance for the top candidates and the result is attached as an extra alert.

Public, side-effect-free helpers (safe to unit-test without a database):
  compute_factors(market, matched) -> dict of factor scores
  build_alerts(market, factors)    -> list of alert dicts
"""
import datetime
import json
import math
import os
import re
import urllib.request
from email.utils import parsedate_to_datetime

from app import db
from app.config import AI_MODEL
from app.services import extract_entities as ee

AI_TOP_N = 10
ANTHROPIC_MESSAGES_URL = "https://api.anthropic.com/v1/messages"

# Weights of the final opportunity score (resolution_risk is a penalty).
WEIGHTS = {
    "price_dislocation": 0.34,
    "news_velocity": 0.24,
    "source_quality": 0.14,
    "liquidity_score": 0.14,
    "time_decay": 0.10,
    "resolution_risk": -0.22,
}


# ----------------------------------------------------------------- time helpers
def _parse_dt(s):
    """Parse ISO-8601 or RFC-2822 timestamps into a naive UTC datetime."""
    if not s:
        return None
    dt = None
    try:
        dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        try:
            dt = parsedate_to_datetime(s)
        except Exception:
            return None
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(datetime.timezone.utc)
    return dt.replace(tzinfo=None)


def _recency_weight(s):
    dt = _parse_dt(s)
    if not dt:
        return 0.4
    hrs = (datetime.datetime.utcnow() - dt).total_seconds() / 3600.0
    if hrs < 0:
        hrs = 0
    return max(0.05, math.exp(-hrs / 48.0))   # half-life of roughly 33 hours


def _days_to(s):
    dt = _parse_dt(s)
    if not dt:
        return None
    return (dt - datetime.datetime.utcnow()).days


def _tier_to_quality(tier):
    return {1: 100, 2: 66, 3: 33}.get(int(tier or 3), 33)


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


# ----------------------------------------------------------------- scoring core
def compute_factors(m, matched):
    """
    Compute the factor scores for one market.

    m:       market dict with yes_price, liquidity, end_date, resolution_text
    matched: list of (relevance, source_tier, sentiment, recency_weight) tuples,
             one per headline matched to this market.
    Returns a dict with all factor scores plus opportunity_score (0..100).
    """
    yes = float(m.get("yes_price") or 0.0)
    liq = float(m.get("liquidity") or 0.0)
    days = _days_to(m.get("end_date"))

    velocity_raw = sum(rw for (_rel, _t, _s, rw) in matched)
    news_velocity = round(_clamp(velocity_raw * 15.0), 1)

    if matched:
        best_tier = min(t for (_rel, t, _s, _rw) in matched)
        source_quality = float(_tier_to_quality(best_tier))
        wsum = sum(rw for (_rel, _t, _s, rw) in matched) or 1.0
        sentiment_shift = round(sum(s * rw for (_rel, _t, s, rw) in matched) / wsum, 2)
    else:
        source_quality = 0.0
        sentiment_shift = 0.0

    price_dislocation = round(_clamp(news_velocity * (1.0 - yes)), 1)
    liquidity_score = round(_clamp(liq / 3000.0 * 100.0), 1)

    if days is None:
        time_decay = 50.0
    elif days < 2:
        time_decay = 30.0
    elif days <= 90:
        time_decay = 100.0
    elif days <= 180:
        time_decay = 70.0
    elif days <= 365:
        time_decay = 45.0
    else:
        time_decay = 25.0

    risk = 0.0
    if yes < 0.02:
        risk += 40
    if days is not None and days > 365:
        risk += 30
    if len(str(m.get("resolution_text") or "")) > 400:
        risk += 15
    if liq < 1000:
        risk += 15
    resolution_risk = round(_clamp(risk), 1)

    factors = {
        "price_dislocation": price_dislocation,
        "news_velocity": news_velocity,
        "sentiment_shift": sentiment_shift,
        "source_quality": source_quality,
        "time_decay": time_decay,
        "resolution_risk": resolution_risk,
        "liquidity_score": liquidity_score,
    }
    opportunity = sum(WEIGHTS[k] * factors[k] for k in WEIGHTS)
    factors["opportunity_score"] = round(_clamp(opportunity), 1)
    return factors


def build_alerts(m, f):
    """Rule-based alerts derived from a market and its factor scores."""
    yes = float(m.get("yes_price") or 0.0)
    yc = round(yes * 100, 1)
    alerts = []
    if f["news_velocity"] >= 40 and yes <= 0.15:
        alerts.append({"alert_type": "news_spike", "severity": "high",
                       "alert_text": f"News spike on a cheap market (YES {yc}c) - check whether the outcome is underpriced."})
    elif f["news_velocity"] >= 22:
        alerts.append({"alert_type": "news_active", "severity": "medium",
                       "alert_text": "Active news flow around this event - worth a closer look."})
    if f["source_quality"] >= 90 and f["news_velocity"] >= 15:
        alerts.append({"alert_type": "tier1", "severity": "medium",
                       "alert_text": "Covered by tier-1 sources - the signal is credible."})
    if f["resolution_risk"] >= 70:
        alerts.append({"alert_type": "risk", "severity": "low",
                       "alert_text": "High resolution risk (distant horizon / lottery price) - size small."})
    return alerts


# ----------------------------------------------------------------- optional AI
def _anthropic(prompt, key, max_tokens=1000):
    body = json.dumps({
        "model": AI_MODEL, "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    req = urllib.request.Request(
        ANTHROPIC_MESSAGES_URL, data=body,
        headers={"content-type": "application/json", "x-api-key": key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=45) as r:
        d = json.loads(r.read().decode("utf-8", "replace"))
    return "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")


def ai_assess(items):
    """
    items: list of (market_dict, [headline_titles]).
    Returns {market_id: {"fair": int, "importance": int, "note": str}},
    or {} when ANTHROPIC_API_KEY is not set or the call fails.
    """
    key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    if not key or not items:
        return {}
    lines = []
    for m, heads in items:
        yc = round(float(m.get("yes_price") or 0) * 100, 1)
        hs = " | ".join(heads[:3]) if heads else "(no fresh headlines)"
        lines.append(f'- id={m["id"]} | "{m.get("title","")}" | market YES={yc}c | ends {m.get("end_date")}\n  headlines: {hs}')
    prompt = (
        "You are a prediction-market analyst. For each market below, using the market price and the "
        "headlines as a hint, estimate your fair probability (0-100, integer) that it resolves YES, an "
        "importance score (0-100, how news-driven/actionable it is right now), and a <=12-word note. "
        "Reply ONLY with a JSON array of objects with keys id, fair, importance, note. No prose.\n\n"
        + "\n".join(lines)
    )
    try:
        txt = _anthropic(prompt, key)
        mm = re.search(r"\[.*\]", txt, re.S)
        arr = json.loads(mm.group(0) if mm else txt)
        out = {}
        for o in arr:
            if o.get("id"):
                out[str(o["id"])] = {
                    "fair": int(o.get("fair", 0)),
                    "importance": int(o.get("importance", 0)),
                    "note": str(o.get("note", ""))[:120],
                }
        return out
    except Exception:
        return {}


# ----------------------------------------------------------------- run
def run(max_price=0.30, use_ai=True):
    """Score every candidate market against recent headlines and persist the results."""
    markets = db.fetch_markets_for_scoring(max_price=max_price, limit=500)
    heads = db.recent_headlines(limit=3000)

    H = []
    for h in heads:
        kw = ee.keywords(h.get("title"))
        H.append((h, kw, _recency_weight(h.get("published_at")),
                  int(h.get("source_tier") or 3), float(h.get("sentiment") or 0)))

    results = []
    for m in markets:
        mtext = " ".join([str(m.get("title", "")), str(m.get("event_title") or ""),
                          str(m.get("resolution_text") or ""), str(m.get("event_tags") or "")])
        mkw = ee.keywords(mtext)
        named = {k for k in mkw if ee.is_named(k)}
        if not mkw:
            f = compute_factors(m, [])
            results.append((m, f, [], build_alerts(m, f), []))
            continue

        links = []
        matched = []
        head_titles = []
        for (h, hkw, rw, tier, sent) in H:
            ov = mkw & hkw
            if not ov:
                continue
            named_ov = ov & named
            if not named_ov and len(ov) < 2:
                continue   # require a named overlap or at least two meaningful words
            rel = round(min(1.0, 0.3 * len(ov) + (0.4 if named_ov else 0.0)) * rw, 3)
            if rel <= 0:
                continue
            links.append((h["id"], rel, ",".join(sorted(ov)[:4])))
            matched.append((rel, tier, sent, rw))
            head_titles.append((rel, h.get("title", "")))

        f = compute_factors(m, matched)
        links.sort(key=lambda x: -x[1])
        head_titles.sort(key=lambda x: -x[0])
        results.append((m, f, links[:30], build_alerts(m, f), [t for _r, t in head_titles[:5]]))

    # persist headline links + scores
    for (m, f, links, _alerts, _heads) in results:
        db.replace_market_headlines(m["id"], links)
        db.replace_market_score(m["id"], f)

    # optional LLM pass over the top candidates
    ai = {}
    if use_ai:
        top = sorted([r for r in results if r[1]["news_velocity"] > 0],
                     key=lambda r: r[1]["opportunity_score"], reverse=True)[:AI_TOP_N]
        ai = ai_assess([(r[0], r[4]) for r in top])

    # persist alerts (AI alert first when present)
    scored = 0
    for (m, f, _links, alerts, _heads) in results:
        a = list(alerts)
        info = ai.get(str(m["id"]))
        if info:
            yc = round(float(m.get("yes_price") or 0) * 100, 1)
            edge = info["fair"] - yc
            sev = "high" if abs(edge) >= 8 else "medium"
            a.insert(0, {"alert_type": "ai", "severity": sev,
                         "alert_text": f"AI: fair ~{info['fair']}% vs market {yc}c (edge {edge:+.0f}), importance {info['importance']}/100. {info['note']}"})
        db.set_alerts_for_market(m["id"], a)
        scored += 1

    return {"markets_scored": scored, "headlines_considered": len(heads),
            "ai_assessed": len(ai)}


if __name__ == "__main__":
    print(run(use_ai=False))
