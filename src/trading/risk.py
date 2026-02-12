"""
Risk Manager — Hayatta kalma + risk kontrolü.
Bakiye < $5 = DUR. Günlük kayıp limiti. Exposure limiti.
"""

import logging
import time
from typing import Optional

from src.config import settings
from src.strategy.mispricing import TradeSignal

logger = logging.getLogger("bot.risk")


class RiskManager:
    """Risk yönetimi ve hayatta kalma kontrolü."""

    def __init__(self):
        self.daily_loss = 0.0
        self.daily_trades = 0
        self._last_reset = time.time()
        self.max_daily_trades = 30       # Günlük max trade
        self.min_trade_cash = 2.0        # Minimum $2 nakit olmalı

    def _maybe_reset_daily(self):
        """24 saat geçtiyse günlük sayaçları sıfırla."""
        if time.time() - self._last_reset > 86400:
            self.daily_loss = 0.0
            self.daily_trades = 0
            self._last_reset = time.time()
            logger.info("📊 Günlük risk sayaçları sıfırlandı")

    def is_trade_allowed(
        self,
        signal: TradeSignal,
        balance: float,
        total_exposure: float,
        open_positions: int,
    ) -> tuple[bool, str]:
        """
        Trade'e izin ver veya reddet.
        Pozisyon limiti YOK — available cash'e göre karar verir.
        
        Returns:
            (allowed: bool, reason: str)
        """
        self._maybe_reset_daily()

        # 1. HAYATTA KALMA kontrolü
        if balance <= settings.survival_balance:
            return False, f"💀 HAYATTA KALMA MODU: Bakiye ${balance:.2f} < ${settings.survival_balance:.2f}"

        # 2. Günlük kayıp limiti
        if self.daily_loss >= settings.daily_loss_limit:
            return False, f"🛑 Günlük kayıp limiti: ${self.daily_loss:.2f} >= ${settings.daily_loss_limit:.2f}"

        # 3. Günlük trade limiti
        if self.daily_trades >= self.max_daily_trades:
            return False, f"⚠️ Günlük trade limiti: {self.daily_trades}/{self.max_daily_trades}"

        # 4. Yeterli nakit var mı? (Max pozisyon limiti yok!)
        available_cash = balance - total_exposure
        if available_cash < self.min_trade_cash:
            return False, f"💰 Yeterli nakit yok: Available ${available_cash:.2f} < ${self.min_trade_cash:.2f}"

        # 5. Pozisyon büyüklüğü available cash'i aşmasın
        if signal.position_size > available_cash:
            return False, f"⚠️ Pozisyon cash'ten büyük: ${signal.position_size:.2f} > available ${available_cash:.2f}"

        # Max Single Cap Calculation
        max_single = balance * settings.max_kelly_fraction

        # 5.5. Minimum Lot Kontrolü (Polymarket Min 5 Shares)
        # V3.3.7: Borsa genellikle min 5 share istiyor.
        MIN_SHARES = 5.0
        if signal.entry_price and signal.entry_price > 0:
            est_shares = signal.position_size / signal.entry_price
            if est_shares < MIN_SHARES:
                required_size = MIN_SHARES * signal.entry_price
                
                if required_size > max_single + 0.05:
                     return False, (
                        f"⚠️ Min 5 lot için bakiye yetersiz: ${required_size:.2f} > ${max_single:.2f} "
                        f"(Price: {signal.entry_price})"
                    )
                
                logger.info(f"⚖️ Min lot ayarı: {est_shares:.1f} -> 5.0 lot (${signal.position_size:.2f} -> ${required_size:.2f})")
                signal.position_size = required_size

        # 6. Tek trade'de bakiyenin max %10'unu aşma
        if signal.position_size > max_single + 0.01:  # Add $0.01 tolerance for float precision
            return False, (
                f"⚠️ Tek trade limiti: ${signal.position_size:.2f} > ${max_single:.2f} "
                f"(%{settings.max_kelly_fraction*100:.0f} bakiye)"
            )

        # 7. Minimum edge kontrolü
        if signal.edge < settings.mispricing_threshold:
            return False, f"⚠️ Edge çok düşük: {signal.edge:.1%} < {settings.mispricing_threshold:.1%}"

        # 8. Minimum güven
        if signal.confidence < 0.55:
            return False, f"⚠️ Güven çok düşük: {signal.confidence:.1%}"

        return True, "✅ Trade onaylı"

    def record_trade(self, pnl: float = 0.0):
        """Trade kaydet, günlük sayaçları güncelle."""
        self._maybe_reset_daily()
        self.daily_trades += 1
        if pnl < 0:
            self.daily_loss += abs(pnl)

    def get_risk_report(self, balance: float) -> dict:
        """Risk raporu."""
        return {
            "balance": round(balance, 2),
            "survival_mode": balance <= settings.survival_balance,
            "daily_loss": round(self.daily_loss, 2),
            "daily_loss_limit": settings.daily_loss_limit,
            "daily_trades": self.daily_trades,
            "max_daily_trades": self.max_daily_trades,
            "is_alive": balance > settings.survival_balance,
        }
