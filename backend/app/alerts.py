import threading
import time
from datetime import datetime

import requests

from .db import SessionLocal
from .models import Strategy
from .pnl import order_pnl, strategy_pnl


class AlertService:
    def __init__(self, settings, market):
        self.settings = settings
        self.market = market

        self.configured = bool(
            settings.telegram_bot_token
            and settings.telegram_chat_id
        )

        self._running = False
        self._thread = None
        self._lock = threading.RLock()

        # Portfolio P&L at the last successful Telegram notification.
        self._last_sent_pnl = None

        # Last time a significant P&L alert was sent.
        self._last_significant_at = 0.0

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        if not self.configured:
            print(
                "[Telegram] Alert service not started: "
                "Telegram is not configured"
            )
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

        print("[Telegram] Alert service stopped")

    # ------------------------------------------------------------------
    # Telegram
    # ------------------------------------------------------------------

    def _send(self, text: str) -> bool:
        """
        Send a Telegram message.
        """

        url = (
            "https://api.telegram.org/"
            f"bot{self.settings.telegram_bot_token}/sendMessage"
        )

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

            print(
                f"[Telegram] HTTP {response.status_code}: "
                f"{response.text}"
            )

            response.raise_for_status()

            return True

        except Exception as exc:
            print(f"[Telegram] Send failed: {exc}")
            return False

    # ------------------------------------------------------------------
    # Portfolio snapshot
    # ------------------------------------------------------------------

    def _snapshot(self):
        """
        Build the current paper-trading portfolio snapshot.

        Returns:

            total_pnl,
            strategy_rows
        """

        db = SessionLocal()

        try:
            strategies = db.query(Strategy).all()

            # Get latest live LTP values from the market-data service.
            ltps = self.market.get_ltps()

            total_pnl = 0.0
            strategy_rows = []

            for strategy in strategies:

                # Only include open paper orders.
                open_orders = [
                    order
                    for order in strategy.orders
                    if getattr(order, "status", "OPEN") == "OPEN"
                ]

                if not open_orders:
                    continue

                # Strategy-level P&L.
                strategy_total = strategy_pnl(
                    open_orders,
                    ltps,
                )

                total_pnl += strategy_total

                order_rows = []

                # Order-level P&L.
                for order in open_orders:

                    current_ltp = ltps.get(
                        order.instrument_key,
                        order.current_ltp,
                    )

                    # If live LTP is not available yet,
                    # use entry price so initial P&L is zero.
                    if current_ltp is None:
                        current_ltp = order.entry_price

                    quantity = (
                        order.lots * order.lot_size
                    )

                    pnl = order_pnl(
                        order.side,
                        order.entry_price,
                        current_ltp,
                        quantity,
                    )

                    order_rows.append(
                        {
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
                        }
                    )

                strategy_rows.append(
                    {
                        "name": strategy.name,
                        "pnl": strategy_total,
                        "orders": order_rows,
                    }
                )

            return round(total_pnl, 2), strategy_rows

        finally:
            db.close()

    # ------------------------------------------------------------------
    # Formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _format_money(value):
        return f"₹{value:.2f}"

    @staticmethod
    def _format_pnl(value):
        return f"₹{value:+.2f}"

    def _format_option_update(
        self,
        total_pnl,
        strategy_rows,
        alert=False,
        pnl_change=None,
    ):
        """
        Format the Telegram notification.

        Normal:

        📊 OPTION P&L UPDATE

        Updated: ...

        INFY 960 PE
        Expiry: ...
        SELL ₹1.05 → ₹0.80
        Qty: 400
        P&L: +₹100.00

        ----------------------------
        TOTAL P&L: +₹100.00
        """

        if alert:
            lines = [
                "🚨 OPTION P&L ALERT",
                "",
            ]

            if pnl_change is not None:
                lines.extend(
                    [
                        (
                            "Change since last notification: "
                            f"{self._format_pnl(pnl_change)}"
                        ),
                        "",
                    ]
                )

        else:
            lines = [
                "📊 OPTION P&L UPDATE",
                "",
            ]

        updated = datetime.now().strftime(
            "%d-%b-%Y %I:%M:%S %p"
        )

        lines.extend(
            [
                f"Updated: {updated}",
                "",
            ]
        )

        for strategy in strategy_rows:

            for order in strategy["orders"]:

                option_name = (
                    f"{order['symbol']} "
                    f"{order['strike']:g} "
                    f"{order['option_type']}"
                )

                lines.extend(
                    [
                        option_name,
                        f"Expiry: {order['expiry']}",
                        (
                            f"{order['side']} "
                            f"{self._format_money(order['entry_price'])}"
                            " → "
                            f"{self._format_money(order['current_ltp'])}"
                        ),
                        f"Qty: {order['quantity']}",
                        f"P&L: {self._format_pnl(order['pnl'])}",
                        "",
                    ]
                )

        lines.extend(
            [
                "----------------------------",
                f"TOTAL P&L: {self._format_pnl(total_pnl)}",
            ]
        )

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Periodic notification
    # ------------------------------------------------------------------

    def _send_periodic_update(self):
        """
        Send the regular portfolio update.
        """

        total_pnl, strategy_rows = self._snapshot()

        message = self._format_option_update(
            total_pnl,
            strategy_rows,
            alert=False,
        )

        if self._send(message):

            with self._lock:
                self._last_sent_pnl = total_pnl

            print(
                "[Telegram] Periodic P&L update sent: "
                f"₹{total_pnl:+.2f}"
            )

            return True

        return False

    # ------------------------------------------------------------------
    # Significant P&L alert
    # ------------------------------------------------------------------

    def _check_significant_change(
        self,
        total_pnl,
        strategy_rows,
    ):
        """
        Send an alert when portfolio P&L changes by the configured
        threshold since the last successful Telegram notification.

        Example:

            SIGNIFICANT_PNL_CHANGE=100

        If P&L moves from +₹50 to +₹160:

            Change = +₹110

        An alert is sent.
        """

        now = time.monotonic()

        with self._lock:
            baseline = self._last_sent_pnl
            last_alert = self._last_significant_at

        # We need a previous notification as the baseline.
        if baseline is None:
            return

        pnl_change = total_pnl - baseline

        threshold = self.settings.significant_pnl_change

        cooldown = (
            self.settings.significant_alert_cooldown_seconds
        )

        # Threshold not reached.
        if abs(pnl_change) < threshold:
            return

        # Prevent alert spam.
        if now - last_alert < cooldown:
            return

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

            print(
                "[Telegram] Significant P&L alert sent: "
                f"change ₹{pnl_change:+.2f}"
            )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _loop(self):
        """
        Telegram notification loop.

        First notification:
            Immediately

        Subsequent notifications:
            Every TELEGRAM_INTERVAL_SECONDS

        Significant P&L:
            Checked during each market/notification cycle.
        """

        # --------------------------------------------------------------
        # Send first notification immediately.
        # --------------------------------------------------------------

        try:
            self._send_periodic_update()

        except Exception as exc:
            print(
                "[Telegram] Initial snapshot failed: "
                f"{exc}"
            )

        # --------------------------------------------------------------
        # Periodic loop.
        # --------------------------------------------------------------

        while self._running:

            interval = max(
                60,
                self.settings.telegram_interval_seconds,
            )

            # Sleep in 1-second increments so shutdown is responsive.
            for _ in range(interval):

                if not self._running:
                    return

                time.sleep(1)

            if not self._running:
                return

            # ----------------------------------------------------------
            # Get latest portfolio.
            # ----------------------------------------------------------

            try:
                total_pnl, strategy_rows = self._snapshot()

            except Exception as exc:
                print(
                    "[Telegram] Snapshot failed: "
                    f"{exc}"
                )
                continue

            # ----------------------------------------------------------
            # Check significant movement BEFORE periodic notification.
            # ----------------------------------------------------------

            try:
                self._check_significant_change(
                    total_pnl,
                    strategy_rows,
                )

            except Exception as exc:
                print(
                    "[Telegram] Significant P&L check failed: "
                    f"{exc}"
                )

            # ----------------------------------------------------------
            # Send normal 5-minute update.
            # ----------------------------------------------------------

            try:
                message = self._format_option_update(
                    total_pnl,
                    strategy_rows,
                    alert=False,
                )

                if self._send(message):

                    with self._lock:
                        self._last_sent_pnl = total_pnl

                    print(
                        "[Telegram] Periodic P&L update sent: "
                        f"₹{total_pnl:+.2f}"
                    )

            except Exception as exc:
                print(
                    "[Telegram] Periodic notification failed: "
                    f"{exc}"
                )