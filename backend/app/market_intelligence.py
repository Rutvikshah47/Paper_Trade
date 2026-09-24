from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from .config import settings

IST = ZoneInfo("Asia/Kolkata")
NSE_HOME = "https://www.nseindia.com"
YAHOO_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
GEMINI_MODEL = settings.gemini_model

YAHOO_SYMBOLS = {
    "Nasdaq": "^IXIC",
    "Dow": "^DJI",
    "S&P 500": "^GSPC",
    "Nikkei": "^N225",
    "Hang Seng": "^HSI",
    "Shanghai": "000001.SS",
    "Brent": "BZ=F",
    "Gold": "GC=F",
    "DXY": "DX-Y.NYB",
    "US 10Y": "^TNX",
    "USD/INR": "INR=X",
}

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
    "required": ["market_mood", "summary", "outlook", "confidence", "drivers", "sector_impacts", "news_items", "watchlist", "events", "scenarios", "data_quality"],
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


def _yahoo(symbol: str):
    encoded = requests.utils.quote(symbol, safe="")
    response = requests.get(
        f"{YAHOO_CHART}{encoded}",
        params={"range": "5d", "interval": "1d", "includePrePost": "true"},
        headers={"User-Agent": UA},
        timeout=15,
        verify=False,
    )
    response.raise_for_status()
    result = (response.json().get("chart", {}).get("result") or [])
    if not result:
        return None
    closes = [x for x in (result[0].get("indicators", {}).get("quote", [{}])[0].get("close") or []) if x is not None]
    if len(closes) < 2:
        return None
    return float(closes[-1]), float(closes[-2])


def collect_market_data() -> dict:
    data = {"fetched_at": datetime.now(IST).isoformat(), "global": {}, "india": {}, "quality": []}
    nse = {}
    try:
        payload = _nse_json("NextApi/apiClient?functionName=getIndexData&&type=All")
        for row in payload.get("data", []):
            name = row.get("indexName")
            if name:
                data["india"][name] = {
                    "last": float(row.get("last") or 0),
                    "prev": float(row.get("previousClose") or 0),
                    "pct": float(row.get("percChange") or 0),
                }
                nse[name] = data["india"][name]
    except Exception as exc:
        data["quality"].append("NSE index data unavailable: " + str(exc))

    try:
        gift = _nse_json("NextApi/apiClient?functionName=getGiftNifty").get("data", {})
        g = gift.get("giftNifty") or {}
        if g.get("lastprice"):
            data["global"]["GIFT Nifty"] = {
                "last": float(g["lastprice"]),
                "pct": float(g.get("perchange") or 0),
                "vs_nifty_close_pct": (
                    (float(g["lastprice"]) / nse["NIFTY 50"]["last"] - 1) * 100
                    if "NIFTY 50" in nse and nse["NIFTY 50"]["last"] else None
                ),
            }
    except Exception as exc:
        data["quality"].append("GIFT Nifty unavailable: " + str(exc))

    for label, symbol in YAHOO_SYMBOLS.items():
        try:
            q = _yahoo(symbol)
            if not q:
                data["quality"].append(label + " unavailable")
                continue
            last, prev = q
            if label == "US 10Y" and last > 20:
                last, prev = last / 10, prev / 10
            data["global" if label not in {"USD/INR"} else "india"][label] = {
                "last": last, "prev": prev, "pct": (last / prev - 1) * 100
            }
        except Exception as exc:
            data["quality"].append(label + " unavailable: " + str(exc))

    for name, short in [
        ("NIFTY BANK", "Bank Nifty"), ("NIFTY IT", "Nifty IT"),
        ("NIFTY FMCG", "Nifty FMCG"), ("NIFTY AUTO", "Nifty Auto"),
        ("NIFTY FIN SERVICE", "Nifty Financial Services"),
        ("NIFTY METAL", "Nifty Metal"), ("NIFTY PHARMA", "Nifty Pharma"),
        ("NIFTY REALTY", "Nifty Realty"), ("NIFTY OIL & GAS", "Nifty Oil & Gas"),
        ("NIFTY PVT BANK", "Nifty Private Bank"),
    ]:
        if name in nse:
            data["india"][short] = nse[name]

    try:
        rows = _nse_json("fiidiiTradeReact")
        for row in rows:
            cat = str(row.get("category", "")).upper()
            net = float(str(row.get("netValue", "0")).replace(",", ""))
            if cat.startswith("FII"):
                data["india"]["FII"] = {"last": net, "unit": "cr"}
            elif cat.startswith("DII"):
                data["india"]["DII"] = {"last": net, "unit": "cr"}
    except Exception as exc:
        data["quality"].append("FII/DII unavailable: " + str(exc))

    try:
        breadth = _nse_json("NextApi/apiClient?functionName=getMarketStatistics").get("data", {}).get("snapshotCapitalMarket", {})
        data["india"]["Breadth"] = {
            "advances": int(breadth.get("advances") or 0),
            "declines": int(breadth.get("declines") or 0),
            "unchanged": int(breadth.get("unchange") or 0),
        }
    except Exception as exc:
        data["quality"].append("Breadth unavailable: " + str(exc))
    return data


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


def _gemini(api_key: str, market: dict, baseline: dict):
    prompt = f"""
{NEWS_INSTRUCTION}

The current time is {datetime.now(IST).isoformat()}.

MARKET DATA (authoritative for numbers):
{json.dumps(market, indent=2)}

DETERMINISTIC BASELINE:
{json.dumps(baseline, indent=2)}

Search for fresh news from the last 24 hours and today's events. Cover India,
US, Asia, Europe, central banks, inflation/rates, crude/energy, geopolitics,
trade/tariffs, major Indian company or sector developments, and anything that
could materially affect Indian equities. Also assess the three conditional
scenarios: Constructive, Base case, and Cautious. Each scenario must name the
observable trigger and the India-market read-through. Do not assign made-up
probabilities.

Return structured JSON only. Keep the supplied numeric market data unchanged.
For each sector, start from its deterministic baseline score and use ai_adjustment
(-20 to +20) only for a clear fresh-news reason. Do not invent source URLs or
market numbers. Do not give personalized trade instructions.
"""
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "responseFormat": {
                "text": {
                    "mimeType": "application/json",
                    "schema": REPORT_SCHEMA,
                }
            },
            "temperature": 0.2,
            "maxOutputTokens": 12000,
        },
    }
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    response.raise_for_status()
    body = response.json()
    parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts)
    result = json.loads(text)
    sources = []
    chunks = body.get("candidates", [{}])[0].get("groundingMetadata", {}).get("groundingChunks", [])
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
        "market_mood": "Mixed / Cautious",
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
            report["generated_by"] = "rule-engine + Gemini 3.8 Flash + Google Search"
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
""
