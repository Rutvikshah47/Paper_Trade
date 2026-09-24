from __future__ import annotations

import json
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests

from .config import settings

IST = ZoneInfo("Asia/Kolkata")
_LAST_GEMINI_STATUS = {
    "configured": False,
    "model": None,
    "ok": False,
    "error": None,
    "sources": 0,
}
NSE_HOME = "https://www.nseindia.com"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"
NSE_VERIFY_SSL = os.getenv("NSE_VERIFY_SSL", "true").strip().lower() not in {"0", "false", "no", "off"}
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


def _float_value(value):
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def gemini_status() -> dict:
    return dict(_LAST_GEMINI_STATUS)


def _google_news_rss() -> tuple[list[dict], list[dict]]:
    """Fetch fresh public Google News RSS headlines for the free-tier fallback.

    This is intentionally separate from Gemini Search grounding. If the API key
    cannot access Gemini 2.5 Flash-Lite, Gemini 3.x can still synthesize these
    fresh headlines without paid Search grounding.
    """
    queries = [
        "India stock market Nifty FII DII RBI",
        "India stocks sectors corporate news",
        "US markets Fed yields dollar oil Asia markets",
    ]
    items = []
    sources = []
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "application/rss+xml,application/xml,text/xml,*/*"})
    for query in queries:
        try:
            from urllib.parse import quote_plus
            import xml.etree.ElementTree as ET
            url = "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-IN&gl=IN&ceid=IN:en"
            response = session.get(url, timeout=15)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            for node in root.findall("./channel/item")[:8]:
                title = (node.findtext("title") or "").strip()
                link = (node.findtext("link") or "").strip()
                pub = (node.findtext("pubDate") or "").strip()
                source_node = node.find("source")
                source = (source_node.text or "").strip() if source_node is not None else "Google News"
                if not title:
                    continue
                items.append({
                    "headline": title,
                    "source": source,
                    "published": pub,
                    "url": link,
                })
                if link and not any(x["url"] == link for x in sources):
                    sources.append({"title": title, "url": link})
        except Exception as exc:
            # Keep the fallback useful even if one RSS query is unavailable.
            continue
    unique = []
    seen = set()
    for item in items:
        key = item["headline"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:15], sources[:15]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "*/*", "Referer": NSE_HOME + "/"})
    return s


def _nse_json(path: str):
    s = _session()
    response = None
    for attempt in range(2):
        s.get(NSE_HOME, timeout=15, verify=NSE_VERIFY_SSL)
        response = s.get(f"{NSE_HOME}/api/{path}", timeout=15, verify=NSE_VERIFY_SSL)
        if response.ok:
            return response.json()
        if response.status_code not in {429, 500, 502, 503, 504} or attempt == 1:
            response.raise_for_status()
        time.sleep(1)
    raise RuntimeError(f"NSE request failed: {path}")



def collect_market_data() -> dict:
    data = {"fetched_at": datetime.now(IST).isoformat(), "global": {}, "india": {}, "quality": []}
    nse = {}

    try:
        payload = _nse_json("NextApi/apiClient?functionName=getIndexData&&type=All")
        for row in payload.get("data", []) or []:
            name = str(row.get("indexName") or "").strip()
            last = _float_value(row.get("last"))
            prev = _float_value(row.get("previousClose"))
            pct = _float_value(row.get("percChange"))
            if not name or last is None or prev in (None, 0):
                continue
            item = {
                "last": last,
                "prev": prev,
                "pct": pct if pct is not None else (last / prev - 1) * 100,
                "source": "NSE",
            }
            data["india"][name] = item
            nse[name.upper()] = item
    except Exception as exc:
        data["quality"].append("NSE index data unavailable: " + str(exc)[:240])

    try:
        gift_payload = _nse_json("NextApi/apiClient?functionName=getGiftNifty")
        gift_data = gift_payload.get("data", {}) if isinstance(gift_payload, dict) else {}
        g = gift_data.get("giftNifty") or gift_data.get("gift_nifty") or {}
        last = _float_value(g.get("lastprice") or g.get("lastPrice") or g.get("last"))
        pct = _float_value(g.get("perchange") or g.get("perChange") or g.get("pct"))
        if last is not None:
            nifty = nse.get("NIFTY 50")
            data["global"]["GIFT Nifty"] = {
                "last": last,
                "pct": pct if pct is not None else 0.0,
                "vs_nifty_close_pct": ((last / nifty["last"]) - 1) * 100 if nifty and nifty.get("last") else None,
                "source": "NSE",
            }
    except Exception as exc:
        data["quality"].append("GIFT Nifty unavailable: " + str(exc)[:180])

    # Global overnight data is obtained in the single Gemini + Google Search
    # request below. This deliberately removes the eleven-request Yahoo path
    # that was repeatedly hitting 429 rate limits on Railway.
    for name, short in [
        ("NIFTY BANK", "Bank Nifty"), ("NIFTY IT", "Nifty IT"),
        ("NIFTY FMCG", "Nifty FMCG"), ("NIFTY AUTO", "Nifty Auto"),
        ("NIFTY FIN SERVICE", "Nifty Financial Services"),
        ("NIFTY METAL", "Nifty Metal"), ("NIFTY PHARMA", "Nifty Pharma"),
        ("NIFTY REALTY", "Nifty Realty"), ("NIFTY OIL & GAS", "Nifty Oil & Gas"),
        ("NIFTY PVT BANK", "Nifty Private Bank"),
        ("INDIA VIX", "India VIX"),
    ]:
        if name in nse:
            data["india"][short] = nse[name]

    # Normalize India VIX casing across NSE payload variants.
    if "India VIX" not in data["india"]:
        for key, value in list(data["india"].items()):
            if key.upper().replace("_", " ") == "INDIA VIX":
                data["india"]["India VIX"] = value
                break

    try:
        rows = _nse_json("fiidiiTradeReact")
        if isinstance(rows, dict):
            rows = rows.get("data") or []
        for row in rows or []:
            cat = str(row.get("category") or row.get("clientType") or "").upper()
            raw = row.get("netValue")
            if raw is None:
                raw = row.get("net_value")
            net = _float_value(str(raw).replace(",", "") if raw is not None else None)
            if net is None:
                continue
            if cat.startswith("FII") or "FII/FPI" in cat:
                data["india"]["FII"] = {"last": net, "unit": "cr", "source": "NSE"}
            elif cat.startswith("DII"):
                data["india"]["DII"] = {"last": net, "unit": "cr", "source": "NSE"}
    except Exception as exc:
        data["quality"].append("FII/DII unavailable: " + str(exc)[:180])

    try:
        breadth = _nse_json("NextApi/apiClient?functionName=getMarketStatistics")
        snap = (breadth.get("data", {}) or {}).get("snapshotCapitalMarket", {}) or {}
        data["india"]["Breadth"] = {
            "advances": int(snap.get("advances") or 0),
            "declines": int(snap.get("declines") or 0),
            "unchanged": int(snap.get("unchange") or snap.get("unchanged") or 0),
            "source": "NSE",
        }
    except Exception as exc:
        data["quality"].append("Breadth unavailable: " + str(exc)[:180])

    return data

def _pct(item) -> float:
    return float(item.get("pct") or 0) if item else 0.0


def _signal(value: float | None, threshold: float, up_positive: bool = True) -> float | None:
    if value is None:
        return None
    if abs(value) < threshold:
        return 0.0
    strength = min(2.0, abs(value) / threshold)
    direction = 1 if value > 0 else -1
    if not up_positive:
        direction *= -1
    return direction * strength


def deterministic_analysis(data: dict) -> dict:
    g, i = data["global"], data["india"]
    def _yield_change_bp(item: dict | None):
        if not item:
            return None
        last, prev = item.get("last"), item.get("prev")
        if last is None or prev is None:
            return None
        return (float(last) - float(prev)) * 100.0

    factors = {
        "us10y": _signal(_yield_change_bp(g.get("US 10Y")), 5.0, False),
        "dxy": _signal(_pct(g.get("DXY")) if g.get("DXY") else None, 0.4, False),
        "nasdaq": _signal(_pct(g.get("Nasdaq")) if g.get("Nasdaq") else None, 0.5),
        "dow": _signal(_pct(g.get("Dow")) if g.get("Dow") else None, 0.5),
        "nikkei": _signal(_pct(g.get("Nikkei")) if g.get("Nikkei") else None, 0.5),
        "hangseng": _signal(_pct(g.get("Hang Seng")) if g.get("Hang Seng") else None, 0.5),
        "shanghai": _signal(_pct(g.get("Shanghai")) if g.get("Shanghai") else None, 0.5),
        "brent": _signal(_pct(g.get("Brent")) if g.get("Brent") else None, 2.0, False),
        "gold": _signal(_pct(g.get("Gold")) if g.get("Gold") else None, 1.5),
        "usdinr": _signal(_pct(i.get("USD/INR")) if i.get("USD/INR") else None, 0.3, False),
        "vix": _signal(_pct(i.get("India VIX")) if i.get("India VIX") else None, 5.0, False),
        "nifty": _signal(_pct(i.get("NIFTY 50")) if i.get("NIFTY 50") else None, 0.7),
        "fii": (
            1.0 if (i.get("FII", {}).get("last") or 0) >= 500
            else -1.0 if (i.get("FII", {}).get("last") or 0) <= -500
            else 0.0
        ) if i.get("FII") else None,
    }

    weights = {
        "us10y": 2, "dxy": 1, "nasdaq": 1.5, "dow": 1, "nikkei": 1,
        "hangseng": 1, "shanghai": 0.75, "brent": 1.5, "gold": 0.5,
        "usdinr": 1, "vix": 1, "nifty": 1, "fii": 1.5,
    }

    available = [k for k, value in factors.items() if value is not None]
    active_weight = sum(weights[k] for k in available)
    total_weight = sum(weights.values()) or 1
    total = sum(factors[k] * weights[k] for k in available)
    pressure = round(max(-100, min(100, total / (active_weight or 1) * 50)), 1)
    coverage_pct = round(active_weight / total_weight * 100, 1)

    sector_scores = {}
    for sector in SECTORS:
        raw = 0.0
        for factor, sensitivity in SENSITIVITY.get(sector, {}).items():
            raw += (factors.get(factor) or 0.0) * sensitivity * 25
        sector_scores[sector] = round(max(-100, min(100, raw)), 1)

    return {
        "pressure": pressure,
        "sector_scores": sector_scores,
        "factors": factors,
        "factor_coverage_pct": coverage_pct,
    }


def _gemini(api_key: str, market: dict, baseline: dict, model: str, news_context: list[dict] | None = None):
    global _LAST_GEMINI_STATUS
    _LAST_GEMINI_STATUS = {
        "configured": bool(api_key),
        "model": model,
        "ok": False,
        "error": None,
        "sources": 0,
    }
    prompt = f"""
{NEWS_INSTRUCTION}

The current time is {datetime.now(IST).isoformat()}.

Important: perform the Google Search grounding yourself in this request. Do not
rely on model memory for any current global market value or current headline.

MARKET DATA (authoritative for numbers):
{json.dumps(market, indent=2)}

FRESH NEWS CONTEXT (use as source material when present; do not invent beyond it):
{json.dumps(news_context or [], indent=2)}

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
    use_google_search = not model.startswith("gemini-3")
    base_payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
    }
    if use_google_search:
        base_payload["tools"] = [{"google_search": {}}]
    # Gemini 2.5 Flash-Lite supports Search grounding and structured output
    # independently, but Google's current docs restrict combining structured
    # outputs with built-in tools to Gemini 3-series models. The free-tier
    # configuration deliberately uses 2.5 Flash-Lite + Search, so send plain
    # JSON text and validate it locally instead of causing a 400 request.
    plain_payload = {
        **base_payload,
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 8000,
        },
    }
    structured_payload = {
        **base_payload,
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": REPORT_SCHEMA,
            "temperature": 0.2,
            "maxOutputTokens": 8000,
        },
    }

    last_error = None
    bodies = []
    models_to_try = [model]
    payloads_by_model = {}
    for selected_model in models_to_try:
        payloads_by_model[selected_model] = (
            (structured_payload, plain_payload)
            if selected_model.startswith("gemini-3")
            else (plain_payload,)
        )

    for selected_model in models_to_try:
        for payload_variant in payloads_by_model[selected_model]:
            for attempt in range(2):
                try:
                    response = requests.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{selected_model}:generateContent",
                        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                        json=payload_variant,
                        timeout=90,
                    )
                    if response.ok:
                        body = response.json()
                        bodies.append(body)
                        break
                    last_error = RuntimeError(
                        f"Gemini HTTP {response.status_code}: {response.text[:1200]}"
                    )
                    if response.status_code in {403, 404}:
                        break
                    if response.status_code not in {400, 429, 500, 502, 503, 504} or attempt == 1:
                        break
                    time.sleep(2 * (attempt + 1))
                except Exception as exc:
                    last_error = exc
                    break
            if bodies:
                break
        if bodies:
            break

    if not bodies:
        _LAST_GEMINI_STATUS["error"] = str(last_error or "Gemini request failed")[:1000]
        raise last_error or RuntimeError("Gemini request failed")

    body = bodies[0]
    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError("Gemini returned no candidates")
    candidate = candidates[0]
    content = candidate.get("content") or {}
    parts = content.get("parts", []) if isinstance(content, dict) else []
    if isinstance(parts, dict):
        parts = [parts]
    if isinstance(parts, str):
        parts = [{"text": parts}]
    text = "".join(
        p.get("text", "") if isinstance(p, dict) else str(p)
        for p in parts
    ).strip()
    if not text:
        raise RuntimeError("Gemini returned no text; finishReason=" + str(candidate.get("finishReason", "unknown")))
    if text.startswith("```"):
        text = text.replace("```json", "", 1).replace("```", "", 1).strip()
    try:
        result = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Gemini returned invalid JSON: {text[:1200]}") from exc
    if not isinstance(result, dict):
        raise RuntimeError(f"Gemini returned JSON of type {type(result).__name__}; expected object")
    sources = []
    grounding = (
        candidate.get("groundingMetadata")
        or candidate.get("grounding_metadata")
        or {}
    )
    chunks = grounding.get("groundingChunks") or grounding.get("grounding_chunks") or []
    if isinstance(chunks, dict):
        chunks = [chunks]
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        web = chunk.get("web") or {}
        if not isinstance(web, dict):
            continue
        uri, title = web.get("uri"), web.get("title")
        if uri and not any(x["url"] == uri for x in sources):
            sources.append({"title": title or uri, "url": uri})
    _LAST_GEMINI_STATUS.update({
        "ok": True,
        "error": None,
        "sources": len(sources),
    })
    return result, sources


def _rule_news(baseline: dict) -> list[dict]:
    drivers = []
    for factor, value in baseline["factors"].items():
        if value is None or abs(value) < 0.5:
            continue
        direction = "positive" if value > 0 else "negative"
        drivers.append({"direction": direction, "title": factor, "explanation": "Material move in this market factor.", "impact": round(value * 25, 1)})
    return drivers[:6]


def generate_report(api_key: str = "") -> dict:
    runtime_api_key = (os.getenv("GEMINI_API_KEY") or api_key or "").strip()
    runtime_model = (os.getenv("GEMINI_MODEL") or settings.gemini_model).strip()
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

    fallback_mood = (
        "Bullish" if baseline["pressure"] >= 30 else
        "Cautious Positive" if baseline["pressure"] >= 10 else
        "Neutral / Mixed" if baseline["pressure"] > -10 else
        "Cautious Negative" if baseline["pressure"] > -30 else
        "Bearish"
    )
    report = {
        "market_mood": fallback_mood,
        "summary": "Indian market data collected. Gemini adds grounded global cues, news and sector read-through when configured.",
        "outlook": "Watch GIFT Nifty, global cues, US yields, Brent, USD/INR, India VIX and FII flows.",
        "confidence": 60,
        "drivers": _rule_news(baseline),
        "sector_impacts": sectors,
        "news_items": [],
        "watchlist": ["GIFT Nifty", "Nifty 50", "Bank Nifty", "India VIX", "USD/INR", "Brent"],
        "events": [],
        "scenarios": [
            {"name": "Constructive", "trigger": "Global risk assets remain firm and domestic breadth improves", "read_through": "Broader participation could support risk appetite."},
            {"name": "Base case", "trigger": "Current macro mix persists", "read_through": "Mixed session with rotation driven by rates, crude, flows and global cues."},
            {"name": "Cautious", "trigger": "Global risk-off strengthens and domestic breadth remains weak", "read_through": "Pressure could remain concentrated in high-beta and rate-sensitive segments."}
        ],
        "data_quality": [],
        "sources": [],
    }

    if runtime_api_key:
        try:
            fallback_news, fallback_sources = _google_news_rss() if runtime_model.startswith("gemini-3") else ([], [])
            ai, sources = _gemini(
                runtime_api_key,
                market,
                baseline,
                runtime_model,
                news_context=fallback_news,
            )
            search_global = ai.get("global_cues") or []
            if isinstance(search_global, dict):
                search_global = [search_global]
            if not isinstance(search_global, list):
                search_global = []
            for item in search_global:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "").strip()
                try:
                    last = float(item.get("last"))
                    prev = float(item.get("prev"))
                    pct = float(item.get("pct"))
                except (TypeError, ValueError):
                    continue
                if not name or prev == 0:
                    continue
                if name == "GIFT Nifty":
                    continue
                target = market["india"] if name == "USD/INR" else market["global"]
                target[name] = {"last": last, "prev": prev, "pct": pct, "source": "Gemini Google Search"}

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
                    "reason": "Deterministic baseline using NSE data plus search-verified global cues.",
                })

            report.update(ai)
            report["sources"] = (sources or fallback_sources)[:15]
            # Keep machine-observed data-quality notes alongside any AI notes.
            report["data_quality"] = list(dict.fromkeys(
                (market.get("quality") or []) + (report.get("data_quality") or [])
            ))[:8]
            # Preserve the deterministic baseline as the anchor. The AI may only
            # contribute the explicit adjustment field.
            merged = []
            ai_sector_rows = report.get("sector_impacts", [])
            if isinstance(ai_sector_rows, dict):
                ai_sector_rows = [ai_sector_rows]
            if not isinstance(ai_sector_rows, list):
                ai_sector_rows = []
            ai_by_sector = {
                str(x.get("sector")): x
                for x in ai_sector_rows
                if isinstance(x, dict) and x.get("sector")
            }
            for sector_row in sectors:
                item = ai_by_sector.get(sector_row["sector"], {})
                raw_adjustment = item.get("ai_adjustment", 0) if isinstance(item, dict) else 0
                raw_confidence = item.get("confidence", 60) if isinstance(item, dict) else 60
                try:
                    adjustment = max(-20, min(20, float(raw_adjustment or 0)))
                except (TypeError, ValueError):
                    adjustment = 0.0
                final_score = max(-100, min(100, round(sector_row["rule_score"] + adjustment, 1)))
                merged.append({
                    "sector": sector_row["sector"],
                    "direction": "positive" if final_score > 10 else "negative" if final_score < -10 else "mixed",
                    "score": final_score,
                    "rule_score": sector_row["rule_score"],
                    "ai_adjustment": adjustment,
                    "confidence": max(0, min(100, float(raw_confidence or 60))),
                    "reason": (item.get("reason") if isinstance(item, dict) else None) or sector_row["reason"],
                })
            report["sector_impacts"] = sorted(merged, key=lambda x: -abs(x["score"]))
            source_label = "Google News RSS" if runtime_model.startswith("gemini-3") else "Google Search"
            report["generated_by"] = f"rule-engine + {runtime_model} + {source_label}"
            verified_global = sum(
                1 for name in (
                    "Nasdaq", "Dow", "S&P 500", "Nikkei", "Hang Seng",
                    "Shanghai", "Brent", "Gold", "DXY", "US 10Y", "USD/INR"
                )
                if market["global"].get(name, {}).get("last") is not None
                or market["india"].get(name, {}).get("last") is not None
            )
            market["quality"].append(
                f"Google Search global-cue coverage: {verified_global}/11 verified."
            )
            report["data_quality"] = list(dict.fromkeys(
                (market.get("quality") or []) + (report.get("data_quality") or [])
            ))[:12]
        except Exception as exc:
            error = str(exc)[:1000]
            # Google currently limits access to Gemini 2.5 models for some newer
            # projects. Automatically fall back to a current free-tier Gemini 3
            # model and feed it fresh public RSS headlines instead of paid Search
            # grounding. This keeps the report useful without requiring billing.
            if runtime_model.startswith("gemini-2.5"):
                fallback_model = "gemini-3.5-flash-lite"
                try:
                    fallback_news, fallback_sources = _google_news_rss()
                    ai, sources = _gemini(
                        runtime_api_key,
                        market,
                        baseline,
                        fallback_model,
                        news_context=fallback_news,
                    )
                    report.update(ai)
                    report["sources"] = (sources or fallback_sources)[:15]
                    report["generated_by"] = f"rule-engine + {fallback_model} + Google News RSS"
                    report["data_quality"] = list(dict.fromkeys(
                        (market.get("quality") or [])
                        + ["Gemini 2.5 unavailable; used free-tier Gemini 3.8 with Google News RSS fallback."]
                        + (report.get("data_quality") or [])
                    ))[:12]
                except Exception as fallback_exc:
                    market["quality"].insert(0, "Gemini fallback unavailable: " + str(fallback_exc)[:800])
                    market["quality"].insert(0, "Gemini 2.5 unavailable: " + error)
                    report["generated_by"] = f"rule-engine (Gemini failed: {runtime_model})"
                    report["summary"] = "Gemini synthesis failed; showing the rule-based market report and both failure reasons in Data Quality."
            else:
                market["quality"].insert(0, "Gemini unavailable: " + error)
                report["generated_by"] = f"rule-engine (Gemini failed: {runtime_model})"
                report["summary"] = "Gemini synthesis failed; showing the rule-based market report and the failure reason in Data Quality."

    report["report_date"] = datetime.now(IST).date().isoformat()
    report["generated_at"] = datetime.now(IST).isoformat()
    report["global_cues"] = [{"name": k, **v} for k, v in market["global"].items()]
    report["india_snapshot"] = [{"name": k, **v} for k, v in market["india"].items() if isinstance(v, dict)]
    report["market_pressure"] = baseline["pressure"]
    report["data_quality"] = list(dict.fromkeys(
        (market.get("quality") or []) + (report.get("data_quality") or [])
    ))[:12]
    if not runtime_api_key:
        report["generated_by"] = "rule-engine (Gemini not configured)"
        report["data_quality"].insert(0, "Gemini disabled: GEMINI_API_KEY is not available to the running process.")
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
