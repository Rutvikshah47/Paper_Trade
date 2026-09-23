from types import SimpleNamespace

from backend.app.risk import bs_price, greeks, implied_vol, risk_band, technical_metrics, calculate_strategy_risk


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
