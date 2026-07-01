"""
sentiment.py — best-effort, HONEST headline sentiment (an optional lens).

WHY THIS IS DELIBERATELY CONSERVATIVE (do not "improve" by removing the guards):
    Free news feeds routinely return generic, non-ticker-specific headlines. A
    sentiment score computed from irrelevant news is noise masquerading as signal
    — the exact failure this whole tool exists to prevent. So this module:
      * pulls headlines AND the company name in one call,
      * keeps only headlines that actually mention the company (relevance gate),
      * scores them with a TRANSPARENT keyword lexicon (no black-box model),
      * returns `available=False` when it cannot get relevant headlines,
      * is clearly labelled a crude proxy, and contributes only as a WEAK lens.
    If a real sentiment feed or the Claude analyst is available, prefer those.
"""

from __future__ import annotations

from typing import Optional

_POS = {
    "beat", "beats", "upgrade", "upgraded", "surge", "surges", "jump", "jumps",
    "rally", "rallies", "record", "strong", "growth", "profit", "raises", "raised",
    "outperform", "wins", "win", "approval", "approved", "boost", "higher", "gains",
    "gain", "tops", "exceeds", "buyback", "dividend", "soar", "soars", "rebound",
    "bullish", "expansion", "wins", "guidance raised",
}
_NEG = {
    "miss", "misses", "downgrade", "downgraded", "plunge", "plunges", "drop",
    "drops", "fall", "falls", "cut", "cuts", "weak", "loss", "losses", "lawsuit",
    "probe", "recall", "warns", "warning", "slump", "lower", "declines", "decline",
    "halts", "halt", "bankruptcy", "fraud", "slashes", "slash", "bearish",
    "downturn", "layoffs", "guidance cut", "shortfall", "disappoints",
}

_URL = "https://query1.finance.yahoo.com/v1/finance/search"
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PreOpenBrief/1.0)"}


def _name_tokens(name: Optional[str]) -> set:
    """Significant lowercase words from a company name for relevance matching."""
    if not name:
        return set()
    stop = {"the", "inc", "inc.", "corp", "corp.", "ltd", "ltd.", "co", "co.",
            "company", "group", "plc", "sa", "ag", "&", "of", "and"}
    return {w.strip(".,") for w in name.lower().split() if w.strip(".,") not in stop and len(w) > 2}


def _score_titles(titles: list) -> tuple:
    pos = neg = 0
    for t in titles:
        words = set(t.lower().replace("-", " ").split())
        pos += len(words & _POS)
        neg += len(words & _NEG)
    total = pos + neg
    if total == 0:
        return 0.0, pos, neg
    return (pos - neg) / total, pos, neg


def headline_sentiment(ticker: str, *, max_headlines: int = 8, timeout: int = 12) -> dict:
    """Return a labelled sentiment proxy or available=False. Never fabricates."""
    out = {
        "_label": "CRUDE headline-keyword proxy — not real NLP; weak lens only",
        "available": False, "score": None, "label": "unavailable",
        "n_relevant": 0, "note": "",
    }
    try:
        import requests
        r = requests.get(_URL, params={"q": ticker, "newsCount": max_headlines,
                                       "quotesCount": 1}, headers=_HEADERS, timeout=timeout)
        r.raise_for_status()
        j = r.json()
        quotes = j.get("quotes") or []
        name = None
        for q in quotes:
            if q.get("symbol", "").upper() == ticker.upper():
                name = q.get("shortname") or q.get("longname")
                break
        if name is None and quotes:
            name = quotes[0].get("shortname") or quotes[0].get("longname")
        toks = _name_tokens(name)

        news = j.get("news") or []
        titles = [n.get("title", "") for n in news if n.get("title")]
        # RELEVANCE GATE: keep only headlines that mention the company.
        relevant = [t for t in titles
                    if toks and any(tok in t.lower() for tok in toks)]
        out["n_relevant"] = len(relevant)
        if not relevant:
            out["note"] = f"no ticker-relevant headlines (had {len(titles)} generic) — sentiment not used"
            return out

        score, pos, neg = _score_titles(relevant)
        out.update({
            "available": True, "score": round(score, 3),
            "label": ("positive" if score > 0.15 else "negative" if score < -0.15 else "neutral"),
            "pos_hits": pos, "neg_hits": neg,
            "note": f"{len(relevant)} relevant headlines ({name})",
        })
    except Exception as e:
        out["note"] = f"sentiment unavailable: {e}"
    return out


def sentiment_dir(sent: dict) -> int:
    """+1 / -1 / 0 direction from a sentiment dict, 0 when unavailable/neutral."""
    if not sent or not sent.get("available"):
        return 0
    s = sent.get("score", 0) or 0
    return 1 if s > 0.15 else -1 if s < -0.15 else 0
