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
        self.max_daily_trades = 20       # Günlük max trade
        self.max_concurrent = 10          # Max açık pozisyon

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

        # 4. Max concurrent pozisyon
        if open_positions >= self.max_concurrent:
            return False, f"⚠️ Max açık pozisyon: {open_positions}/{self.max_concurrent}"

        # 5. Toplam exposure kontrolü
        new_exposure = total_exposure + signal.position_size
        if new_exposure > settings.max_total_exposure:
            return False, (
                f"⚠️ Exposure limiti: ${new_exposure:.2f} > ${settings.max_total_exposure:.2f}"
            )

        # 6. Tek trade'de bakiyenin max %6'sını aşma
        max_single = balance * settings.max_kelly_fraction
        if signal.position_size > max_single:
            return False, (
                f"⚠️ Tek trade limiti: ${signal.position_size:.2f} > ${max_single:.2f} "
                f"(%{settings.max_kelly_fraction*100:.0f} bakiye)"
            )

        # 7. Pozisyon büyüklüğü bakiyeyi aşmasın
        if signal.position_size > balance * 0.5:
            return False, f"⚠️ Pozisyon çok büyük: ${signal.position_size:.2f} > bakiyenin %50'si"

        # 8. Minimum edge kontrolü
        if signal.edge < settings.mispricing_threshold:
            return False, f"⚠️ Edge çok düşük: {signal.edge:.1%} < {settings.mispricing_threshold:.1%}"

        # 9. Minimum güven
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
