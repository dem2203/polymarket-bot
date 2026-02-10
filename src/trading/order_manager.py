"""
Order Manager - Emir oluşturma, gönderme, iptal etme.
DRY_RUN modunda simülasyon yapılır.
"""

import uuid
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY, SELL

from src.config import settings
from src.wallet.auth import PolymarketAuth
from src.trading.strategy import TradingSignal, SignalType
from src.utils import logger


class OrderStatus(Enum):
    PENDING = "PENDING"
    PLACED = "PLACED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    SIMULATED = "SIMULATED"


@dataclass
class Order:
    """İşlem emri."""
    id: str
    token_id: str
    condition_id: str
    market_question: str
    side: str  # BUY / SELL
    price: float
    size: float  # USDC
    order_type: str  # LIMIT / MARKET (GTC/FOK)
    status: OrderStatus
    strategy_name: str
    signal_confidence: float
    reason: str
    polymarket_order_id: str = ""
    fill_price: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def __str__(self):
        emoji = "🟢" if self.side == "BUY" else "🔴"
        status_emoji = {
            OrderStatus.FILLED: "✅",
            OrderStatus.PLACED: "⏳",
            OrderStatus.SIMULATED: "🧪",
            OrderStatus.FAILED: "❌",
            OrderStatus.CANCELLED: "🚫",
        }.get(self.status, "❓")
        return (
            f"{emoji} {self.side} ${self.size:.2f} @ {self.price:.4f} "
            f"{status_emoji} {self.status.value} | {self.strategy_name}"
        )


class OrderManager:
    """Emir yönetimi - oluşturma, gönderme, iptal, takip."""

    def __init__(self, auth: PolymarketAuth):
        self.auth = auth
        self._client: ClobClient | None = None
        self.orders: list[Order] = []
        self.open_orders: dict[str, Order] = {}  # order_id -> Order

    @property
    def client(self) -> ClobClient:
        if not self._client:
            self._client = self.auth.get_authenticated_client()
        return self._client

    def execute_signal(self, signal: TradingSignal, size_usdc: float) -> Optional[Order]:
        """Trading sinyalini emire çevir ve gönder."""
        side_str = BUY if signal.signal_type == SignalType.BUY else SELL

        order = Order(
            id=str(uuid.uuid4())[:8],
            token_id=signal.token_id,
            condition_id=signal.condition_id,
            market_question=signal.market_question,
            side=side_str,
            price=signal.price,
            size=size_usdc,
            order_type="LIMIT",
            status=OrderStatus.PENDING,
            strategy_name=signal.strategy_name,
            signal_confidence=signal.confidence,
            reason=signal.reason,
        )

        if settings.dry_run:
            return self._simulate_order(order)
        else:
            return self._place_order(order)

    def _simulate_order(self, order: Order) -> Order:
        """DRY_RUN modunda emir simülasyonu."""
        order.status = OrderStatus.SIMULATED
        order.fill_price = order.price
        order.polymarket_order_id = f"SIM-{order.id}"
        self.orders.append(order)

        logger.info(
            f"🧪 [DRY RUN] Simüle Emir: {order}\n"
            f"   Market: {order.market_question[:60]}...\n"
            f"   Neden: {order.reason}"
        )
        return order

    def _place_order(self, order: Order) -> Optional[Order]:
        """Gerçek emir gönder."""
        try:
            logger.info(f"📤 Emir gönderiliyor: {order.side} ${order.size:.2f} @ {order.price:.4f}")

            # Order args oluştur
            order_args = OrderArgs(
                price=order.price,
                size=order.size,
                side=order.side,
                token_id=order.token_id,
            )

            # CLOB'a gönder
            signed_order = self.client.create_order(order_args)
            resp = self.client.post_order(signed_order, OrderType.GTC)

            if resp and resp.get("success"):
                order.status = OrderStatus.PLACED
                order.polymarket_order_id = resp.get("orderID", "")
                self.open_orders[order.polymarket_order_id] = order
                logger.info(f"✅ Emir yerleştirildi: {order.polymarket_order_id}")
            else:
                order.status = OrderStatus.FAILED
                error_msg = resp.get("errorMsg", "Unknown error") if resp else "No response"
                logger.error(f"❌ Emir başarısız: {error_msg}")

            self.orders.append(order)
            return order

        except Exception as e:
            order.status = OrderStatus.FAILED
            self.orders.append(order)
            logger.error(f"❌ Emir gönderme hatası: {e}")
            return order

    def cancel_order(self, order_id: str) -> bool:
        """Açık emri iptal et."""
        try:
            if settings.dry_run:
                logger.info(f"🧪 [DRY RUN] Emir iptal simülasyonu: {order_id}")
                if order_id in self.open_orders:
                    self.open_orders[order_id].status = OrderStatus.CANCELLED
                    del self.open_orders[order_id]
                return True

            self.client.cancel(order_id)
            if order_id in self.open_orders:
                self.open_orders[order_id].status = OrderStatus.CANCELLED
                del self.open_orders[order_id]
            logger.info(f"🚫 Emir iptal edildi: {order_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Emir iptal hatası [{order_id}]: {e}")
            return False

    def cancel_all_orders(self) -> int:
        """Tüm açık emirleri iptal et."""
        cancelled = 0
        for order_id in list(self.open_orders.keys()):
            if self.cancel_order(order_id):
                cancelled += 1
        logger.info(f"🚫 {cancelled} emir toplu iptal edildi")
        return cancelled

    def check_order_status(self, order_id: str) -> Optional[dict]:
        """Emir durumunu sorgula."""
        try:
            if settings.dry_run:
                return {"status": "SIMULATED"}
            return self.client.get_order(order_id)
        except Exception as e:
            logger.error(f"❌ Emir durum sorgulama hatası [{order_id}]: {e}")
            return None

    def get_open_orders(self) -> list[Order]:
        """Açık emirleri listele."""
        return list(self.open_orders.values())

    def get_order_history(self, limit: int = 20) -> list[Order]:
        """Emir geçmişini getir (son N emir)."""
        return self.orders[-limit:]

    def get_stats(self) -> dict:
        """Emir istatistikleri."""
        filled = [o for o in self.orders if o.status in (OrderStatus.FILLED, OrderStatus.SIMULATED)]
        failed = [o for o in self.orders if o.status == OrderStatus.FAILED]
        return {
            "total_orders": len(self.orders),
            "filled": len(filled),
            "failed": len(failed),
            "open": len(self.open_orders),
            "total_volume": sum(o.size for o in filled),
        }
