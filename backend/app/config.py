import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}

def _origins() -> list[str]:
    value = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    return [item.strip().rstrip("/") for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    use_mock_market_data: bool = _bool("USE_MOCK_MARKET_DATA", False)
    upstox_access_token: str = os.getenv("UPSTOX_ACCESS_TOKEN", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_interval_seconds: int = max(60, int(os.getenv("TELEGRAM_INTERVAL_SECONDS", "300")))
    significant_pnl_change: float = max(0.0, float(os.getenv("SIGNIFICANT_PNL_CHANGE", "100")))
    significant_alert_cooldown_seconds: int = max(60, int(os.getenv("SIGNIFICANT_ALERT_COOLDOWN_SECONDS", "60")))
    upstox_verify_ssl: bool = _bool("UPSTOX_VERIFY_SSL", True)
    telegram_verify_ssl: bool = _bool("TELEGRAM_VERIFY_SSL", True)
    cors_origins: list[str] = field(default_factory=_origins)


settings = Settings()
