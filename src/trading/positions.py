"""
Position Tracker — Açık pozisyon takibi, PnL hesabı.
Hayatta kalma kontrolü.
"""

import json
import os
import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from src.config import settings
from src.trading.executor import ExecutedOrder

logger = logging.getLogger("bot.positions")
DATA_FILE = "data/positions.json"


@dataclass
class Position:
    """Açık pozisyon."""
    market_id: str
    question: str
    token_side: str      # YES veya NO
    entry_price: float
    shares: float
    cost_basis: float    # Toplam maliyet ($)
    current_price: float
    token_id: str = ""   # CLOB token ID (SELL için gerekli!)
    unrealized_pnl: float = 0.0
    pnl_pct: float = 0.0
    opened_at: float = 0.0

    def update_price(self, new_price: float):
        """Fiyat güncelle, PnL hesapla."""
        self.current_price = new_price
        current_value = self.shares * new_price
        self.unrealized_pnl = current_value - self.cost_basis
        self.pnl_pct = (self.unrealized_pnl / self.cost_basis) if self.cost_basis > 0 else 0.0


@dataclass
class ClosedPosition:
    """Kapatılmış pozisyon."""
    market_id: str
    question: str
    token_side: str
    entry_price: float
    exit_price: float
    shares: float
    realized_pnl: float
    pnl_pct: float
    hold_time: float     # Saniye


class PositionTracker:
    """Pozisyon yönetimi ve PnL takibi."""

    def __init__(self):
        self.open_positions: dict[str, Position] = {}
        self.closed_positions: list[ClosedPosition] = []
        self.total_realized_pnl: float = 0.0
        self.daily_pnl: float = 0.0
        self._last_daily_reset: float = time.time()
        
        # Başlangıçta yükle
        self.load_positions()

    def save_positions(self):
        """Pozisyonları diske kaydet."""
        try:
            data = {
                "open_positions": {
                    mid: asdict(pos) for mid, pos in self.open_positions.items()
                },
                "total_realized_pnl": self.total_realized_pnl,
                "daily_pnl": self.daily_pnl,
                "last_daily_reset": self._last_daily_reset
            }
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Pozisyon kaydetme hatası: {e}")

    def load_positions(self):
        """Pozisyonları diskten yükle."""
        if not os.path.exists(DATA_FILE):
            return

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Open positions
            for mid, pos_data in data.get("open_positions", {}).items():
                self.open_positions[mid] = Position(**pos_data)
            
            self.total_realized_pnl = data.get("total_realized_pnl", 0.0)
            self.daily_pnl = data.get("daily_pnl", 0.0)
            self._last_daily_reset = data.get("last_daily_reset", time.time())
            
            if self.open_positions:
                logger.info(f"📂 {len(self.open_positions)} açık pozisyon geri yüklendi.")
        except Exception as e:
            logger.error(f"Pozisyon yükleme hatası: {e}")

    def open_position(self, order: ExecutedOrder, token_id: str = "") -> Position:
        """Yeni pozisyon aç."""
        position = Position(
            market_id=order.market_id,
            question=order.question,
            token_side=order.token_side,
            entry_price=order.price,
            shares=order.shares,
            cost_basis=order.size,
            current_price=order.price,
            token_id=token_id,
            opened_at=time.time(),
        )

        self.open_positions[order.market_id] = position
        self.save_positions()
        
        logger.info(
            f"📂 Pozisyon açıldı: {order.token_side} {order.shares:.1f} shares "
            f"@ ${order.price:.3f} (${order.size:.2f}) | {order.question[:40]}..."
        )
        return position

    def add_remote_position(self, market_id: str, question: str, token_side: str, 
                          shares: float, entry_price: float, token_id: str):
        """API'den gelen pozisyonu ekle (Sync için)."""
        if market_id in self.open_positions:
            return  # Zaten takipte

        cost_basis = shares * entry_price
        pos = Position(
            market_id=market_id,
            question=question,
            token_side=token_side,
            entry_price=entry_price,
            shares=shares,
            cost_basis=cost_basis,
            current_price=entry_price, # Geçici
            token_id=token_id,
            opened_at=time.time() # Bilinmiyor
        )
        self.open_positions[market_id] = pos
        self.save_positions()
        logger.info(f"🔄 Senkronize edildi: {token_side} {shares:.1f} @ ${entry_price:.2f} | {question[:40]}")

    def close_position(self, market_id: str, exit_price: float) -> Optional[ClosedPosition]:
        """Pozisyon kapat, PnL hesapla."""
        position = self.open_positions.pop(market_id, None)
        if not position:
            return None

        realized_pnl = (exit_price - position.entry_price) * position.shares
        pnl_pct = (exit_price - position.entry_price) / position.entry_price if position.entry_price > 0 else 0
        hold_time = time.time() - position.opened_at

        closed = ClosedPosition(
            market_id=market_id,
            question=position.question,
            token_side=position.token_side,
            entry_price=position.entry_price,
            exit_price=exit_price,
            shares=position.shares,
            realized_pnl=realized_pnl,
            pnl_pct=pnl_pct,
            hold_time=hold_time,
        )

        self.closed_positions.append(closed)
        self.total_realized_pnl += realized_pnl
        self.daily_pnl += realized_pnl
        self.save_positions()

        emoji = "🟢" if realized_pnl >= 0 else "🔴"
        logger.info(
            f"{emoji} Pozisyon kapatıldı: ${realized_pnl:+.2f} ({pnl_pct:+.1%}) "
            f"| {position.question[:40]}..."
        )
        return closed

    def check_stop_loss_take_profit(self, market_prices: dict) -> list[dict]:
        """
        Tüm açık pozisyonlarda SL/TP kontrol et.
        market_prices: {market_id: current_yes_price}
        
        Returns: Kapatılması gereken pozisyon bilgileri listesi
        [{"market_id": ..., "token_id": ..., "shares": ..., "price": ..., "reason": ...}]
        """
        to_close = []

        for market_id, position in self.open_positions.items():
            if market_id not in market_prices:
                continue

            new_price = market_prices[market_id]
            position.update_price(new_price)

            # Stop-loss kontrolü
            if position.pnl_pct <= -settings.stop_loss_pct:
                logger.warning(
                    f"🛑 STOP-LOSS tetiklendi: {position.question[:40]}... "
                    f"| PnL={position.pnl_pct:.1%}"
                )
                to_close.append({
                    "market_id": market_id,
                    "token_id": position.token_id,
                    "shares": position.shares,
                    "price": new_price,
                    "reason": "STOP_LOSS",
                })
                continue

            # Take-profit kontrolü
            if position.pnl_pct >= settings.take_profit_pct:
                logger.info(
                    f"🎉 TAKE-PROFIT tetiklendi: {position.question[:40]}... "
                    f"| PnL={position.pnl_pct:.1%}"
                )
                to_close.append({
                    "market_id": market_id,
                    "token_id": position.token_id,
                    "shares": position.shares,
                    "price": new_price,
                    "reason": "TAKE_PROFIT",
                })

        return to_close

    @property
    def total_exposure(self) -> float:
        """Toplam açık pozisyon değeri."""
        return sum(p.cost_basis for p in self.open_positions.values())

    @property
    def is_alive(self) -> bool:
        """Bot hayatta mı?"""
        return True  # Balance check runtime'da yapılır

    def get_portfolio_summary(self, balance: float) -> dict:
        """Portfolio özeti."""
        win_count = sum(1 for c in self.closed_positions if c.realized_pnl > 0)
        total_closed = len(self.closed_positions)
        win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0

        # Daily reset (24 saat geçtiyse)
        if time.time() - self._last_daily_reset > 86400:
            self.daily_pnl = 0.0
            self._last_daily_reset = time.time()

        return {
            "balance": round(balance, 2),
            "open_positions": len(self.open_positions),
            "total_exposure": round(self.total_exposure, 2),
            "total_realized_pnl": round(self.total_realized_pnl, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "total_trades": total_closed,
            "win_rate": round(win_rate, 1),
            "unrealized_pnl": round(
                sum(p.unrealized_pnl for p in self.open_positions.values()), 2
            ),
        }

    def has_position(self, market_id: str) -> bool:
        """Bu markette açık pozisyon var mı?"""
        return market_id in self.open_positions
