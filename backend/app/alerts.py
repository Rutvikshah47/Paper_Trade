import threading
import time
from datetime import datetime

import requests

from .db import SessionLocal
from .models import PaperOrder, Strategy
from .pnl import order_pnl


class AlertService:
    """Telegram notifications and live significant-P&L monitoring."""

    def __init__(self, settings, market):
        self.settings = settings
        self.market = market
        self.configured = bool(settings.telegram_bot_token and settings.telegram_chat_id)
        self._running = False
        self._thread = None
        self._lock = threading.RLock()
        self._last_sent_pnl = None
        self._last_significant_at = 0.0

    def start(self):
        if not self.configured:
            print("[Telegram] Alert service not started: Telegram is not configured")
            return
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._loop,
            daemon=True,
            name="telegram-alert-service",
        )
        self._thread.start()
        print("[Telegram] Alert service started")

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)
        self._thread = None
        print("[Telegram] Alert service stopped")

    def on_market_tick(self, _instrument_key: str, _ltp: float) -> None:
        """Called by MarketDataService for every live/mock LTP update."""
        if not self._running or not self.configured:
            return
        try:
            total_pnl, strategy_rows = self._snapshot()
            self._check_significant_change(total_pnl, strategy_rows)
        except Exception as exc:
            print(f"[Telegram] Live P&L check failed: {exc}")

    def _send(self, text: str) -> bool:
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        try:
            response = requests.post(
                url,
                data={
                    "chat_id": self.settings.telegram_chat_id,
                    "text": text,
                },
                timeout=15,
                verify=self.settings.telegram_verify_ssl,
            )
            print(f"[Telegram] HTTP {response.status_code}: {response.text}")
            response.raise_for_status()
            return True
        except Exception as exc:
            print(f"[Telegram] Send failed: {exc}")
            return False

    def _wait_for_market_data(self, timeout: int = 30) -> bool:
        start = time.monotonic()
        while self._running:
            db = SessionLocal()
            try:
                keys = [
                    row[0]
                    for row in db.query(PaperOrder.instrument_key)
                    .filter(PaperOrder.status == "OPEN")
                    .distinct()
                    .all()
                ]
            finally:
                db.close()

            if not keys:
                return True

            ltps = self.market.get_ltps()
            if all(key in ltps for key in keys):
                print(f"[Telegram] Live market data ready: {len(keys)} instrument(s)")
                return True

            if time.monotonic() - start >= timeout:
                print(f"[Telegram] Timed out waiting for live market data. Available LTPs: {ltps}")
                return False
            time.sleep(1)
        return False

    def _snapshot(self):
        db = SessionLocal()
        try:
            strategies = db.query(Strategy).all()
            ltps = self.market.get_ltps()
            total_pnl = 0.0
            strategy_rows = []

            for strategy in strategies:
                open_orders = [
                    order for order in strategy.orders
                    if getattr(order, "status", "OPEN") == "OPEN"
                ]
                if not open_orders:
                    continue

                strategy_total = 0.0
                order_rows = []
                for order in open_orders:
                    current_ltp = ltps.get(order.instrument_key)
                    quantity = order.lots * order.lot_size
                    pnl = None
                    if current_ltp is not None:
                        pnl = order_pnl(order.side, order.entry_price, current_ltp, quantity)
                        if pnl is not None:
                            strategy_total += pnl

                    order_rows.append({
                        "symbol": order.symbol,
                        "trading_symbol": order.trading_symbol,
                        "expiry": order.expiry,
                        "strike": order.strike,
                        "option_type": order.option_type,
                        "side": order.side,
                        "entry_price": order.entry_price,
                        "current_ltp": current_ltp,
                        "quantity": quantity,
                        "pnl": pnl,
                    })

                total_pnl += strategy_total
                strategy_rows.append({
                    "name": strategy.name,
                    "pnl": strategy_total,
                    "orders": order_rows,
                })

            return round(total_pnl, 2), strategy_rows
        finally:
            db.close()

    @staticmethod
    def _format_money(value):
        if value is None:
            return "N/A"
        return f"₹{value:.2f}"

    @staticmethod
    def _format_pnl(value):
        if value is None:
            return "N/A"
        return f"₹{value:+.2f}"

    def _format_option_update(self, total_pnl, strategy_rows, alert=False, pnl_change=None):
        if alert:
            lines = ["🚨 OPTION P&L ALERT", ""]
            if pnl_change is not None:
                lines.extend([
                    f"Change since last notification: {self._format_pnl(pnl_change)}",
                    "",
                ])
        else:
            lines = ["📊 OPTION P&L UPDATE", ""]

        updated = datetime.now().strftime("%d-%b-%Y %I:%M:%S %p")
        lines.extend([f"Updated: {updated}", ""])

        for strategy in strategy_rows:
            for order in strategy["orders"]:
                option_name = f"{order['symbol']} {order['strike']:g} {order['option_type']}"
                lines.extend([
                    option_name,
                    f"Expiry: {order['expiry']}",
                    f"{order['side']} {self._format_money(order['entry_price'])} → {self._format_money(order['current_ltp'])}",
                    f"Qty: {order['quantity']}",
                    f"P&L: {self._format_pnl(order['pnl'])}",
                    "",
                ])

        lines.extend([
            "----------------------------",
            f"TOTAL P&L: {self._format_pnl(total_pnl)}",
        ])
        return "\n".join(lines)

    def _send_periodic_update(self):
        total_pnl, strategy_rows = self._snapshot()
        message = self._format_option_update(total_pnl, strategy_rows, alert=False)
        if self._send(message):
            with self._lock:
                self._last_sent_pnl = total_pnl
            print(f"[Telegram] Periodic P&L update sent: ₹{total_pnl:+.2f}")
            return True
        return False

    def _check_significant_change(self, total_pnl, strategy_rows):
        now = time.monotonic()
        with self._lock:
            baseline = self._last_sent_pnl
            last_alert = self._last_significant_at

        if baseline is None:
            return False

        pnl_change = total_pnl - baseline
        threshold = self.settings.significant_pnl_change
        cooldown = self.settings.significant_alert_cooldown_seconds

        if abs(pnl_change) < threshold:
            return False
        if now - last_alert < cooldown:
            return False

        message = self._format_option_update(
            total_pnl,
            strategy_rows,
            alert=True,
            pnl_change=pnl_change,
        )
        if self._send(message):
            with self._lock:
                self._last_significant_at = now
                self._last_sent_pnl = total_pnl
            print(f"[Telegram] Significant P&L alert sent: change ₹{pnl_change:+.2f}")
            return True
        return False

    def _loop(self):
        try:
            if self._wait_for_market_data(timeout=30):
                self._send_periodic_update()
            else:
                print("[Telegram] Initial notification skipped because live market data was not ready")
        except Exception as exc:
            print(f"[Telegram] Initial snapshot failed: {exc}")

        while self._running:
            interval = max(60, self.settings.telegram_interval_seconds)
            for _ in range(interval):
                if not self._running:
                    return
                time.sleep(1)
            if not self._running:
                return

            try:
                self._send_periodic_update()
            except Exception as exc:
                print(f"[Telegram] Periodic notification failed: {exc}")
