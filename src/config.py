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

    # ---- DeepSeek (Second AI) ----
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    enable_deepseek_validation: bool = True

    # ---- Self-Learning ----
    enable_self_learning: bool = True
    self_review_interval_hours: int = 12

    # ---- Github Memory (Backup) ----
    github_token: str = ""
    github_repo: str = ""

    # ---- Polymarket ----
    polymarket_private_key: str = ""
    polymarket_api_key: str = ""
    polymarket_api_secret: str = ""
    polymarket_passphrase: str = ""
    polymarket_funder_address: str = "0x04c03aac02601586cdd007f96bcfe03c3b5b12bf"  # Proxy Address (Funds here!)

    # ---- Telegram ----
    enable_telegram: bool = False
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # ---- Trading (RECOVERY MODE ACTIVATED 🦅) ----
    dry_run: bool = True
    starting_balance: float = 34.56
    max_kelly_fraction: float = 0.05      # Max %5 sermaye/trade
    kelly_multiplier: float = 0.2          # Muhafazakar Kelly
    max_daily_trades: int = 3              # Günde max 3 işlem

    # ... (Risk settings remain same) ...

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
        # MASTER SWITCH: Eğer enable_telegram False ise, token olsa bile False dön!
        return self.enable_telegram and bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def is_alive(self) -> bool:
        """Bot hayatta mı? Bakiye survival_balance'dan fazla mı?"""
        return True  # Runtime'da balance ile kontrol edilir


# Global settings instance
settings = Settings()
