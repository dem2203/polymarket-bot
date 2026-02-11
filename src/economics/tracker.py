"""
Economics Tracker — API maliyeti vs trading geliri.
Bot kendi masrafını çıkarıyor mu takip eder.
"""

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger("bot.economics")


@dataclass
class EconomicsSnapshot:
    """Ekonomik durum anlık görüntüsü."""
    starting_balance: float
    current_balance: float
    total_api_cost: float
    total_trading_pnl: float
    net_profit: float           # trading_pnl - api_cost
    roi_pct: float
    is_self_sustaining: bool    # Net kâr > 0 mı?
    api_calls: int
    cost_per_trade: float
    runtime_hours: float


class EconomicsTracker:
    """Bot ekonomisini takip eder — kendi masrafını çıkarıyor mu?"""

    def __init__(self, starting_balance: float):
        self.starting_balance = starting_balance
        self.start_time = time.time()
        
        # Gelirler
        self.total_trading_pnl: float = 0.0
        self.total_trades: int = 0
        
        # Giderler
        self.total_api_cost: float = 0.0
        self.total_api_calls: int = 0

    def record_trade_pnl(self, pnl: float):
        """Trade kârı/zararı kaydet."""
        self.total_trading_pnl += pnl
        self.total_trades += 1

    def record_api_cost(self, cost: float, calls: int = 1):
        """API maliyeti kaydet."""
        self.total_api_cost += cost
        self.total_api_calls += calls

    @property
    def net_profit(self) -> float:
        """Net kâr = Trading PnL - API maliyeti."""
        return self.total_trading_pnl - self.total_api_cost

    @property
    def is_self_sustaining(self) -> bool:
        """Bot kendi masrafını çıkarıyor mu?"""
        return self.net_profit > 0

    @property
    def runtime_hours(self) -> float:
        """Çalışma süresi (saat)."""
        return (time.time() - self.start_time) / 3600

    def get_snapshot(self, current_balance: float) -> EconomicsSnapshot:
        """Ekonomik durum raporu."""
        net = self.net_profit
        roi = ((current_balance - self.starting_balance) / self.starting_balance * 100) if self.starting_balance > 0 else 0
        cost_per_trade = (self.total_api_cost / self.total_trades) if self.total_trades > 0 else 0

        return EconomicsSnapshot(
            starting_balance=self.starting_balance,
            current_balance=current_balance,
            total_api_cost=round(self.total_api_cost, 4),
            total_trading_pnl=round(self.total_trading_pnl, 2),
            net_profit=round(net, 2),
            roi_pct=round(roi, 2),
            is_self_sustaining=self.is_self_sustaining,
            api_calls=self.total_api_calls,
            cost_per_trade=round(cost_per_trade, 4),
            runtime_hours=round(self.runtime_hours, 1),
        )

    def format_report(self, current_balance: float) -> str:
        """Formatlanmış ekonomi raporu."""
        snap = self.get_snapshot(current_balance)
        sustain = "✅ EVET" if snap.is_self_sustaining else "❌ HAYIR"

        return (
            f"💰 BOT EKONOMİSİ RAPORU\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Başlangıç: ${snap.starting_balance:.2f}\n"
            f"Mevcut:    ${snap.current_balance:.2f}\n"
            f"ROI:       {snap.roi_pct:+.1f}%\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Trading PnL: ${snap.total_trading_pnl:+.2f}\n"
            f"API Maliyet: -${snap.total_api_cost:.4f}\n"
            f"Net Kâr:     ${snap.net_profit:+.2f}\n"
            f"━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Kendi masrafını çıkarıyor mu? {sustain}\n"
            f"API çağrı: {snap.api_calls} | Trade: {self.total_trades}\n"
            f"Çağrı başına maliyet: ${snap.cost_per_trade:.4f}\n"
            f"Çalışma süresi: {snap.runtime_hours:.1f} saat"
        )
