"""
Position Tracker - Aktif pozisyonları, PnL ve portfolio takibi.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from src.trading.order_manager import Order, OrderStatus
from src.utils import logger


@dataclass
class Position:
    """Açık pozisyon."""
    id: str
    token_id: str
    condition_id: str
    market_question: str
    side: str  # YES / NO
    entry_price: float
    current_price: float
    size_usdc: float  # Toplam yatırım
    quantity: float  # Token miktarı
    strategy_name: str
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    is_open: bool = True
    opened_at: datetime = field(default_factory=datetime.now)
    closed_at: Optional[datetime] = None

    @property
    def pnl_pct(self) -> float:
        """PnL yüzdesi."""
        if self.entry_price <= 0:
            return 0
        return (self.current_price - self.entry_price) / self.entry_price

    def update_price(self, new_price: float):
        """Güncel fiyatı güncelle ve PnL'i hesapla."""
        self.current_price = new_price
        self.unrealized_pnl = (new_price - self.entry_price) * self.quantity

    def close(self, exit_price: float):
        """Pozisyonu kapat."""
        self.current_price = exit_price
        self.realized_pnl = (exit_price - self.entry_price) * self.quantity
        self.unrealized_pnl = 0
        self.is_open = False
        self.closed_at = datetime.now()

    def __str__(self):
        pnl_emoji = "🟢" if self.unrealized_pnl >= 0 else "🔴"
        return (
            f"{'📈' if self.is_open else '📉'} {self.side} {self.market_question[:40]}... | "
            f"Giriş: {self.entry_price:.4f} Güncel: {self.current_price:.4f} | "
            f"{pnl_emoji} PnL: ${self.unrealized_pnl:.2f} ({self.pnl_pct:+.1%})"
        )


class PositionTracker:
    """Pozisyon takip ve portfolio yönetimi."""

    def __init__(self):
        self.positions: list[Position] = []
        self.open_positions: dict[str, Position] = {}  # token_id -> Position

    def open_position(self, order: Order) -> Position:
        """Yeni pozisyon aç (filled order'dan)."""
        fill_price = order.fill_price if order.fill_price > 0 else order.price
        quantity = order.size / fill_price if fill_price > 0 else 0

        pos = Position(
            id=order.id,
            token_id=order.token_id,
            condition_id=order.condition_id,
            market_question=order.market_question,
            side=order.side,
            entry_price=fill_price,
            current_price=fill_price,
            size_usdc=order.size,
            quantity=quantity,
            strategy_name=order.strategy_name,
        )

        self.positions.append(pos)
        self.open_positions[order.token_id] = pos
        logger.info(f"📊 Pozisyon açıldı: {pos}")
        return pos

    def close_position(self, token_id: str, exit_price: float) -> Optional[Position]:
        """Pozisyonu kapat."""
        pos = self.open_positions.get(token_id)
        if not pos:
            logger.warning(f"⚠️ Kapatılacak pozisyon bulunamadı: {token_id[:8]}...")
            return None

        pos.close(exit_price)
        del self.open_positions[token_id]
        logger.info(f"📊 Pozisyon kapatıldı: {pos} | Realized PnL: ${pos.realized_pnl:.2f}")
        return pos

    def update_prices(self, price_map: dict[str, float]):
        """Tüm açık pozisyonların fiyatlarını güncelle."""
        for token_id, pos in self.open_positions.items():
            if token_id in price_map:
                pos.update_price(price_map[token_id])

    def has_position(self, token_id: str) -> bool:
        """Bu token'da açık pozisyon var mı?"""
        return token_id in self.open_positions

    def get_open_positions(self) -> list[Position]:
        """Açık pozisyonları listele."""
        return list(self.open_positions.values())

    def get_portfolio_summary(self) -> dict:
        """Portfolio özeti."""
        open_pos = self.get_open_positions()
        closed_pos = [p for p in self.positions if not p.is_open]

        total_invested = sum(p.size_usdc for p in open_pos)
        total_unrealized_pnl = sum(p.unrealized_pnl for p in open_pos)
        total_realized_pnl = sum(p.realized_pnl for p in closed_pos)

        # Win rate
        winning = [p for p in closed_pos if p.realized_pnl > 0]
        win_rate = len(winning) / len(closed_pos) if closed_pos else 0

        summary = {
            "open_positions": len(open_pos),
            "closed_positions": len(closed_pos),
            "total_invested": total_invested,
            "unrealized_pnl": total_unrealized_pnl,
            "realized_pnl": total_realized_pnl,
            "total_pnl": total_unrealized_pnl + total_realized_pnl,
            "win_rate": win_rate,
            "positions": [str(p) for p in open_pos],
        }

        logger.info(
            f"📋 Portfolio Özeti:\n"
            f"   Açık: {len(open_pos)} | Kapalı: {len(closed_pos)}\n"
            f"   Yatırım: ${total_invested:.2f}\n"
            f"   Unrealized PnL: ${total_unrealized_pnl:.2f}\n"
            f"   Realized PnL: ${total_realized_pnl:.2f}\n"
            f"   Win Rate: {win_rate:.0%}"
        )
        return summary

    def get_total_exposure(self) -> float:
        """Toplam açık pozisyon büyüklüğü (USDC)."""
        return sum(p.size_usdc for p in self.open_positions.values())
