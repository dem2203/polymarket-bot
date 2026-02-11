"""
Mispricing Strategy — Ana strateji.
AI fair value vs market price → edge > %8 ise trade sinyali.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.config import settings
from src.ai.brain import AIBrain
from src.strategy.kelly import KellySizer

logger = logging.getLogger("bot.strategy.mispricing")


@dataclass
class TradeSignal:
    """Bir trade sinyali."""
    market_id: str
    question: str
    category: str
    direction: str         # BUY_YES veya BUY_NO
    fair_value: float      # AI hesapladı
    market_price: float    # Mevcut fiyat
    edge: float            # |fair_value - market_price|
    confidence: float      # AI güven skoru
    position_size: float   # $ cinsinden
    shares: float          # Hisse sayısı
    price: float           # Alım fiyatı
    token_side: str        # YES veya NO
    reasoning: str         # AI'ın gerekçesi
    kelly_fraction: float  # Kelly oranı
    api_cost: float = 0.0  # Bu analiz için API maliyeti
    tokens: list = field(default_factory=list)
    slug: str = ""


class MispricingStrategy:
    """AI-powered mispricing tespiti ve trade sinyali üretimi."""

    def __init__(self, brain: AIBrain, kelly: KellySizer):
        self.brain = brain
        self.kelly = kelly
        self.threshold = settings.mispricing_threshold

    async def analyze_market(self, market: dict, balance: float) -> Optional[TradeSignal]:
        """
        Tek bir marketi analiz et.
        
        1. Claude'dan fair value al
        2. Mispricing var mı kontrol et (>%8)
        3. Kelly ile pozisyon büyüklüğü hesapla
        4. TradeSignal döndür
        """
        # 1. AI Fair Value
        ai_result = await self.brain.estimate_fair_value(market)
        if not ai_result:
            return None

        fair_value = ai_result["probability"]
        confidence = ai_result["confidence"]
        reasoning = ai_result["reasoning"]
        api_cost = ai_result["api_cost"]

        # Düşük güvenli tahminleri atla
        if confidence < 0.55:
            return None

        # 2. Mispricing tespiti
        yes_price = float(market.get("yes_price", 0.5))
        mispricing = self.brain.detect_mispricing(fair_value, yes_price)

        if not mispricing["has_edge"]:
            return None

        direction = mispricing["direction"]
        edge = mispricing["edge"]

        logger.info(
            f"🎯 Mispricing bulundu: {market['question'][:50]}... "
            f"| FV={fair_value:.2f} vs Price={yes_price:.2f} "
            f"| Edge={edge:.1%} | {direction}"
        )

        # 3. Kelly Criterion
        kelly_result = self.kelly.calculate(
            fair_value=fair_value,
            market_price=yes_price,
            balance=balance,
            direction=direction,
            confidence=confidence,
        )

        if kelly_result["position_size"] < 1.0:
            logger.debug(f"Kelly too small for {market['question'][:40]}")
            return None

        # 4. Trade Signal oluştur
        return TradeSignal(
            market_id=market["id"],
            question=market["question"],
            category=market.get("category", "general"),
            direction=direction,
            fair_value=fair_value,
            market_price=yes_price,
            edge=edge,
            confidence=confidence,
            position_size=kelly_result["position_size"],
            shares=kelly_result["shares"],
            price=kelly_result["price"],
            token_side=kelly_result["token_side"],
            reasoning=reasoning,
            kelly_fraction=kelly_result["adjusted_fraction"],
            api_cost=api_cost,
            tokens=market.get("tokens", []),
            slug=market.get("slug", ""),
        )

    async def scan_for_signals(
        self, markets: list[dict], balance: float, max_signals: int = 5
    ) -> list[TradeSignal]:
        """
        Tüm marketleri tara, en iyi sinyalleri döndür.
        
        Markets zaten filtrelenmiş olmalı (hacim, likidite vs).
        """
        signals = []
        analyzed = 0

        for market in markets:
            try:
                signal = await self.analyze_market(market, balance)
                analyzed += 1

                if signal:
                    signals.append(signal)
                    logger.info(
                        f"📊 Sinyal #{len(signals)}: {signal.question[:40]}... "
                        f"| {signal.direction} @ ${signal.price:.3f} "
                        f"| Edge={signal.edge:.1%} | Size=${signal.position_size:.2f}"
                    )

                # Yeterli sinyal bulduysa dur (API maliyet optimizasyonu)
                if len(signals) >= max_signals:
                    break

            except Exception as e:
                logger.warning(f"Market analiz hatası: {e}")
                continue

        # Edge'e göre sırala (en büyük edge önce)
        signals.sort(key=lambda s: s.edge * s.confidence, reverse=True)

        logger.info(
            f"📈 {analyzed} market analiz edildi → {len(signals)} sinyal bulundu "
            f"(API maliyeti: ${self.brain.total_api_cost:.4f})"
        )

        return signals[:max_signals]
