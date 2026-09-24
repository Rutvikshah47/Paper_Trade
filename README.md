# Paper Trader — Local Upstox Paper-Trading Terminal

A local paper-trading application for multi-leg NSE options strategies.

**Important:** Upstox is used for market-data/instrument resolution only. This application does **not** place, modify, or cancel Upstox orders.

## Stack

- React + Vite
- FastAPI
- SQLAlchemy + SQLite
- Upstox Instrument Search / Option Contracts
- Upstox Market Data Feed V3 via `upstox-python-sdk`
- Telegram alerts
- Paper P&L engine

## Live mode

Create `backend/.env`:

```text
USE_MOCK_MARKET_DATA=false
UPSTOX_ACCESS_TOKEN=YOUR_ACCESS_TOKEN

TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=-5397224177
TELEGRAM_INTERVAL_SECONDS=300
SIGNIFICANT_PNL_CHANGE=100
SIGNIFICANT_ALERT_COOLDOWN_SECONDS=60

UPSTOX_VERIFY_SSL=true
TELEGRAM_VERIFY_SSL=true
```

Never commit `.env` or real access tokens.

## Run backend

```bash
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

Using `python -m uvicorn` is intentional: it guarantees Uvicorn runs from the active virtual environment.

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

## Run frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open:

```text
http://localhost:5173
```

## Live flow

1. Create a paper strategy with one or more option legs.
2. Backend resolves every leg against Upstox and stores the exact `instrument_key` and lot size.
3. Backend subscribes all open legs to Upstox Market Data Feed V3.
4. LTPs are maintained in an in-memory thread-safe cache.
5. P&L is recalculated from the latest LTP.
6. UI polls the dashboard every 1.5 seconds.
7. Telegram sends a portfolio snapshot every 5 minutes.
8. A significant P&L movement can generate an additional alert.

## P&L

SELL:

```text
(entry price - current LTP) × lots × lot size
```

BUY:

```text
(current LTP - entry price) × lots × lot size
```

Strategy P&L is the sum of all its legs. Portfolio P&L is the sum of all strategies.

## Useful API endpoints

```text
GET  /api/health
GET  /api/dashboard
GET  /api/market/status
POST /api/market/connect

GET  /api/strategies
GET  /api/strategies/{id}
POST /api/strategies
DELETE /api/strategies/{id}

GET  /api/upstox/underlying?symbol=INFY
GET  /api/upstox/expiries?symbol=INFY
GET  /api/upstox/contracts?symbol=INFY&expiry=2026-09-29
GET  /api/upstox/resolve-option?symbol=INFY&expiry=2026-09-29&strike=1020&option_type=PE
```

## Troubleshooting

### npm hangs

Check:

```bash
npm config get registry
```

For a normal personal/local install, the public registry is:

```text
https://registry.npmjs.org/
```

### Upstox SSL error

Prefer fixing the local CA/certificate chain. `UPSTOX_VERIFY_SSL=false` exists only as a temporary development workaround.

### No LTP

Check:

```bash
curl http://127.0.0.1:8000/api/market/status
```

Then inspect `last_error` and confirm the access token has not expired.

## Tests

From the project root:

```bash
cd backend
source .venv/bin/activate
cd ..
pytest -q
```

## Market Intelligence

The Market Intelligence page generates a fresh report on demand; no scheduled job is required.

Click **Market Intelligence** in the header, then **Generate fresh report**. The backend fetches current India/global market data (including GIFT Nifty, US/Asian indices, US 10Y, DXY, Brent, gold, USD/INR, India VIX, Nifty/sector indices, breadth and FII/DII flows), calculates a deterministic market/sector baseline, and then uses Gemini with Google Search grounding for fresh news, sector read-through and a conditional outlook.

Set in `backend/.env`:

```text
GEMINI_API_KEY=YOUR_GEMINI_API_KEY
GEMINI_MODEL=gemini-3.8-flash
```

The API key stays on the backend and is never exposed to the browser. Reports are persisted in the `market_reports` table so previous manual generations can be compared later.

The sector score is anchored to deterministic market sensitivities. Gemini may add an explicit news adjustment of at most +/-20; the supplied market-data numbers are not replaced by AI-generated numbers.

Endpoints:

```text
GET  /api/market-intelligence/latest
GET  /api/market-intelligence/history?limit=8
POST /api/market-intelligence/generate
```