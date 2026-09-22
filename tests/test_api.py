import os
import tempfile

_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_db.close()
os.environ["PAPER_TRADER_DB_PATH"] = _db.name
os.environ["USE_MOCK_MARKET_DATA"] = "true"

from fastapi.testclient import TestClient
from backend.app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] == "mock"


def test_create_multi_leg_strategy_and_dashboard():
    payload = {
        "name": "Test INFY Strangle",
        "description": "automated test",
        "orders": [
            {"symbol": "INFY", "expiry": "2026-09-29", "strike": 960, "option_type": "PE", "side": "SELL", "entry_price": 1.05, "lots": 1},
            {"symbol": "INFY", "expiry": "2026-09-29", "strike": 1220, "option_type": "CE", "side": "SELL", "entry_price": 0.55, "lots": 1}
        ]
    }
    response = client.post("/api/strategies", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert len(body["orders"]) == 2
    assert body["orders"][0]["quantity"] == 400
    assert body["orders"][1]["quantity"] == 400
    assert body["priced_legs"] == 2
    assert body["pnl"] is not None

    response = client.get("/api/dashboard")
    assert response.status_code == 200
    dashboard = response.json()
    assert len(dashboard["strategies"]) == 1
    assert dashboard["open_orders"] == 2
    assert dashboard["total_pnl"] == dashboard["strategies"][0]["pnl"]


def test_get_and_delete_strategy():
    payload = {
        "name": "Delete Me",
        "orders": [
            {"symbol": "TCS", "expiry": "2026-09-29", "strike": 4000, "option_type": "PE", "side": "BUY", "entry_price": 10, "lots": 2}
        ]
    }
    created = client.post("/api/strategies", json=payload)
    strategy_id = created.json()["id"]
    assert client.get(f"/api/strategies/{strategy_id}").status_code == 200
    assert client.delete(f"/api/strategies/{strategy_id}").status_code == 204
    assert client.get(f"/api/strategies/{strategy_id}").status_code == 404


def test_market_status():
    response = client.get("/api/market/status")
    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "mock"
    assert "ltps" in body
