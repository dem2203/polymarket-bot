"""
Kelly Criterion — Pozisyon büyüklüğü hesaplayıcı.
f* = (b*p - q) / b
Max %6 sermaye, Fractional Kelly (%50) ile.
"""

import logging
from src.config import settings

logger = logging.getLogger("bot.kelly")


class KellySizer:
    """Kelly Criterion tabanlı pozisyon büyüklüğü hesaplayıcı."""

    def __init__(self):
        self.max_fraction = settings.max_kelly_fraction    # Max %6
        self.multiplier = settings.kelly_multiplier         # Fractional Kelly (%50)

    def calculate(
        self,
        fair_value: float,
        market_price: float,
        balance: float,
        direction: str,
        confidence: float = 0.7,
    ) -> dict:
        """
        Kelly criterion ile optimal pozisyon büyüklüğü hesapla.
        
        Args:
            fair_value: AI'ın hesapladığı olasılık (0-1)
            market_price: Mevcut market fiyatı (0-1)
            balance: Toplam bakiye ($)
            direction: "BUY_YES" veya "BUY_NO"
            confidence: AI'ın güven skoru (0-1)
            
        Returns:
            {
                "position_size": float ($),
                "shares": float,
                "kelly_fraction": float,
                "adjusted_fraction": float,
                "price": float,
                "side": str,
            }
        """
        if direction == "BUY_YES":
            p = fair_value            # Kazanma olasılığı
            price = market_price      # Share fiyatı
        else:  # BUY_NO
            p = 1.0 - fair_value      # NO kazanma olasılığı
            price = 1.0 - market_price  # NO share fiyatı

        q = 1.0 - p  # Kaybetme olasılığı

        # Odds: net kazanç per $1 yatırım
        # Share $price'a alınır, YES kazanırsa $1 olur
        # Net kazanç = (1 - price) / price
        if price <= 0.01 or price >= 0.99:
            return self._zero_result(price, direction)

        b = (1.0 - price) / price  # Net odds

        # Kelly formülü: f* = (b*p - q) / b
        kelly_raw = (b * p - q) / b

        if kelly_raw <= 0:
            # Edge yok veya negatif — trade yapma
            return self._zero_result(price, direction)

        # Confidence ile ağırlıkla
        kelly_adjusted = kelly_raw * confidence

        # Fractional Kelly uygula (daha muhafazakâr)
        kelly_fraction = kelly_adjusted * self.multiplier

        # Max fraction cap uygula
        kelly_fraction = min(kelly_fraction, self.max_fraction)

        # Pozisyon büyüklüğü ($)
        position_size = balance * kelly_fraction

        # Minimum $1, maximum kontrol
        if position_size < 1.0:
            position_size = 0.0  # Çok küçük — trade yapma

        # Share sayısı
        shares = position_size / price if price > 0 else 0

        logger.info(
            f"Kelly: raw={kelly_raw:.4f}, adj={kelly_fraction:.4f}, "
            f"size=${position_size:.2f}, shares={shares:.1f} @ ${price:.3f}"
        )

        return {
            "position_size": round(position_size, 2),
            "shares": round(shares, 1),
            "kelly_fraction": round(kelly_raw, 4),
            "adjusted_fraction": round(kelly_fraction, 4),
            "price": price,
            "side": "BUY" if direction in ("BUY_YES", "BUY_NO") else "SELL",
            "token_side": "YES" if direction == "BUY_YES" else "NO",
        }

    def _zero_result(self, price: float, direction: str) -> dict:
        return {
            "position_size": 0.0,
            "shares": 0.0,
            "kelly_fraction": 0.0,
            "adjusted_fraction": 0.0,
            "price": price,
            "side": "NONE",
            "token_side": "YES" if direction == "BUY_YES" else "NO",
        }
