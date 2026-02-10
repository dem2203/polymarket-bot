"""
Risk Manager - Pozisyon büyüklüğü, stop-loss, take-profit, günlük limit.
Tüm trade kararlarında risk onayı gerektirir.
"""

from datetime import datetime, timedelta
from src.config import settings
from src.trading.strategy import TradingSignal
from src.trading.position_tracker import PositionTracker
from src.trading.order_manager import Order, OrderStatus
from src.utils import logger


class RiskManager:
    """Risk yönetimi - her trade'den önce onay gereklidir."""

    def __init__(self, position_tracker: PositionTracker):
        self.position_tracker = position_tracker
        self.daily_pnl: float = 0.0
        self.daily_reset_time: datetime = datetime.now()
        self.total_trades_today: int = 0
        self.max_daily_trades: int = 50  # Günlük max işlem sayısı

    def _reset_daily_if_needed(self):
        """Günlük sayaçları sıfırla (her 24 saatte)."""
        now = datetime.now()
        if now - self.daily_reset_time > timedelta(hours=24):
            logger.info(f"🔄 Günlük risk sayaçları sıfırlanıyor | Günlük PnL: ${self.daily_pnl:.2f}")
            self.daily_pnl = 0.0
            self.total_trades_today = 0
            self.daily_reset_time = now

    def approve_trade(self, signal: TradingSignal) -> tuple[bool, str, float]:
        """
        Trade sinyalini risk açısından değerlendir.
        Returns: (onay, neden, önerilen_büyüklük)
        """
        self._reset_daily_if_needed()

        # 1. Güven eşiği kontrolü
        if signal.confidence < settings.min_confidence:
            return False, f"Güven eşiği altında: {signal.confidence:.0%} < {settings.min_confidence:.0%}", 0

        # 2. Günlük kayıp limiti kontrolü
        if self.daily_pnl < -settings.daily_loss_limit:
            return False, f"Günlük kayıp limiti aşıldı: ${self.daily_pnl:.2f} < -${settings.daily_loss_limit:.2f}", 0

        # 3. Günlük işlem sayısı kontrolü
        if self.total_trades_today >= self.max_daily_trades:
            return False, f"Günlük max işlem sayısı aşıldı: {self.total_trades_today}/{self.max_daily_trades}", 0

        # 4. Toplam exposure kontrolü
        current_exposure = self.position_tracker.get_total_exposure()
        if current_exposure >= settings.max_total_exposure:
            return (
                False,
                f"Max exposure aşıldı: ${current_exposure:.2f} >= ${settings.max_total_exposure:.2f}",
                0,
            )

        # 5. Aynı market'te zaten pozisyon var mı?
        if self.position_tracker.has_position(signal.token_id):
            return False, f"Bu market'te zaten pozisyon var: {signal.token_id[:8]}...", 0

        # 6. Pozisyon büyüklüğü hesapla
        suggested_size = self._calculate_position_size(signal, current_exposure)

        if suggested_size <= 0:
            return False, "Hesaplanan pozisyon büyüklüğü 0", 0

        logger.info(
            f"✅ Risk onayı: {signal.signal_type.value} ${suggested_size:.2f} | "
            f"Güven: {signal.confidence:.0%} | Exposure: ${current_exposure + suggested_size:.2f}"
        )
        return True, "Risk kontrollerinden geçti", suggested_size

    def _calculate_position_size(self, signal: TradingSignal, current_exposure: float) -> float:
        """Kelly Criterion benzeri pozisyon büyüklüğü hesaplama."""
        # Kalan exposure kapasitesi
        remaining_capacity = settings.max_total_exposure - current_exposure

        # Güvene dayalı büyüklük (yüksek güven = daha büyük pozisyon)
        confidence_factor = signal.confidence
        base_size = settings.max_order_size * confidence_factor

        # Maksimum emir büyüklüğü
        size = min(base_size, settings.max_order_size, remaining_capacity)

        # Minimum eşik ($1)
        if size < 1.0:
            return 0

        return round(size, 2)

    def check_stop_loss(self, token_id: str, current_price: float, entry_price: float) -> bool:
        """Stop-loss tetiklendi mi?"""
        if entry_price <= 0:
            return False
        pnl_pct = (current_price - entry_price) / entry_price
        if pnl_pct < -settings.stop_loss_pct:
            logger.warning(
                f"🛑 STOP-LOSS tetiklendi: {token_id[:8]}... | "
                f"Giriş: {entry_price:.4f} → Güncel: {current_price:.4f} | "
                f"PnL: {pnl_pct:+.1%}"
            )
            return True
        return False

    def check_take_profit(self, token_id: str, current_price: float, entry_price: float) -> bool:
        """Take-profit tetiklendi mi?"""
        if entry_price <= 0:
            return False
        pnl_pct = (current_price - entry_price) / entry_price
        if pnl_pct > settings.take_profit_pct:
            logger.info(
                f"🎯 TAKE-PROFIT tetiklendi: {token_id[:8]}... | "
                f"Giriş: {entry_price:.4f} → Güncel: {current_price:.4f} | "
                f"PnL: {pnl_pct:+.1%}"
            )
            return True
        return False

    def record_trade_result(self, pnl: float):
        """Trade sonucunu kaydet."""
        self.daily_pnl += pnl
        self.total_trades_today += 1
        logger.info(
            f"📊 Trade kaydı: PnL ${pnl:+.2f} | "
            f"Günlük PnL: ${self.daily_pnl:+.2f} | "
            f"Bugünkü işlemler: {self.total_trades_today}"
        )

    def get_risk_report(self) -> dict:
        """Risk durumu raporu."""
        current_exposure = self.position_tracker.get_total_exposure()
        return {
            "daily_pnl": self.daily_pnl,
            "daily_loss_limit": settings.daily_loss_limit,
            "daily_limit_remaining": settings.daily_loss_limit + self.daily_pnl,
            "total_exposure": current_exposure,
            "max_exposure": settings.max_total_exposure,
            "exposure_remaining": settings.max_total_exposure - current_exposure,
            "trades_today": self.total_trades_today,
            "max_daily_trades": self.max_daily_trades,
            "stop_loss_pct": settings.stop_loss_pct,
            "take_profit_pct": settings.take_profit_pct,
        }
