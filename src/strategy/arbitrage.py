"""
Arbitrage Strategy — Risksiz arbitraj fırsatı tespiti.
YES + NO < 0.98 ise her ikisini alarak risksiz kâr.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from src.config import settings

logger = logging.getLogger("bot.strategy.arbitrage")


@dataclass
class ArbitrageSignal:
    """Arbitraj fırsatı sinyali."""
    market_id: str
    question: str
    yes_price: float
    no_price: float
    total_price: float      # YES + NO
    profit_margin: float    # 1.0 - total_price (risksiz kâr marjı)
    position_size: float    # $ cinsinden
    tokens: list = None
    slug: str = ""


class ArbitrageStrategy:
    """YES + NO < 0.98 arbitraj tespiti."""

    def __init__(self):
        self.min_margin = 0.02  # Minimum %2 marj (masrafları karşılamak için)

    def detect(self, markets: list[dict], balance: float) -> list[ArbitrageSignal]:
        """
        Tüm marketlerde arbitraj fırsatı ara.
        YES + NO < 0.98 ise her ikisini al.
        """
        signals = []

        for market in markets:
            try:
                yes_price = float(market.get("yes_price", 0.5))
                no_price = float(market.get("no_price", 0.5))
                total = yes_price + no_price

                if total >= (1.0 - self.min_margin):
                    continue  # Marj yetersiz

                profit_margin = 1.0 - total

                # Pozisyon büyüklüğü: max %6 balance, min $2
                max_pos = balance * settings.max_kelly_fraction
                position_size = min(max_pos, balance * 0.05)  # %5 ile sınırla

                if position_size < 2.0:
                    continue

                signal = ArbitrageSignal(
                    market_id=market["id"],
                    question=market["question"],
                    yes_price=yes_price,
                    no_price=no_price,
                    total_price=total,
                    profit_margin=profit_margin,
                    position_size=round(position_size, 2),
                    tokens=market.get("tokens", []),
                    slug=market.get("slug", ""),
                )
                signals.append(signal)

                logger.info(
                    f"🔄 Arbitraj fırsatı: {market['question'][:50]}... "
                    f"| YES={yes_price:.3f} + NO={no_price:.3f} = {total:.3f} "
                    f"| Marj={profit_margin:.1%}"
                )

            except (ValueError, TypeError) as e:
                continue

        signals.sort(key=lambda s: s.profit_margin, reverse=True)
        return signals
