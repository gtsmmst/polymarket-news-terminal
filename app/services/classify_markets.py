"""
classify_markets.py - refines the market CATEGORY used by the dashboard filter.

db.infer_category() assigns a coarse politics / other label at ingest time. This
module refines it to geopolitics / politics / macro / crypto / sports / other so
that the "Politics + Geopolitics" filter and the sort options are meaningful and
macro / crypto markets can be separated. Run periodically by the scheduler.
"""
from app.db import all_markets_brief, set_market_category

GEO = [
    "iran", "israel", "ukraine", "russia", "crimea", "gaza", "hamas", "hezbollah",
    "hormuz", "taiwan", "china", "north korea", "ceasefire", "war", "invasion",
    "nato", "missile", "strike", "nuclear", "sanctions", "venezuela", "cuba",
    "syria", "lebanon", "houthi", "airstrike", "annex", "occupation", "yemen",
]
POL = [
    "election", "president", "nominee", "prime minister", "congress", "senate",
    "parliament", "governor", "mayor", "referendum", "impeachment", "vote",
    "ballot", "campaign", "cabinet", "coalition", "resign", "supreme court",
]
MACRO = [
    "fed", "federal reserve", "interest rate", "rate cut", "inflation", "cpi",
    "gdp", "recession", "unemployment", "tariff", "oil", "crude", "s&p", "nasdaq",
    "treasury", "ecb", "jobs report", "debt ceiling",
]
CRYPTO = ["bitcoin", "btc", "ethereum", "eth", "solana", "crypto", "stablecoin", "etf"]
SPORTS = [
    "vs.", " vs ", "world cup", "nba", "nfl", "mlb", "nhl", "premier league",
    "champions league", "wimbledon", "open", "match", "playoff", "super bowl",
    "championship", "grand prix",
]


def _classify(text):
    t = (text or "").lower()
    def hit(words):
        return any(w in t for w in words)
    # order matters: geo > politics > macro > crypto > sports
    if hit(GEO):
        return "geopolitics"
    if hit(POL):
        return "politics"
    if hit(MACRO):
        return "macro"
    if hit(CRYPTO):
        return "crypto"
    if hit(SPORTS):
        return "sports"
    return "other"


def refine_categories():
    """Re-label every market. Returns a per-category counter."""
    rows = all_markets_brief()
    counts = {}
    for m in rows:
        text = " ".join([
            str(m.get("title", "")),
            str(m.get("event_title", "") or ""),
            str(m.get("resolution_text", "") or ""),
            str(m.get("event_tags", "") or ""),
        ])
        cat = _classify(text)
        set_market_category(m["id"], cat)
        counts[cat] = counts.get(cat, 0) + 1
    return counts
