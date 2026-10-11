"""
extract_entities.py - lightweight entity / keyword extraction (no heavy NLP).

Idea: matching a headline to a market needs shared ENTITIES (countries, leaders,
organisations, topics), not shared function words. So we pull multi-word proper
names, check them against a small gazetteer and add long content words. The
matcher then requires a NAMED overlap so that words like "before" / "win" do not
produce false positives.
"""
import re
from collections import Counter

COUNTRIES = {
    "iran", "israel", "ukraine", "russia", "china", "taiwan", "gaza", "palestine",
    "lebanon", "syria", "yemen", "venezuela", "cuba", "north korea", "south korea",
    "india", "pakistan", "france", "germany", "italy", "spain", "poland", "turkey",
    "saudi arabia", "qatar", "egypt", "iraq", "afghanistan", "japan", "mexico",
    "canada", "brazil", "argentina", "nigeria", "ethiopia", "sudan", "libya",
    "united states", "usa", "uk", "britain", "netherlands", "belgium", "greece",
    "hungary", "romania", "georgia", "armenia", "azerbaijan", "moldova", "serbia",
    "crimea", "donbas", "kursk", "kharkiv", "hormuz", "kerch",
}
LEADERS = {
    "trump", "biden", "harris", "vance", "putin", "zelensky", "zelenskyy", "netanyahu",
    "khamenei", "pezeshkian", "xi", "xi jinping", "modi", "macron", "scholz", "merz",
    "starmer", "erdogan", "orban", "lukashenko", "maduro", "milei", "lula",
    "sheinbaum", "meloni", "von der leyen", "powell", "lavrov", "rubio", "newsom",
    "desantis", "obama", "ramaswamy", "gabbard", "massie",
}
ORGS = {
    "nato", "opec", "imf", "fed", "federal reserve", "ecb", "un", "united nations",
    "eu", "european union", "hamas", "hezbollah", "houthi", "houthis", "wagner",
    "idf", "cia", "iaea", "brics", "g7", "g20", "supreme court", "congress", "senate",
}
TOPICS = {
    "ceasefire", "sanctions", "nuclear", "enrichment", "uranium", "missile", "drone",
    "offensive", "invasion", "blockade", "tariff", "inflation", "recession",
    "election", "referendum", "impeachment", "coup", "default", "shutdown", "strike",
    "annex", "occupation", "withdrawal", "mobilization", "summit", "airstrike",
    "escalation", "negotiation", "treaty", "embargo",
}
GAZETTEER = COUNTRIES | LEADERS | ORGS | TOPICS
MULTIWORD = sorted([g for g in GAZETTEER if " " in g], key=len, reverse=True)
SINGLE = {g for g in GAZETTEER if " " not in g}

STOP = {
    "will", "the", "and", "for", "with", "from", "this", "that", "before", "after",
    "your", "what", "when", "which", "their", "there", "have", "has", "does", "are",
    "win", "wins", "reach", "reaches", "yes", "vote", "votes", "than", "into", "over",
    "under", "between", "during", "about", "would", "could", "should", "first", "next",
    "year", "years", "month", "day", "days", "team", "game", "match", "odds",
    "predictions", "market", "markets", "polymarket", "presidential", "nominee",
}


def is_named(token):
    return token in GAZETTEER or " " in token


def keywords(text):
    """Set of keyword tokens extracted from the text."""
    text = text or ""
    low = text.lower()
    toks = set()
    for m in re.findall(r"\b([A-Z][a-zA-Z.&'-]+(?:\s+[A-Z][a-zA-Z.&'-]+){0,3})\b", text):
        ph = re.sub(r"\s+", " ", m).strip().lower()
        if len(ph) > 2 and ph not in STOP:
            toks.add(ph)
    for mw in MULTIWORD:
        if mw in low:
            toks.add(mw)
    words = set(re.findall(r"[a-zA-Z]{3,}", low))
    toks |= (words & SINGLE)
    for w in words:
        if len(w) >= 5 and w not in STOP:
            toks.add(w)
    return toks


def named_keywords(text):
    return {k for k in keywords(text) if is_named(k)}


def market_query_terms(markets, top=18):
    """GDELT search strings built from the most frequent NAMED entities across markets."""
    cnt = Counter()
    for m in markets:
        text = " ".join([
            str(m.get("title", "")),
            str(m.get("event_title", "") or ""),
            str(m.get("resolution_text", "") or ""),
            str(m.get("event_tags", "") or ""),
        ])
        for k in named_keywords(text):
            cnt[k] += 1
    terms = [w for w, _ in cnt.most_common(top * 2)]
    terms = sorted(terms, key=lambda w: (0 if (" " in w or w in COUNTRIES or w in LEADERS) else 1))
    return terms[:top]
