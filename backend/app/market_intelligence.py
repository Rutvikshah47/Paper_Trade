from __future__ import annotations

import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from .config import settings

IST = ZoneInfo("Asia/Kolkata")
NSE_HOME = "https://www.nseindia.com"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
SECTORS = [
    "Financials", "IT", "Pharma", "FMCG", "Auto", "Real Estate",
    "Aviation", "Oil & Gas", "Metals", "Chemicals", "Capital Goods",
    "Defence", "Telecom",
]

SENSITIVITY = {
    "Financials": {"us10y": -1.2, "fii": 1.0, "vix": -0.4, "nifty": 0.5},
    "IT": {"nasdaq": 1.0, "usdinr": 0.7, "us10y": 0.35, "fii": 0.3},
    "Pharma": {"usdinr": 0.6, "dxy": 0.25, "fii": 0.2},
    "FMCG": {"us10y": 0.4, "vix": 0.35, "fii": 0.25},
    "Auto": {"brent": -0.6, "us10y": 0.3, "usdinr": -0.25, "nifty": 0.25},
    "Real Estate": {"us10y": -0.9, "vix": -0.35},
    "Aviation": {"brent": -1.4, "usdinr": -0.45, "vix": -0.3},
    "Oil & Gas": {"brent": 0.7, "usdinr": -0.2},
    "Metals": {"shanghai": 0.55, "gold": 0.2, "nifty": 0.2},
    "Chemicals": {"brent": -0.7, "usdinr": -0.2},
    "Capital Goods": {"fii": 0.35, "nifty": 0.45, "us10y": -0.3},
    "Defence": {"fii": 0.1},
    "Telecom": {"us10y": -0.2, "nifty": 0.2},
}

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "market_mood": {
            "type": "string",
            "enum": ["Bullish", "Cautious Positive", "Neutral / Mixed", "Cautious Negative", "Bearish"]
        },
        "global_cues": {"type": "array", "maxItems": 12, "items": {"type": "object", "properties": {
            "name": {"type": "string"},
            "last": {"type": "number"},
            "prev": {"type": "number"},
            "pct": {"type": "number"}
        }, "required": ["name", "last", "prev", "pct"]}},
        "summary": {"type": "string"},
        "outlook": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        "drivers": {"type": "array", "maxItems": 8, "items": {"type": "object", "properties": {
            "direction": {"type": "string", "enum": ["positive", "negative", "neutral"]},
            "title": {"type": "string"},
            "explanation": {"type": "string"},
            "impact": {"type": "number", "minimum": -100, "maximum": 100},
        }, "required": ["direction", "title", "explanation", "impact"]}},
        "sector_impacts": {"type": "array", "maxItems": 13, "items": {"type": "object", "properties": {
            "sector": {"type": "string"},
            "direction": {"type": "string", "enum": ["positive", "negative", "mixed"]},
            "score": {"type": "number", "minimum": -100, "maximum": 100},
            "ai_adjustment": {"type": "number", "minimum": -20, "maximum": 20},
            "confidence": {"type": "number", "minimum": 0, "maximum": 100},
            "reason": {"type": "string"},
        }, "required": ["sector", "direction", "score", "ai_adjustment", "confidence", "reason"]}},
        "news_items": {"type": "array", "maxItems": 10, "items": {"type": "object", "properties": {
            "headline": {"type": "string"},
            "source": {"type": "string"},
            "impact": {"type": "string", "enum": ["high", "medium", "low"]},
            "sectors": {"type": "array", "items": {"type": "string"}, "maxItems": 6},
            "summary": {"type": "string"},
        }, "required": ["headline", "source", "impact", "sectors", "summary"]}},
        "watchlist": {"type": "array", "items": {"type": "string"}, "maxItems": 10},
        "events": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
        "scenarios": {"type": "array", "maxItems": 3, "items": {"type": "object", "properties": {
            "name": {"type": "string", "enum": ["Constructive", "Base case", "Cautious"]},
            "trigger": {"type": "string"},
            "read_through": {"type": "string"}
        }, "required": ["name", "trigger", "read_through"]}},
        "data_quality": {"type": "array", "items": {"type": "string"}, "maxItems": 8},
    },
    "required": ["market_mood", "global_cues", "summary", "outlook", "confidence", "drivers", "sector_impacts", "news_items", "watchlist", "events", "scenarios", "data_quality"],
}


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "*/*", "Referer": NSE_HOME + "/"})
    return s


def _nse_json(path: str):
    s = _session()
    s.get(NSE_HOME, timeout=15, verify=False)
    response = s.get(f"{NSE_HOME}/api/{path}", timeout=15, verify=False)
    response.raise_for_status()
    return response.json()


def _pct(item) -> float:
    return float(item.get("pct") or 0) if item else 0.0


def _signal(value: float, threshold: float, up_positive: bool = True) -> float:
    if not value or abs(value) < threshold:
        return 0.0
    strength = min(2.0, abs(value) / threshold)
    direction = 1 if value > 0 else -1
    if not up_positive:
        direction *= -1
    return direction * strength


def deterministic_analysis(data: dict) -> dict:
    g, i = data["global"], data["india"]
    factors = {
        "us10y": _signal(_pct(g.get("US 10Y")), 0.05, False),
        "dxy": _signal(_pct(g.get("DXY")), 0.4, False),
        "nasdaq": _signal(_pct(g.get("Nasdaq")), 0.5),
        "dow": _signal(_pct(g.get("Dow")), 0.5),
        "nikkei": _signal(_pct(g.get("Nikkei")), 0.5),
        "hangseng": _signal(_pct(g.get("Hang Seng")), 0.5),
        "shanghai": _signal(_pct(g.get("Shanghai")), 0.5),
        "brent": _signal(_pct(g.get("Brent")), 2.0, False),
        "gold": _signal(_pct(g.get("Gold")), 1.5),
        "usdinr": _signal(_pct(i.get("USD/INR")), 0.3, False),
        "vix": _signal(_pct(i.get("India VIX")), 5.0, False),
        "nifty": _signal(_pct(i.get("Nifty 50")), 0.7),
        "fii": 1.0 if (i.get("FII", {}).get("last") or 0) >= 500 else -1.0 if (i.get("FII", {}).get("last") or 0) <= -500 else 0.0,
    }
    weights = {"us10y":2,"dxy":1,"nasdaq":1.5,"dow":1,"nikkei":1,"hangseng":1,"shanghai":0.75,"brent":1.5,"gold":0.5,"usdinr":1,"vix":1,"nifty":1,"fii":1.5}
    total = sum(factors[k] * weights[k] for k in factors)
    denom = sum(weights.values()) or 1
    pressure = round(max(-100, min(100, total / denom * 50)), 1)

    sector_scores = {}
    for sector in SECTORS:
        raw = 0.0
        for factor, sensitivity in SENSITIVITY.get(sector, {}).items():
            raw += factors.get(factor, 0) * sensitivity * 25
        sector_scores[sector] = round(max(-100, min(100, raw)), 1)
    return {"pressure": pressure, "sector_scores": sector_scores, "factors": factors}


def _gemini(api_key: str, market: dict, baseline: dict, model: str):
    prompt = f"""
{NEWS_INSTRUCTION}

The current time is {datetime.now(IST).isoformat()}.

MARKET DATA (authoritative for numbers):
{json.dumps(market, indent=2)}

DETERMINISTIC BASELINE:
{json.dumps(baseline, indent=2)}

Use Google Search for fresh information from the last 24 hours and today's
latest available market sessions.

Return GLOBAL CUES for these instruments only when you can verify the latest
value and previous close/session: Nasdaq, Dow, S&P 500, Nikkei, Hang Seng,
Shanghai, Brent, Gold, DXY, US 10Y, USD/INR. Do not invent values. For US 10Y
return the yield level and previous-session yield.

Find material current NEWS affecting Indian equities. Cover India, US, Asia,
Europe, central banks, inflation/rates, crude/energy, currencies, geopolitics,
trade/tariffs, major Indian companies and sectors. Prefer authoritative sources
such as Reuters, Bloomberg, CNBC, Financial Times, WSJ, RBI, Federal Reserve,
ECB, BoJ, NSE/BSE, company filings and government releases.

Also assess Constructive, Base case and Cautious scenarios. Each scenario must
name an observable trigger and India-market read-through. Do not assign made-up
probabilities.

Return structured JSON only. Keep the supplied Indian numeric market data unchanged.
For each sector, start from its deterministic baseline score and use ai_adjustment
(-20 to +20) only for a clear fresh-news reason. Do not invent source URLs or
market numbers. Do not give personalized trade instructions.
"""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "response_mime_type": "application/json",
            "response_schema": REPORT_SCHEMA,
            "temperature": 0.2,
            "maxOutputTokens": 12000,
        },
    }
    response = None
    for attempt in range(2):
        response = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
            headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=90,
        )
        if response.ok:
            break
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == 1:
            raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:1200]}")
        time.sleep(2)

    body = response.json()
    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    candidate = candidates[0]
    parts = candidate.get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts).strip()
    if not text:
        raise RuntimeError("Gemini returned no text; finishReason=" + str(candidate.get("finishReason", "unknown")))
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned invalid JSON: {text[:1000]}") from exc
    sources = []
    chunks = candidate.get("groundingMetadata", {}).get("groundingChunks", [])
    for chunk in chunks:
        web = chunk.get("web") or {}
        uri, title = web.get("uri"), web.get("title")
        if uri and not any(x["url"] == uri for x in sources):
            sources.append({"title": title or uri, "url": uri})
    return result, sources


def _rule_news(baseline: dict) -> list[dict]:
    drivers = []
    for factor, value in baseline["factors"].items():
        if abs(value) < 0.5:
            continue
        direction = "positive" if value > 0 else "negative"
        drivers.append({"direction": direction, "title": factor, "explanation": "Material move in this market factor.", "impact": round(value * 25, 1)})
    return drivers[:6]


def generate_report(api_key: str = "") -> dict:
    market = collect_market_data()
    baseline = deterministic_analysis(market)
    sectors = []
    for sector, score in sorted(baseline["sector_scores"].items(), key=lambda x: -abs(x[1])):
        sectors.append({
            "sector": sector,
            "direction": "positive" if score > 10 else "negative" if score < -10 else "mixed",
            "score": score,
            "rule_score": score,
            "ai_adjustment": 0,
            "confidence": 60,
            "reason": "Deterministic macro and market sensitivity baseline.",
        })

    report = {
        "market_mood": "Neutral / Mixed",
        "summary": "Fresh market data collected. Add Gemini API access for grounded news synthesis.",
        "outlook": "Watch GIFT Nifty, US yields, Brent, USD/INR, India VIX and FII flows.",
        "confidence": 60,
        "drivers": _rule_news(baseline),
        "sector_impacts": sectors,
        "news_items": [],
        "watchlist": ["GIFT Nifty", "Nifty 50", "Bank Nifty", "India VIX", "USD/INR", "Brent"],
        "events": [],
        "scenarios": [
            {"name": "Base case", "trigger": "Current macro mix persists", "read_through": "Mixed session with sector rotation driven by rates, crude and global cues."}
        ],
        "data_quality": [],
        "sources": [],
    }

    if api_key:
        try:
            ai, sources = _gemini(api_key, market, baseline)
            report.update(ai)
            report["sources"] = sources[:15]
            # Keep machine-observed data-quality notes alongside any AI notes.
            report["data_quality"] = list(dict.fromkeys(
                (market.get("quality") or []) + (report.get("data_quality") or [])
            ))[:8]
            # Preserve the deterministic baseline as the anchor. The AI may only
            # contribute the explicit adjustment field.
            merged = []
            ai_by_sector = {str(x.get("sector")): x for x in report.get("sector_impacts", [])}
            for sector_row in sectors:
                item = ai_by_sector.get(sector_row["sector"], {})
                adjustment = max(-20, min(20, float(item.get("ai_adjustment", 0) or 0)))
                final_score = max(-100, min(100, round(sector_row["rule_score"] + adjustment, 1)))
                merged.append({
                    "sector": sector_row["sector"],
                    "direction": "positive" if final_score > 10 else "negative" if final_score < -10 else "mixed",
                    "score": final_score,
                    "rule_score": sector_row["rule_score"],
                    "ai_adjustment": adjustment,
                    "confidence": max(0, min(100, float(item.get("confidence", 60) or 60))),
                    "reason": item.get("reason") or sector_row["reason"],
                })
            report["sector_impacts"] = sorted(merged, key=lambda x: -abs(x["score"]))
            report["generated_by"] = f"rule-engine + {GEMINI_MODEL} + Google Search"
        except Exception as exc:
            market["quality"].append("Gemini unavailable: " + str(exc))

    report["report_date"] = datetime.now(IST).date().isoformat()
    report["generated_at"] = datetime.now(IST).isoformat()
    report["global_cues"] = [{"name": k, **v} for k, v in market["global"].items()]
    report["india_snapshot"] = [{"name": k, **v} for k, v in market["india"].items() if isinstance(v, dict)]
    report["market_pressure"] = baseline["pressure"]
    report["data_quality"] = list(dict.fromkeys(
        (market.get("quality") or []) + (report.get("data_quality") or [])
    ))[:8]
    report.setdefault("generated_by", "rule-engine")
    return report


NEWS_INSTRUCTION = """
You are the market intelligence layer for an Indian equity pre-market dashboard.

Your job is to explain the current market using REAL-TIME web information.
Use Google Search aggressively for financial news published or materially updated
within the last 24 hours. Search across India, US, Europe, China/Asia, central
banks, inflation/rates, crude/energy, currencies, geopolitics, trade/tariffs,
large Indian companies, and sector-specific developments.

Prefer authoritative or high-quality sources where available: Reuters,
Bloomberg, CNBC, Financial Times, WSJ, RBI, Federal Reserve, ECB, BoJ,
NSE/BSE/company filings and official government releases.

The supplied market-data block is authoritative for numeric market values.
Do not replace supplied prices, percentages or institutional-flow values with
numbers inferred from search. Use search to VERIFY context, find fresh news,
identify catalysts, and explain implications.

Clearly separate:
1) verified facts from current market data and sourced news,
2) interpretation/read-through,
3) conditional scenarios.

Do not give guaranteed predictions or personalized trade instructions. Never claim
that a sector or index will definitely rise or fall. Describe the conditions that
could support or pressure them.
"""
