"""
Polymarket AI Trading Bot V2 — Configuration
Tüm ayarlar .env dosyasından yüklenir.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    """Bot konfigürasyonu — .env'den otomatik yüklenir."""

    # ---- AI Brain ----
    anthropic_api_key: str = ""
    ai_model: str = "claude-3-5-haiku-20241022"
    ai_max_tokens: int = 512

    # ---- Polymarket ----
    polymarket_private_key: str = ""
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_passphrase: str = ""
    polymarket_funder_address: str = ""

    # ---- Telegram ----
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ---- Trading ----
    dry_run: bool = True
    starting_balance: float = 34.56
    max_kelly_fraction: float = 0.06      # Max %6 sermaye/trade
    kelly_multiplier: float = 0.5          # Fractional Kelly

    # ---- Risk ----
    mispricing_threshold: float = 0.08     # >%8 fark = trade
    stop_loss_pct: float = 0.20
    take_profit_pct: float = 0.25
    daily_loss_limit: float = 25.0
    survival_balance: float = 5.0
    max_total_exposure: float = 100.0

    # ---- Scanning ----
    scan_interval: int = 600               # 10 dakika
    min_volume: float = 10000.0
    min_liquidity: float = 1000.0
    max_markets_per_scan: int = 1000

    # ---- Endpoints ----
    clob_api_url: str = "https://clob.polymarket.com"
    gamma_api_url: str = "https://gamma-api.polymarket.com"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @property
    def has_polymarket_key(self) -> bool:
        return bool(self.polymarket_private_key and self.polymarket_private_key != "0xYOUR_PRIVATE_KEY")

    @property
    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key and not self.anthropic_api_key.startswith("sk-ant-api03-xxxxx"))

    @property
    def has_telegram(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def is_alive(self) -> bool:
        """Bot hayatta mı? Bakiye survival_balance'dan fazla mı?"""
        return True  # Runtime'da balance ile kontrol edilir


# Global settings instance
settings = Settings()
