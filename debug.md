Absolutely. Below is a **copy-paste-ready deployment/setup document** for the Paper Trader application, including the installation issues we encountered and their fixes.

# Paper Trader — Local Deployment & Setup Guide

## 1. Application Overview

Paper Trader is a local web application with:

* **Frontend:** React-based UI
* **Backend:** Python + FastAPI
* **Database:** SQLite + SQLAlchemy
* **Market Data:** Upstox Market Data WebSocket V3
* **Notifications:** Telegram Bot API
* **Trading Mode:** **Paper trading only**
* **Python:** 3.12
* **Frontend package manager:** npm
* **Backend environment:** Python virtual environment (`.venv`)

The application does **not** place real orders with Upstox.

---

# 2. Prerequisites

Install the following on macOS:

* Git
* Python 3.12
* Node.js / npm
* pyenv — recommended for Python version management

Verify:

```bash
python3 --version
node --version
npm --version
git --version
```

Recommended versions:

```text
Python 3.12.x
Node.js 18+ / 20+
npm 9+
```

---

# 3. Project Directory

Current project structure:

```text
Trading/
└── paper-trader/
    ├── backend/
    │   ├── app/
    │   ├── tests/
    │   ├── .env
    │   ├── .env.example
    │   └── requirements.txt
    │
    └── frontend/
        ├── src/
        ├── package.json
        └── ...
```

Current local path:

```bash
/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader
```

Go to the project:

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader"
```

---

# 4. Backend Setup

Go to backend:

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/backend"
```

---

## 5. Create Python Virtual Environment

Because the project uses Python packages such as FastAPI, SQLAlchemy and Upstox SDK, use a dedicated virtual environment.

Create it:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

You should see something similar to:

```text
(.venv) rutvik.shah@... backend %
```

Verify Python:

```bash
which python
```

Expected:

```text
.../paper-trader/backend/.venv/bin/python
```

Verify:

```bash
python --version
```

Expected:

```text
Python 3.12.x
```

---

# 6. Install Backend Packages

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Verify important packages:

```bash
python -c "import sqlalchemy, fastapi, pydantic; print('Dependencies OK')"
```

Expected:

```text
Dependencies OK
```

Also verify Upstox:

```bash
python -c "import upstox_client; print('Upstox SDK OK')"
```

---

# 7. Important: Always Use the Virtual Environment Python

One issue we encountered was running `uvicorn` from the global environment.

For example:

```bash
uvicorn app.main:app --reload --port 8000
```

This can accidentally use a globally installed `uvicorn`, which may use a different Python environment.

This resulted in errors such as:

```text
ModuleNotFoundError: No module named 'sqlalchemy'
```

### Correct command

Always start the backend using:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

This guarantees that `uvicorn` runs using the currently activated `.venv`.

---

# 8. Backend Environment Variables

Create:

```text
backend/.env
```

Use `.env.example` as the template:

```bash
cp .env.example .env
```

Edit:

```bash
nano .env
```

The environment file should contain the required configuration, such as:

```text
UPSTOX_ACCESS_TOKEN=your_upstox_access_token

TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_CHAT_ID=your_telegram_chat_id

TELEGRAM_INTERVAL_SECONDS=300
SIGNIFICANT_PNL_CHANGE=100
SIGNIFICANT_ALERT_COOLDOWN_SECONDS=60
```

If SSL verification configuration is present in the project, use the project's configured value appropriately.

### Important

Do **not** commit `.env` to Git.

Add this to `.gitignore`:

```text
.env
.venv/
__pycache__/
*.pyc
```

---

# 9. Start Backend

From:

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/backend"
```

Activate environment:

```bash
source .venv/bin/activate
```

Start FastAPI:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Expected output should contain something similar to:

```text
Uvicorn running on http://127.0.0.1:8000
```

---

# 10. Verify Backend

Open:

```text
http://127.0.0.1:8000
```

Health endpoint:

```bash
curl http://127.0.0.1:8000/api/health
```

Example:

```json
{
  "status": "ok"
}
```

The application also exposes API documentation through FastAPI.

Open:

```text
http://127.0.0.1:8000/docs
```

This is useful for manually testing backend APIs.

---

# 11. Frontend Setup

Open another terminal.

Go to:

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/frontend"
```

Install npm dependencies:

```bash
npm install
```

Start the frontend:

```bash
npm run dev
```

The terminal should display the frontend URL, normally something like:

```text
http://localhost:5173
```

Open that URL in the browser.

---

# 12. Frontend + Backend

During local development:

```text
Browser
   |
   v
Frontend
localhost:5173
   |
   v
Backend
localhost:8000
   |
   +---- SQLite
   |
   +---- Upstox WebSocket
   |
   +---- Telegram API
```

Keep **two terminals** running.

### Terminal 1 — Backend

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/backend"

source .venv/bin/activate

python -m uvicorn app.main:app --reload --port 8000
```

### Terminal 2 — Frontend

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/frontend"

npm run dev
```

Then open:

```text
http://localhost:5173
```

---

# 13. Upstox Configuration

The application uses the Upstox Python SDK.

The important import is:

```python
import upstox_client
```

The SDK configuration is:

```python
configuration = upstox_client.Configuration()
configuration.access_token = ACCESS_TOKEN

api_client = upstox_client.ApiClient(configuration)
```

The application uses the **Market Data Feed V3 WebSocket** for live prices.

---

# 14. Upstox WebSocket

The application uses:

```python
upstox_client.MarketDataStreamerV3
```

Typical initialization:

```python
streamer = upstox_client.MarketDataStreamerV3(
    api_client,
    [],
    "full",
)
```

Events:

```python
streamer.on("open", on_open)
streamer.on("message", on_message)
streamer.on("error", on_error)
streamer.on("close", on_close)
```

Then:

```python
streamer.connect()
```

### Important

Use string event names:

```python
"open"
"message"
"error"
"close"
```

Do not assume an enum such as:

```python
WebSocketEventType.OPEN
```

is available in the installed SDK version.

---

# 15. Subscribing to Market Data

After WebSocket connection:

```python
streamer.subscribe(
    chain["subscriptions"],
    MODE,
)
```

Supported modes used during development include:

```text
ltpc
option_greeks
full
full_d30
```

For richer market information, `full` was used.

Example live feed:

```json
{
  "feeds": {
    "NSE_EQ|INE009A01021": {
      "fullFeed": {
        "marketFF": {
          "ltpc": {
            "ltp": 1040.0
          }
        }
      }
    }
  }
}
```

---

# 16. Upstox Instrument Keys

Upstox WebSocket subscriptions require the instrument key.

Example:

```text
NSE_EQ|INE009A01021
```

For options:

```text
NSE_FO|83369
```

The application resolves option instruments before subscribing.

For example:

```text
INFY 1020 PE 29 SEP 26
```

was resolved to:

```text
NSE_FO|83369
```

---

# 17. Upstox REST API SSL Issue

We encountered this issue while making REST requests:

```text
requests.exceptions.SSLError:
certificate verify failed:
unable to get local issuer certificate
```

This is generally caused by the local Python environment not trusting the certificate chain, often due to corporate proxy / CA configuration.

---

# 18. Temporary SSL Workaround

The application supports an SSL verification configuration.

For local troubleshooting, SSL verification was temporarily disabled.

For example:

```text
UPSTOX_VERIFY_SSL=false
```

If requests are made directly:

```python
requests.get(
    url,
    verify=False,
)
```

and warnings can be suppressed:

```python
import urllib3

urllib3.disable_warnings(
    urllib3.exceptions.InsecureRequestWarning
)
```

### Important

This should be treated as a **temporary troubleshooting workaround**.

Do not permanently disable TLS certificate verification in a production deployment.

---

# 19. Preferred SSL Fix

The preferred solution is to configure Python/requests with the correct CA certificate.

First check certifi:

```bash
python -c "import certifi; print(certifi.where())"
```

Upgrade certifi:

```bash
python -m pip install --upgrade certifi
```

If your corporate network uses a custom CA, obtain the approved corporate CA certificate and configure the application/environment to trust it.

For example:

```bash
export REQUESTS_CA_BUNDLE=/path/to/corporate-ca.pem
```

Then restart the backend.

---

# 20. Telegram Configuration

The application sends paper-trading P&L notifications through Telegram.

Required:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Example:

```text
TELEGRAM_BOT_TOKEN=<bot token>
TELEGRAM_CHAT_ID=-5397224177
```

The Telegram bot must have permission to send messages to the target group.

---

# 21. Telegram Notification Format

The application sends notifications similar to:

```text
📊 OPTION P&L UPDATE

Updated: 20-Sep-2026 11:04:21 PM

INFY 960 PE
Expiry: 2026-09-29
SELL ₹1.05 → ₹1.05
Qty: 400
P&L: +₹0.00

INFY 1220 CE
Expiry: 2026-09-29
SELL ₹0.55 → ₹0.55
Qty: 400
P&L: +₹0.00

----------------------------
TOTAL P&L: +₹0.00
```

---

# 22. Telegram HTML Formatting Issue

Initially, Telegram HTML parsing was used.

This caused problems because option-related text can contain characters such as:

```text
<
>
```

For example:

```text
<--- ATM
```

Telegram interpreted these as HTML.

The solution was to use **plain text** instead of Telegram HTML parsing.

Therefore, the Telegram request should use:

```python
data={
    "chat_id": chat_id,
    "text": text,
}
```

rather than:

```python
data={
    "chat_id": chat_id,
    "text": text,
    "parse_mode": "HTML",
}
```

unless the message is properly HTML-escaped.

---

# 23. Paper P&L Calculation

For a short option:

```text
P&L = (Entry Price - Current LTP) × Quantity
```

For a long option:

```text
P&L = (Current LTP - Entry Price) × Quantity
```

Quantity:

```text
Quantity = Number of Lots × Lot Size
```

Example:

```text
SELL INFY 960 PE
Entry = ₹1.05
Current = ₹0.80
Lot Size = 400
Lots = 1
```

P&L:

```text
(1.05 - 0.80) × 400
= ₹100
```

---

# 24. Current Paper Positions Example

Example positions used during development:

```text
INFY 960 PE
SELL
Entry: ₹1.05
Lots: 1
Lot size: 400
Expiry: 29-Sep-2026
```

and:

```text
INFY 1220 CE
SELL
Entry: ₹0.55
Lots: 1
Lot size: 400
Expiry: 29-Sep-2026
```

Total premium received:

```text
₹420 + ₹220
= ₹640
```

The P&L is then calculated dynamically using live option LTP.

---

# 25. Telegram Notification Frequency

Current configuration:

```text
TELEGRAM_INTERVAL_SECONDS=300
```

means:

```text
300 seconds = 5 minutes
```

So a periodic notification is sent every 5 minutes.

Significant P&L threshold:

```text
SIGNIFICANT_PNL_CHANGE=100
```

means a significant alert is triggered when the portfolio P&L changes by at least:

```text
₹100
```

Cooldown:

```text
SIGNIFICANT_ALERT_COOLDOWN_SECONDS=60
```

prevents repeated alerts from being sent too frequently.

---

# 26. Database

The application uses SQLite through SQLAlchemy.

The database is local to the backend.

Typical architecture:

```text
FastAPI
   |
SQLAlchemy
   |
SQLite
```

The database stores things such as:

* Strategies
* Orders
* Paper positions
* Option information
* Entry prices
* Quantity
* Status

---

# 27. Running Backend Tests

From backend:

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/backend"

source .venv/bin/activate
```

Run:

```bash
pytest
```

At one stage the complete backend test suite passed:

```text
8 passed
```

Warnings may be shown; warnings are not necessarily test failures.

For more verbose output:

```bash
pytest -v
```

---

# 28. Common Issue — `ModuleNotFoundError`

### Error

```text
ModuleNotFoundError: No module named 'sqlalchemy'
```

### Cause

Usually the application is being executed using the global Python installation rather than the project's `.venv`.

### Fix

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/backend"

source .venv/bin/activate

python -m pip install -r requirements.txt

python -m uvicorn app.main:app --reload --port 8000
```

Verify:

```bash
which python
```

It should point to:

```text
.../backend/.venv/bin/python
```

---

# 29. Common Issue — Global Uvicorn

Avoid:

```bash
uvicorn app.main:app --reload
```

Prefer:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

This ensures the correct Python environment is used.

---

# 30. Common Issue — `npm EPERM: operation not permitted, uv_cwd`

We encountered:

```text
npm ERR! code EPERM
npm ERR! syscall uv_cwd
npm ERR! operation not permitted
```

This can occur when the current working directory is no longer accessible or the terminal is in a stale/deleted directory.

### Fix

Move somewhere safe:

```bash
cd ~
```

Then return to the frontend:

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/frontend"
```

Then:

```bash
npm install
```

or:

```bash
npm run dev
```

---

# 31. Common Issue — npm Registry / Corporate Artifactory

The npm registry in the environment was configured to:

```text
https://artifactory.dyn.nutanix.com/artifactory/api/npm/canaveral-npm
```

Check current registry:

```bash
npm config get registry
```

If npm is expected to use the corporate Artifactory, keep the configured registry.

If troubleshooting a public project outside the corporate environment, verify whether the registry should instead be:

```text
https://registry.npmjs.org/
```

Do not blindly change the corporate registry if corporate authentication/dependencies depend on it.

---

# 32. Common Issue — Frontend Doesn't Start

Check Node:

```bash
node --version
```

Check npm:

```bash
npm --version
```

Go to frontend:

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/frontend"
```

Remove dependencies if installation is corrupted:

```bash
rm -rf node_modules
```

Then:

```bash
npm install
```

Start:

```bash
npm run dev
```

---

# 33. Check Backend Port

Check whether port 8000 is already occupied:

```bash
lsof -i :8000
```

If an old process is running, stop it:

```bash
kill <PID>
```

Then:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

---

# 34. Check Frontend Port

Check:

```bash
lsof -i :5173
```

If the port is occupied, either stop the old process or allow Vite to choose another port.

---

# 35. Debugging Backend Health

Run:

```bash
curl http://127.0.0.1:8000/api/health
```

The application may return fields similar to:

```json
{
  "status": "ok",
  "market_data": "DISCONNECTED",
  "mode": "upstox",
  "telegram_configured": true,
  "upstox_configured": true,
  "last_market_error": null
}
```

### Important

`market_data: DISCONNECTED` does not necessarily mean the entire application is broken.

If no strategy/options have been subscribed yet, the WebSocket may have no active subscriptions.

After a strategy is created and instruments are subscribed, live LTP data should begin flowing.

---

# 36. Verifying Live Market Data

Once a strategy is created:

1. Create the paper strategy.
2. Add option legs.
3. Resolve the Upstox instrument.
4. Subscribe to the instrument.
5. Upstox WebSocket receives market data.
6. Backend updates the LTP cache.
7. Frontend displays the LTP.
8. P&L is recalculated.

Architecture:

```text
Upstox
   |
   | WebSocket V3
   v
MarketDataStreamerV3
   |
   v
Market LTP Cache
   |
   +---------> Frontend
   |
   +---------> P&L Engine
   |
   +---------> Telegram Alerts
```

---

# 37. Debugging Upstox Live LTP

If LTP is not appearing:

### Step 1 — Check backend

```bash
curl http://127.0.0.1:8000/api/health
```

### Step 2 — Check terminal logs

Look for:

```text
WebSocket connected
subscription
market data
```

or errors.

### Step 3 — Verify access token

Check that:

```text
UPSTOX_ACCESS_TOKEN
```

is configured correctly.

### Step 4 — Verify instrument key

For example:

```text
NSE_FO|83369
```

### Step 5 — Check whether the strategy has actually subscribed to the option.

### Step 6 — Check frontend browser console.

---

# 38. Application Startup Checklist

Every time the application needs to be started:

### Terminal 1

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/backend"
```

```bash
source .venv/bin/activate
```

```bash
python -m uvicorn app.main:app --reload --port 8000
```

### Terminal 2

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/frontend"
```

```bash
npm run dev
```

### Browser

Open:

```text
http://localhost:5173
```

### Backend health

```bash
curl http://127.0.0.1:8000/api/health
```

---

# 39. Complete Fresh Installation

If the project needs to be installed on a new Mac:

```bash
git clone <repository>
```

Then:

```bash
cd paper-trader/backend
```

Create virtual environment:

```bash
python3 -m venv .venv
```

Activate:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Verify:

```bash
python -c "import sqlalchemy, fastapi, pydantic; print('Dependencies OK')"
```

Configure:

```bash
cp .env.example .env
```

Edit `.env` with the required credentials.

Run backend:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

Then open another terminal:

```bash
cd paper-trader/frontend
```

Install:

```bash
npm install
```

Run:

```bash
npm run dev
```

Open:

```text
http://localhost:5173
```

---

# 40. Recommended Git Workflow

Before making changes:

```bash
git status
```

Pull latest changes:

```bash
git pull
```

Create a branch:

```bash
git checkout -b feature/<feature-name>
```

After changes:

```bash
git status
```

Run backend tests:

```bash
cd backend
source .venv/bin/activate
pytest
```

Then:

```bash
git add .
git commit -m "Add <feature>"
git push origin feature/<feature-name>
```

---

# 41. Important Files

### Backend

```text
backend/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── pnl.py
│   ├── market.py
│   ├── instrument.py
│   └── alerts.py
│
├── tests/
├── .env
├── .env.example
└── requirements.txt
```

### Important responsibilities

```text
main.py
    FastAPI application / API routes

config.py
    Environment configuration

db.py
    Database configuration

models.py
    SQLAlchemy database models

schemas.py
    API request/response schemas

instrument.py
    Upstox instrument resolution

market.py
    Live Upstox market data / WebSocket

pnl.py
    Paper P&L calculation

alerts.py
    Telegram notifications

tests/
    Backend automated tests
```

---

# 42. P&L Calculation Function

The core P&L function is:

```python
def order_pnl(
    side: str,
    entry_price: float,
    current_ltp: float | None,
    quantity: int,
) -> float | None:
    if current_ltp is None:
        return None

    if side == "SELL":
        return round(
            (entry_price - current_ltp) * quantity,
            2,
        )

    if side == "BUY":
        return round(
            (current_ltp - entry_price) * quantity,
            2,
        )

    raise ValueError(
        f"Unsupported side: {side}"
    )
```

The strategy-level P&L aggregates all open orders.

---

# 43. Important Paper-Trading Rule

The application is currently intended for:

```text
PAPER TRADING ONLY
```

The application can:

* Resolve instruments
* Receive live market prices
* Create paper positions
* Calculate paper P&L
* Track option legs
* Send Telegram notifications

It should **not** call Upstox order-placement APIs.

Do not add real order placement unless the application's trading mode, safety controls, authentication and user confirmation flow are deliberately redesigned.

---

# 44. Troubleshooting Decision Tree

### Backend won't start

Run:

```bash
source .venv/bin/activate
which python
python --version
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

---

### `No module named sqlalchemy`

Run:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Then:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

---

### `uv_cwd` / npm EPERM

Run:

```bash
cd ~
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/frontend"
npm install
npm run dev
```

---

### Upstox SSL error

Check:

```bash
python -c "import certifi; print(certifi.where())"
```

Upgrade:

```bash
python -m pip install --upgrade certifi
```

For temporary local troubleshooting only:

```text
UPSTOX_VERIFY_SSL=false
```

Prefer installing/configuring the correct CA certificate for a permanent fix.

---

### Telegram not working

Check:

```text
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
```

Then restart backend.

Check backend logs for:

```text
[Telegram] HTTP 200
```

If Telegram returns an error, inspect the HTTP response.

---

### LTP not showing

Check:

```text
Upstox access token
        ↓
Instrument key
        ↓
WebSocket connection
        ↓
Subscription
        ↓
LTP message
        ↓
Market cache
        ↓
Frontend
```

---

# 45. Quick Start — Daily Use

For normal development, only these commands should be necessary.

### Backend

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/backend"
source .venv/bin/activate
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

Open another terminal:

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/frontend"
npm run dev
```

### Open application

```text
http://localhost:5173
```

### Check backend

```bash
curl http://127.0.0.1:8000/api/health
```

### Run tests

```bash
cd "/Users/rutvik.shah/Documents/My Scripts/Trading/paper-trader/backend"
source .venv/bin/activate
pytest
```

This is the core operational flow to keep as a quick-reference section at the top of the project README.
