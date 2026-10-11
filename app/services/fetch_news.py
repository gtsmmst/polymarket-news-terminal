"""
fetch_news.py - free news feed: GDELT DOC 2.0 API + public RSS.

No paid wire feeds are required:
  * GDELT DOC 2.0 (https://api.gdeltproject.org) - global news, no API key,
    refreshed roughly every 15 minutes, searchable by query (Iran, Crimea, election ...).
  * RSS from large outlets (Al Jazeera / BBC / Guardian / Politico / NBC) - plain XML.

Headlines are stored in the database (deduplicated by a hash of url + title) with
the source name, a source "tier" and a cheap lexicon-based sentiment. GDELT queries
are built from the named entities found in the tracked markets, plus a fixed set of
standing topics.
"""
import datetime
import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from app.db import upsert_headline

UA = {"User-Agent": "Mozilla/5.0 (polymarket-news-terminal)"}
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Source tier: 1 = top wires / quality press, 2 = large outlets, 3 = everything else.
TIER = {
    "reuters.com": 1, "apnews.com": 1, "bloomberg.com": 1, "ft.com": 1, "wsj.com": 1,
    "economist.com": 1, "bbc.co.uk": 1, "bbc.com": 1, "nytimes.com": 1,
    "washingtonpost.com": 1, "aljazeera.com": 2, "theguardian.com": 2, "politico.com": 2,
    "axios.com": 2, "cnbc.com": 2, "cnn.com": 2, "kyivindependent.com": 2, "nbcnews.com": 2,
    "foxnews.com": 3, "tass.com": 3, "rt.com": 3,
}

# Standing topics that are always queried (geopolitics / politics / macro focus).
STANDING_TOPICS = [
    "Iran nuclear", "Iran Israel", "Strait of Hormuz", "Ukraine Crimea",
    "Russia Ukraine ceasefire", "Gaza ceasefire", "Venezuela Maduro", "Taiwan China",
    "North Korea", "US election 2028", "Federal Reserve interest rate", "NATO",
    "oil price OPEC", "Trump policy",
]

RSS_FEEDS = [
    ("Reuters World", "https://www.reutersagency.com/feed/?best-topics=political-general&post_type=best"),
    ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Guardian World", "https://www.theguardian.com/world/rss"),
    ("Politico", "https://www.politico.com/rss/politicopicks.xml"),
    ("NBC World", "https://feeds.nbcnews.com/nbcnews/public/world"),
]

POS = set("win wins agree agrees deal deals ceasefire peace breakthrough approve approved "
          "victory rises gains surge advance recover recovers signs resolves easing".split())
NEG = set("collapse fails reject war strike strikes attack killed crisis sanctions invasion "
          "escalate escalates plunge dies threat threats blockade missile drone".split())


def tier_for(domain):
    d = (domain or "").lower().replace("www.", "")
    return TIER.get(d, 3)


def cheap_sentiment(title):
    """Lexicon sentiment: (# positive words) - (# negative words) in the title."""
    w = set(re.findall(r"[a-z]+", (title or "").lower()))
    return float(len(w & POS) - len(w & NEG))


def _http_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _gdelt_date(s):
    try:
        return datetime.datetime.strptime(s, "%Y%m%dT%H%M%SZ").isoformat()
    except Exception:
        return datetime.datetime.utcnow().isoformat()


def fetch_gdelt(query, maxrecords=35, timespan="3d"):
    """Query the GDELT DOC API in ArtList mode. Returns [] on any error."""
    q = urllib.parse.urlencode({
        "query": query, "mode": "ArtList", "format": "json",
        "maxrecords": maxrecords, "timespan": timespan, "sort": "DateDesc",
    })
    try:
        data = _http_json(f"{GDELT_URL}?{q}")
    except Exception:
        return []
    out = []
    for a in (data.get("articles") or []):
        title = (a.get("title") or "").strip()
        url = a.get("url")
        if not title or not url:
            continue
        dom = a.get("domain") or ""
        out.append({
            "source": dom or "gdelt", "tier": tier_for(dom), "title": title,
            "url": url, "published": _gdelt_date(a.get("seendate")),
        })
    return out


def fetch_rss(name, url, limit=40):
    """Fetch an RSS 2.0 or Atom feed. Returns [] on any error."""
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
        root = ET.fromstring(raw)
    except Exception:
        return []
    items = []
    for it in root.iter():
        tag = it.tag.lower()
        if tag.endswith("item") or tag.endswith("entry"):
            title = link = pub = None
            for ch in it:
                t = ch.tag.lower()
                if t.endswith("title"):
                    title = (ch.text or "").strip()
                elif t.endswith("link"):
                    link = (ch.get("href") or ch.text or "").strip()
                elif t.endswith("pubdate") or t.endswith("published") or t.endswith("updated"):
                    pub = (ch.text or "").strip()
            if title and link:
                items.append({
                    "source": name, "tier": 2, "title": title, "url": link,
                    "published": pub or datetime.datetime.utcnow().isoformat(),
                })
            if len(items) >= limit:
                break
    return items


def fetch_all_news(market_queries=None, per_query=30):
    """
    Pull GDELT (standing topics + market-derived queries) and RSS, store everything
    in the database. Returns a small counter dict.
    """
    queries = list(STANDING_TOPICS)
    for q in (market_queries or []):
        if q and q not in queries:
            queries.append(q)

    seen = set()
    saved = 0
    gdelt_ok = 0

    for q in queries:
        arts = fetch_gdelt(q, maxrecords=per_query)
        if arts:
            gdelt_ok += 1
        for h in arts:
            if h["url"] in seen:
                continue
            seen.add(h["url"])
            upsert_headline(h["source"], h["tier"], h["title"], h["url"], h["published"],
                            sentiment=cheap_sentiment(h["title"]))
            saved += 1
        time.sleep(0.25)  # be polite to GDELT

    for name, url in RSS_FEEDS:
        for h in fetch_rss(name, url):
            if h["url"] in seen:
                continue
            seen.add(h["url"])
            upsert_headline(h["source"], h["tier"], h["title"], h["url"], h["published"],
                            sentiment=cheap_sentiment(h["title"]))
            saved += 1

    return {"queries": len(queries), "gdelt_responding": gdelt_ok, "headlines_saved": saved}


if __name__ == "__main__":
    print(fetch_all_news())
