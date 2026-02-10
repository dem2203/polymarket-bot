"""
Polymarket Bot Configuration
Tüm ayarlar .env dosyasından yüklenir.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Bot konfigürasyonu - .env dosyasından otomatik yüklenir."""

    # --- Polymarket Wallet ---
    polymarket_private_key: str = Field(default="", description="Polymarket wallet private key")
    polymarket_api_key: str = Field(default="", description="CLOB API key (auto-derived)")
    polymarket_api_secret: str = Field(default="", description="CLOB API secret (auto-derived)")
    polymarket_passphrase: str = Field(default="", description="CLOB API passphrase (auto-derived)")
    polymarket_funder_address: str = Field(default="", description="Funder address for proxy wallets")
    polymarket_signature_type: int = Field(default=0, description="0=EOA, 1=Magic, 2=GnosisSafe")

    # --- Telegram ---
    telegram_bot_token: str = Field(default="", description="Telegram bot token")
    telegram_chat_id: str = Field(default="", description="Telegram chat ID")

    # --- Trading Parameters ---
    dry_run: bool = Field(default=True, description="True = no real orders")
    max_order_size: float = Field(default=10.0, description="Max single order size in USDC")
    max_total_exposure: float = Field(default=100.0, description="Max total portfolio exposure in USDC")
    stop_loss_pct: float = Field(default=0.15, description="Stop-loss percentage")
    take_profit_pct: float = Field(default=0.30, description="Take-profit percentage")
    daily_loss_limit: float = Field(default=50.0, description="Max daily loss in USDC")
    min_liquidity: float = Field(default=1000.0, description="Min market liquidity to trade")
    scan_interval: int = Field(default=60, description="Market scan interval in seconds")
    min_confidence: float = Field(default=0.65, description="Min strategy confidence to trade")

    # --- API Endpoints ---
    clob_api_url: str = Field(default="https://clob.polymarket.com", description="CLOB API URL")
    gamma_api_url: str = Field(default="https://gamma-api.polymarket.com", description="Gamma API URL")

    # --- Polygon ---
    chain_id: int = Field(default=137, description="Polygon Mainnet chain ID")

    # --- Logging ---
    log_level: str = Field(default="INFO", description="Logging level")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }

    @property
    def has_credentials(self) -> bool:
        """Private key mevcut mu kontrol et."""
        return bool(self.polymarket_private_key and self.polymarket_private_key != "your_private_key_here")

    @property
    def has_api_creds(self) -> bool:
        """API credential'ları mevcut mu kontrol et."""
        return bool(self.polymarket_api_key and self.polymarket_api_secret and self.polymarket_passphrase)

    @property
    def has_telegram(self) -> bool:
        """Telegram yapılandırılmış mı kontrol et."""
        return bool(
            self.telegram_bot_token
            and self.telegram_chat_id
            and self.telegram_bot_token != "your_telegram_bot_token"
        )


# Singleton instance
settings = Settings()
