from types import SimpleNamespace

from backend.app.risk import atr_wilder, bs_price, greeks, implied_vol, risk_band, technical_metrics, calculate_strategy_risk


def test_black_scholes_round_trip_iv():
    spot, strike, t, rate, vol = 100.0, 100.0, 30 / 365, 0.06, 0.25
    premium = bs_price(spot, strike, t, rate, vol, "CE")
    iv = implied_vol(premium, spot, strike, t, rate, "CE")
    assert iv is not None
    assert abs(iv - vol) < 1e-3


def test_greeks_exist():
    g = greeks(100, 100, 30 / 365, 0.06, 0.25, "CE")
    assert g["delta"] > 0
    assert g["gamma"] > 0
    assert g["vega"] > 0


def test_risk_bands_and_technical():
    assert risk_band(10) == "NORMAL"
    assert risk_band(50) == "WARNING"
    assert risk_band(90) == "CRITICAL"
    m = technical_metrics(list(range(100, 130)))
    assert m["rsi"] == 100
    assert m["momentum_pct"] > 0


def test_strategy_risk_expected_move_and_short_distances():
    strategy = SimpleNamespace(orders=[
        SimpleNamespace(status="OPEN", current_ltp=20.0, expiry="2027-01-01",
                       strike=90.0, option_type="PE", side="SELL", lots=1, lot_size=1, id=1),
        SimpleNamespace(status="OPEN", current_ltp=20.0, expiry="2027-01-01",
                       strike=110.0, option_type="CE", side="SELL", lots=1, lot_size=1, id=2),
    ])
    result = calculate_strategy_risk(strategy, 100.0, [])
    assert result["expected_move"] is not None
    assert result["distance_to_upper_short_pct"] == 10.0
    assert result["distance_to_lower_short_pct"] == 10.0
    assert result["delta"] is not None
    assert result["gamma"] is not None
    assert result["theta"] is not None
    assert result["vega"] is not None


def test_wilder_atr_and_technical_metrics():
    closes = [100 + i for i in range(20)]
    highs = [c + 2 for c in closes]
    lows = [c - 1 for c in closes]
    atr = atr_wilder(highs, lows, closes, 14)
    assert atr is not None
    assert abs(atr - 3.0) < 1e-9
    metrics = technical_metrics(closes, [100] * len(closes), highs, lows)
    assert metrics["atr"] == atr
    assert metrics["atr_pct"] > 0


def test_threat_range_helpers_are_derived_from_expected_move():
    from backend.app.main import _threat_states
    strategy = SimpleNamespace(orders=[
        SimpleNamespace(status="OPEN", side="SELL", option_type="CE", strike=110.0),
        SimpleNamespace(status="OPEN", side="SELL", option_type="PE", strike=90.0),
    ])
    assert _threat_states(strategy, {"spot": 109.0, "expected_move": 2.0}) == (False, False, False, False)
    assert _threat_states(strategy, {"spot": 108.5, "expected_move": 2.0}) == (True, False, False, False)
    assert _threat_states(strategy, {"spot": 110.0, "expected_move": 2.0}) == (True, False, True, False)


def test_settings_exposes_cors_origins(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://example.vercel.app, http://localhost:5173")
    from backend.app.config import Settings
    settings = Settings()
    assert settings.cors_origins == ["https://example.vercel.app", "http://localhost:5173"]


def test_application_import_smoke():
    from backend.app.main import app
    assert app.title == "Paper Trader"
