from backend.app.pnl import order_pnl


def test_sell_profit():
    assert order_pnl("SELL", 1.05, 0.72, 400) == 132.0


def test_sell_loss():
    assert order_pnl("SELL", 1.05, 1.25, 400) == -80.0


def test_buy_profit():
    assert order_pnl("BUY", 10.0, 12.5, 100) == 250.0


def test_unknown_ltp():
    assert order_pnl("SELL", 10.0, None, 100) is None
