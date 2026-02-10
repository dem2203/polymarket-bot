"""
Trading Stratejileri - Momentum, Value, Arbitrage.
Her strateji market verilerini analiz eder ve sinyal üretir.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime
from src.utils import logger


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class Side(Enum):
    YES = "YES"
    NO = "NO"


@dataclass
class TradingSignal:
    """Strateji tarafından üretilen trade sinyali."""
    signal_type: SignalType
    side: Side  # YES veya NO token
    token_id: str
    condition_id: str
    market_question: str
    price: float
    confidence: float  # 0-1 arası
    strategy_name: str
    reason: str
    suggested_size: float = 0.0  # USDC
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self):
        emoji = "🟢" if self.signal_type == SignalType.BUY else "🔴" if self.signal_type == SignalType.SELL else "⚪"
        return (
            f"{emoji} {self.signal_type.value} {self.side.value} @ {self.price:.4f} "
            f"| Güven: {self.confidence:.0%} | {self.strategy_name}"
        )


class BaseStrategy(ABC):
    """Tüm stratejiler için temel sınıf."""

    name: str = "BaseStrategy"

    @abstractmethod
    def analyze(self, market: dict, snapshot: dict) -> Optional[TradingSignal]:
        """Market verilerini analiz et ve sinyal üret."""
        pass


class MomentumStrategy(BaseStrategy):
    """
    Momentum Stratejisi:
    - Fiyat hareketlerine dayalı
    - Düşük fiyatlı (< 0.35) YES token'larda yukarı momentum tespit eder
    - Yüksek fiyatlı (> 0.70) YES token'larda satış sinyali üretir
    - Spread ve likiditeyi dikkate alır
    """

    name = "Momentum"

    def __init__(self, buy_threshold: float = 0.35, sell_threshold: float = 0.70):
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def analyze(self, market: dict, snapshot: dict) -> Optional[TradingSignal]:
        price = snapshot.get("price", 0)
        midpoint = snapshot.get("midpoint", 0)
        spread = snapshot.get("spread", 0)
        token_id = snapshot.get("token_id", "")

        if price <= 0 or spread <= 0:
            return None

        # Spread çok genişse atla
        if spread > 0.05:
            return None

        condition_id = market.get("condition_id", "")
        question = market.get("question", "")

        # Düşük fiyatlı YES token - alım fırsatı
        if price < self.buy_threshold and midpoint > 0:
            # Fiyat midpoint'in altında mı?
            if price < midpoint * 0.98:
                confidence = min(0.85, (self.buy_threshold - price) / self.buy_threshold + 0.3)
                return TradingSignal(
                    signal_type=SignalType.BUY,
                    side=Side.YES,
                    token_id=token_id,
                    condition_id=condition_id,
                    market_question=question,
                    price=price,
                    confidence=confidence,
                    strategy_name=self.name,
                    reason=f"Düşük fiyat momentum: {price:.4f} < threshold {self.buy_threshold}",
                )

        # Yüksek fiyatlı YES token - satış fırsatı (kar al)
        if price > self.sell_threshold:
            confidence = min(0.80, (price - self.sell_threshold) / (1 - self.sell_threshold) + 0.3)
            return TradingSignal(
                signal_type=SignalType.SELL,
                side=Side.YES,
                token_id=token_id,
                condition_id=condition_id,
                market_question=question,
                price=price,
                confidence=confidence,
                strategy_name=self.name,
                reason=f"Yüksek fiyat momentum: {price:.4f} > threshold {self.sell_threshold}",
            )

        return None


class ValueStrategy(BaseStrategy):
    """
    Value Stratejisi:
    - Düşük değerlenmiş market'leri tespit eder
    - YES + NO fiyat toplamı 1'den sapma gösteriyorsa opportunity tespit eder
    - Likidite ve hacim oranlarına bakar
    """

    name = "Value"

    def __init__(self, mispricing_threshold: float = 0.05):
        self.mispricing_threshold = mispricing_threshold

    def analyze(self, market: dict, snapshot: dict) -> Optional[TradingSignal]:
        price = snapshot.get("price", 0)
        token_id = snapshot.get("token_id", "")

        if price <= 0:
            return None

        condition_id = market.get("condition_id", "")
        question = market.get("question", "")

        # Outcome fiyatlarını kontrol et
        outcome_prices = market.get("outcome_prices", "")
        if outcome_prices and isinstance(outcome_prices, str):
            try:
                import json
                prices = json.loads(outcome_prices)
                if len(prices) >= 2:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                    total = yes_price + no_price

                    # Fiyat toplamı 1'den sapma gösteriyorsa
                    deviation = abs(total - 1.0)
                    if deviation > self.mispricing_threshold:
                        # Düşük fiyatlı taraf alım fırsatı
                        if yes_price < no_price and yes_price < 0.45:
                            confidence = min(0.75, deviation * 5 + 0.3)
                            return TradingSignal(
                                signal_type=SignalType.BUY,
                                side=Side.YES,
                                token_id=token_id,
                                condition_id=condition_id,
                                market_question=question,
                                price=yes_price,
                                confidence=confidence,
                                strategy_name=self.name,
                                reason=f"Value fırsatı: YES={yes_price:.4f} NO={no_price:.4f} Total={total:.4f}",
                            )
                        elif no_price < yes_price and no_price < 0.45:
                            confidence = min(0.75, deviation * 5 + 0.3)
                            return TradingSignal(
                                signal_type=SignalType.BUY,
                                side=Side.NO,
                                token_id=token_id,
                                condition_id=condition_id,
                                market_question=question,
                                price=no_price,
                                confidence=confidence,
                                strategy_name=self.name,
                                reason=f"Value fırsatı: NO={no_price:.4f} YES={yes_price:.4f} Total={total:.4f}",
                            )
            except (json.JSONDecodeError, ValueError, IndexError):
                pass

        return None


class ArbitrageStrategy(BaseStrategy):
    """
    Arbitraj Stratejisi:
    - YES + NO fiyatları toplamı < 1.0 ise her ikisini de alarak risksiz kar
    - Bid-ask spread arbitraj fırsatları
    - Cross-market fiyat farkları (aynı event, farklı market)
    """

    name = "Arbitrage"

    def __init__(self, min_profit_pct: float = 0.02):
        self.min_profit_pct = min_profit_pct

    def analyze(self, market: dict, snapshot: dict) -> Optional[TradingSignal]:
        price = snapshot.get("price", 0)
        token_id = snapshot.get("token_id", "")

        if price <= 0:
            return None

        condition_id = market.get("condition_id", "")
        question = market.get("question", "")

        # YES + NO < 1.0 arbitraj kontrolü
        outcome_prices = market.get("outcome_prices", "")
        if outcome_prices and isinstance(outcome_prices, str):
            try:
                import json
                prices = json.loads(outcome_prices)
                if len(prices) >= 2:
                    yes_price = float(prices[0])
                    no_price = float(prices[1])
                    total = yes_price + no_price

                    # Toplam 1'den düşükse arbitraj fırsatı
                    if total < (1.0 - self.min_profit_pct):
                        profit_pct = (1.0 - total) / total
                        confidence = min(0.90, profit_pct * 5 + 0.5)

                        # Daha ucuz tarafı al
                        side = Side.YES if yes_price <= no_price else Side.NO
                        buy_price = min(yes_price, no_price)

                        return TradingSignal(
                            signal_type=SignalType.BUY,
                            side=side,
                            token_id=token_id,
                            condition_id=condition_id,
                            market_question=question,
                            price=buy_price,
                            confidence=confidence,
                            strategy_name=self.name,
                            reason=f"Arbitraj: YES+NO={total:.4f} < 1.0 | Potansiyel kar: {profit_pct:.2%}",
                        )
            except (json.JSONDecodeError, ValueError, IndexError):
                pass

        return None


class StrategyEngine:
    """Tüm stratejileri orkestre eden motor."""

    def __init__(self):
        self.strategies: list[BaseStrategy] = [
            MomentumStrategy(),
            ValueStrategy(),
            ArbitrageStrategy(),
        ]
        logger.info(f"🧠 Strategy Engine başlatıldı | {len(self.strategies)} strateji aktif")

    def evaluate(self, market: dict, snapshot: dict) -> list[TradingSignal]:
        """Tüm stratejileri çalıştır ve sinyalleri topla."""
        signals = []
        for strategy in self.strategies:
            try:
                signal = strategy.analyze(market, snapshot)
                if signal:
                    signals.append(signal)
                    logger.info(f"  📡 {signal}")
            except Exception as e:
                logger.error(f"❌ Strateji hatası [{strategy.name}]: {e}")
        return signals

    def get_best_signal(self, market: dict, snapshot: dict, min_confidence: float = 0.5) -> Optional[TradingSignal]:
        """En yüksek güvenli sinyali döndür."""
        signals = self.evaluate(market, snapshot)
        if not signals:
            return None

        # Güven eşiği altındakileri filtrele
        signals = [s for s in signals if s.confidence >= min_confidence]
        if not signals:
            return None

        # En yüksek güvenli sinyal
        return max(signals, key=lambda s: s.confidence)
