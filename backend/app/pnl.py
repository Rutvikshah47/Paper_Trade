def order_pnl(
    side: str,
    entry_price: float,
    current_ltp: float | None,
    quantity: int,
) -> float | None:
    if current_ltp is None:
        return None
    if side == "SELL":
        return round((entry_price - current_ltp) * quantity, 2)
    if side == "BUY":
        return round((current_ltp - entry_price) * quantity, 2)
    raise ValueError(f"Unsupported side: {side}")


def strategy_pnl(orders, ltps: dict[str, float]) -> float:
    total = 0.0
    for order in orders:
        ltp = ltps.get(order.instrument_key, order.current_ltp)
        value = order_pnl(
            order.side,
            order.entry_price,
            ltp,
            order.lots * order.lot_size,
        )
        if value is not None:
            total += value
    return round(total, 2)
