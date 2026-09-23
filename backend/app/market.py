import random
import threading
import time
from typing import Callable


class MarketDataService:
    """Thread-safe live market cache backed by Upstox Market Data Feed V3."""

    def __init__(self, use_mock: bool, access_token: str, verify_ssl: bool):
        self.use_mock = use_mock
        self.access_token = access_token
        self.verify_ssl = verify_ssl
        self._ltps: dict[str, float] = {}
        self._volumes: dict[str, float] = {}
        self._lock = threading.RLock()
        self._subscribed: set[str] = set()
        self._running = False
        self._thread: threading.Thread | None = None
        self._streamer = None
        self._on_tick: Callable[[str, float], None] | None = None
        self.status = "DISCONNECTED"
        self.last_error: str | None = None

    def set_callback(self, callback: Callable[[str, float], None]) -> None:
        self._on_tick = callback

    def get_ltps(self) -> dict[str, float]:
        with self._lock:
            return dict(self._ltps)

    def get_volumes(self) -> dict[str, float]:
        with self._lock:
            return dict(self._volumes)

    def subscribed_keys(self) -> list[str]:
        with self._lock:
            return sorted(self._subscribed)

    def subscribe(self, instrument_keys: list[str]) -> None:
        keys = {k for k in instrument_keys if k}
        if not keys:
            return
        with self._lock:
            new_keys = keys - self._subscribed
            self._subscribed.update(keys)

        if self.use_mock:
            if not self._running:
                self._running = True
                self.status = "CONNECTED (MOCK)"
                self._thread = threading.Thread(target=self._mock_loop, daemon=True)
                self._thread.start()
            return

        if self._streamer is not None and self.status == "CONNECTED":
            try:
                if new_keys:
                    self._streamer.subscribe(sorted(new_keys), "full")
                return
            except Exception as exc:
                self.last_error = str(exc)
                self.status = f"ERROR: {exc}"

        if not self._running:
            self.start_upstox()

    def _emit(self, key: str, ltp: float) -> None:
        callback = self._on_tick
        if callback:
            try:
                callback(key, ltp)
            except Exception:
                pass

    def _mock_loop(self) -> None:
        while self._running:
            with self._lock:
                keys = list(self._subscribed)
                for key in keys:
                    previous = self._ltps.get(key, random.uniform(1.0, 100.0))
                    new_price = max(0.05, previous + random.uniform(-0.10, 0.10))
                    self._ltps[key] = round(new_price, 2)
                    value = self._ltps[key]
                    self._emit(key, value)
            time.sleep(1)

    def start_upstox(self) -> None:
        if not self.access_token:
            self.status = "ERROR: UPSTOX_ACCESS_TOKEN missing"
            self.last_error = self.status
            return
        if self._thread and self._thread.is_alive():
            return

        try:
            import upstox_client
        except ImportError as exc:
            self.status = "ERROR: upstox-python-sdk not installed"
            self.last_error = str(exc)
            return

        def run():
            try:
                configuration = upstox_client.Configuration()
                configuration.access_token = self.access_token
                api_client = upstox_client.ApiClient(configuration)
                streamer = upstox_client.MarketDataStreamerV3(api_client, [], "full")
                self._streamer = streamer

                def on_open(*_args):
                    with self._lock:
                        keys = sorted(self._subscribed)
                    if keys:
                        streamer.subscribe(keys, "full")
                    self.status = "CONNECTED"
                    self.last_error = None

                def on_message(message):
                    try:
                        if not isinstance(message, dict):
                            return
                        feeds = message.get("feeds", {})
                        for key, feed in feeds.items():
                            if not isinstance(feed, dict):
                                continue
                            market_ff = None
                            ff = feed.get("ff")
                            if isinstance(ff, dict):
                                market_ff = ff.get("marketFF")
                            if not isinstance(market_ff, dict):
                                full = feed.get("fullFeed")
                                if isinstance(full, dict):
                                    market_ff = full.get("marketFF")
                            if not isinstance(market_ff, dict):
                                market_ff = feed

                            ltpc = market_ff.get("ltpc") if isinstance(market_ff, dict) else None
                            if isinstance(ltpc, dict) and ltpc.get("ltp") is not None:
                                value = float(ltpc["ltp"])
                                volume = None
                                ohlc = market_ff.get("marketOHLC", {}).get("ohlc", []) if isinstance(market_ff.get("marketOHLC"), dict) else []
                                if isinstance(ohlc, list):
                                    for bar in ohlc:
                                        if isinstance(bar, dict) and bar.get("interval") == "I1" and bar.get("vol") is not None:
                                            volume = float(bar["vol"])
                                if volume is None:
                                    details = market_ff.get("eFeedDetails")
                                    if isinstance(details, dict) and details.get("vtt") is not None:
                                        volume = float(details["vtt"])
                                with self._lock:
                                    self._ltps[key] = value
                                    if volume is not None:
                                        self._volumes[key] = volume
                                self._emit(key, value)
                    except Exception as exc:
                        self.last_error = f"Malformed market-data tick: {exc}"

                def on_error(error, *_args):
                    self.last_error = str(error)
                    self.status = "ERROR: Upstox WebSocket"

                def on_close(*_args):
                    self.status = "DISCONNECTED"
                    self._running = False

                streamer.on("open", on_open)
                streamer.on("message", on_message)
                streamer.on("error", on_error)
                streamer.on("close", on_close)

                self._running = True
                self.status = "CONNECTING"
                streamer.connect()
            except Exception as exc:
                self.status = f"ERROR: {exc}"
                self.last_error = str(exc)
                self._running = False

        self._running = True
        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        try:
            if self._streamer is not None:
                self._streamer.disconnect()
        except Exception:
            pass
        self._streamer = None
        self.status = "DISCONNECTED"
