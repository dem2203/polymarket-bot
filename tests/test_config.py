"""Config modülü testleri."""

import os
import pytest


def test_settings_defaults():
    """Varsayılan ayarların doğru yüklendiğini kontrol et."""
    from src.config import Settings

    s = Settings(
        polymarket_private_key="test_key",
        _env_file=None,  # .env dosyasını yükleme
    )
    assert s.dry_run is True
    assert s.max_order_size == 10.0
    assert s.max_total_exposure == 100.0
    assert s.stop_loss_pct == 0.15
    assert s.take_profit_pct == 0.30
    assert s.chain_id == 137
    assert s.clob_api_url == "https://clob.polymarket.com"
    assert s.gamma_api_url == "https://gamma-api.polymarket.com"


def test_settings_has_credentials():
    """Credential kontrolü çalışıyor mu?"""
    from src.config import Settings

    s1 = Settings(polymarket_private_key="", _env_file=None)
    assert s1.has_credentials is False

    s2 = Settings(polymarket_private_key="your_private_key_here", _env_file=None)
    assert s2.has_credentials is False

    s3 = Settings(polymarket_private_key="0xabc123", _env_file=None)
    assert s3.has_credentials is True


def test_settings_has_telegram():
    """Telegram yapılandırma kontrolü."""
    from src.config import Settings

    s1 = Settings(
        polymarket_private_key="test",
        telegram_bot_token="your_telegram_bot_token",
        telegram_chat_id="123",
        _env_file=None,
    )
    assert s1.has_telegram is False

    s2 = Settings(
        polymarket_private_key="test",
        telegram_bot_token="1234:ABCdef",
        telegram_chat_id="12345",
        _env_file=None,
    )
    assert s2.has_telegram is True
