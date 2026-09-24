import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

load_dotenv()


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    use_mock_market_data: bool = _bool("USE_MOCK_MARKET_DATA", False)
    upstox_access_token: str = os.getenv("UPSTOX_ACCESS_TOKEN", "")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    telegram_interval_seconds: int = max(60, int(os.getenv("TELEGRAM_INTERVAL_SECONDS", "300")))
    significant_pnl_change: float = max(0.0, float(os.getenv("SIGNIFICANT_PNL_CHANGE", "100")))
    significant_alert_cooldown_seconds: int = max(
        60, int(os.getenv("SIGNIFICANT_ALERT_COOLDOWN_SECONDS", "60"))
    )
    upstox_verify_ssl: bool = _bool("UPSTOX_VERIFY_SSL", True)
    telegram_verify_ssl: bool = _bool("TELEGRAM_VERIFY_SSL", True)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
    cors_origins: list[str] = field(default_factory=lambda: [x.strip() for x in os.getenv("CORS_ORIGINS", "*").split(",") if x.strip()] or ["*"])


settings = Settings()
