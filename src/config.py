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

    # ---- Sniper Mode (V4.4) ----
    sniper_mode: bool = True               # Nokta atışı modu aktif mi?
    sniper_multiplier: float = 0.5         # Sniper sinyaline basılacak Kelly (0.5x)


    # ---- Risk ----
    mispricing_threshold: float = 0.08     # >%8 fark = trade (Sadece çok net fırsatlar)
    stop_loss_pct: float = 0.10            # %10 Stop Loss (Sıkı)
    take_profit_pct: float = 0.30          # %30 Take Profit (Hızlı kâr al)
    max_days_to_expiry: int = 45           # V vadeyi kısalttık (Dead money yok)
    stagnation_days: int = 3               # 3 gün hareket etmeyenle vedalaş
    stagnation_threshold: float = 0.02     
    daily_loss_limit: float = 5.0          # Günlük max $5 kayıp
    survival_balance: float = 5.0
    
    max_total_exposure: float = 80.0       # %80 Exposure (Nakit tut)

    # ---- Scanning ----
    scan_interval: int = 600               # 10 dakikada bir tara (Sakinleş)
    min_volume: float = 50000.0            # Sadece çok likit marketler
    min_liquidity: float = 5000.0
    max_markets_per_scan: int = 500

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
