from datetime import date, timedelta
from typing import Any

import requests


class InstrumentResolutionError(RuntimeError):
    pass


class UpstoxInstrumentResolver:
    SEARCH_URL = "https://api.upstox.com/v2/instruments/search"
    OPTION_CONTRACT_URL = "https://api.upstox.com/v2/option/contract"

    def __init__(self, access_token: str, verify_ssl: bool = True):
        self.access_token = access_token
        self.verify_ssl = verify_ssl

    def _get(self, url: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        if not self.access_token:
            raise InstrumentResolutionError("UPSTOX_ACCESS_TOKEN is not configured")
        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self.access_token}",
        }
        try:
            response = requests.get(
                url,
                headers=headers,
                params=params,
                timeout=15,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise InstrumentResolutionError(f"Upstox request failed: {exc}") from exc
        except ValueError as exc:
            raise InstrumentResolutionError("Upstox returned invalid JSON") from exc
        return payload.get("data", [])

    def resolve_underlying(self, symbol: str) -> dict[str, Any]:
        symbol = symbol.strip().upper()
        candidates = self._get(
            self.SEARCH_URL,
            {
                "query": symbol,
                "exchanges": "NSE",
                "segments": "EQ",
                "records": 30,
                "page_number": 1,
            },
        )
        exact = [
            x for x in candidates
            if str(x.get("trading_symbol", "")).upper() == symbol
            and x.get("segment") == "NSE_EQ"
        ]
        if not exact:
            exact = [
                x for x in candidates
                if str(x.get("short_name", "")).upper() == symbol
                and x.get("segment") == "NSE_EQ"
            ]
        if not exact:
            raise InstrumentResolutionError(f"NSE equity not found: {symbol}")
        return exact[0]


    def get_historical_daily_closes(self, instrument_key: str, end_date: date | None = None, sessions: int = 3) -> list[dict[str, Any]]:
        """Return recent daily OHLC candles, newest first, for an equity instrument."""
        end = end_date or date.today()
        start = end - timedelta(days=max(7, sessions * 4))
        encoded = requests.utils.quote(instrument_key, safe="")
        url = f"https://api.upstox.com/v3/historical-candle/{encoded}/days/1/{end.isoformat()}/{start.isoformat()}"
        if not self.access_token:
            raise InstrumentResolutionError("UPSTOX_ACCESS_TOKEN is not configured")
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.access_token}"}
        try:
            response = requests.get(url, headers=headers, timeout=15, verify=self.verify_ssl)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise InstrumentResolutionError(f"Upstox historical request failed: {exc}") from exc
        except ValueError as exc:
            raise InstrumentResolutionError("Upstox returned invalid historical JSON") from exc
        candles = payload.get("data", {}).get("candles", [])
        result = []
        for candle in candles:
            if len(candle) < 5:
                continue
            result.append({
                "timestamp": candle[0],
                "open": float(candle[1]),
                "high": float(candle[2]),
                "low": float(candle[3]),
                "close": float(candle[4]),
                "volume": float(candle[5]) if len(candle) > 5 and candle[5] is not None else None,
            })
        return result
    def get_option_contracts(
        self,
        symbol: str,
        expiry: date | None = None,
    ) -> list[dict[str, Any]]:
        underlying = self.resolve_underlying(symbol)
        params = {"instrument_key": underlying["instrument_key"]}
        if expiry:
            params["expiry_date"] = expiry.isoformat()
        return self._get(self.OPTION_CONTRACT_URL, params)

    def get_expiries(self, symbol: str) -> list[str]:
        contracts = self.get_option_contracts(symbol)
        expiries = sorted(
            {
                str(x["expiry"])
                for x in contracts
                if x.get("expiry")
            }
        )
        return expiries

    def resolve_option(
        self,
        symbol: str,
        expiry: date,
        strike: float,
        option_type: str,
    ) -> dict[str, Any]:
        contracts = self.get_option_contracts(symbol, expiry)
        candidates = [
            x for x in contracts
            if str(x.get("instrument_type", "")).upper() == option_type.upper()
            and x.get("expiry") == expiry.isoformat()
            and abs(float(x.get("strike_price", -1)) - float(strike)) < 1e-9
            and str(x.get("underlying_symbol", "")).upper() == symbol.upper()
        ]
        if not candidates:
            raise InstrumentResolutionError(
                f"Option not found: {symbol} {expiry} {strike:g} {option_type}"
            )
        return candidates[0]

    def get_option_chain(
        self,
        symbol: str,
        expiry: date,
    ) -> list[dict[str, Any]]:
        return self.get_option_contracts(symbol, expiry)
