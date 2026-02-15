"""
Mispricing Strategy V3 — Dual-AI consensus + self-learning.
AI fair value vs market price → edge > %8 → DeepSeek doğrulama → trade sinyali.
"""

import logging
from dataclasses import dataclass, field
from typing import Optional

from src.config import settings
from src.ai.brain import AIBrain
from src.ai.deepseek_validator import DeepSeekValidator
from src.strategy.kelly import KellySizer

logger = logging.getLogger("bot.strategy.mispricing")


@dataclass
class TradeSignal:
    """Bir trade sinyali."""
    market_id: str
    question: str
    category: str
    direction: str         # BUY_YES veya BUY_NO
    fair_value: float      # Claude hesapladı
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
    # V3: Dual-AI
    deepseek_fair_value: float = 0.0
    consensus: bool = True
    combined_fair_value: float = 0.0
    entry_price: float = 0.0


class MispricingStrategy:
    """AI-powered mispricing tespiti — V3: dual-AI + self-learning."""

    def __init__(self, brain: AIBrain, kelly: KellySizer,
                 deepseek: Optional[DeepSeekValidator] = None,
                 fact_checker = None):  # V3.6: Data validation
        self.brain = brain
        self.kelly = kelly
        self.deepseek = deepseek
        self.fact_checker = fact_checker  # V3.6
        self.threshold = settings.mispricing_threshold

        # Performance context (PerformanceTracker'dan gelir)
        self._performance_context = ""

    def set_performance_context(self, context: str):
        """PerformanceTracker'dan öğrenme bilgisini ayarla."""
        self._performance_context = context

    async def analyze_market(self, market: dict, cash: float,
                               portfolio_value: float = 0.0,
                               kelly_multiplier: float = 0.5) -> Optional[TradeSignal]:
        """
        Tek bir marketi analiz et — V3 pipeline:
        1. Claude'dan fair value al (performance context ile)
        2. DeepSeek ile doğrula (consensus check)
        3. Mispricing var mı kontrol et (>%8)
        4. Kelly ile pozisyon büyüklüğü hesapla (adaptive)
        5. TradeSignal döndür
        """
        # 1. AI Fair Value (Claude + financial context)
        ai_result = await self.brain.estimate_fair_value(
            market, 
            performance_context=self._performance_context,
            cash=cash,
            portfolio_value=portfolio_value
        )
        if not ai_result:
            return None

        fair_value = ai_result["probability"]
        confidence = ai_result["confidence"]
        reasoning = ai_result["reasoning"]
        api_cost = ai_result["api_cost"]

        question = market.get("question", "")[:40]
        yes_price = float(market.get("yes_price", 0.5))
        
        # Debug: AI ne düşünüyor?
        edge_raw = abs(fair_value - yes_price)
        logger.info(
            f"🧠 AI: {question}... | FV={fair_value:.2f} vs Mkt={yes_price:.2f} "
            f"| Edge={edge_raw:.1%} | Conf={confidence:.0%}"
        )

        # Düşük güvenli tahminleri atla (Warrior: 0.45'e düşürüldü)
        if confidence < 0.45:
            logger.debug(f"⏭️ Düşük güven ({confidence:.0%}) — atlandı: {question}")
            return None
        
        # V3.6: DATA VALIDATION (before any trading logic)
        if self.fact_checker:
            validation = await self.fact_checker.validate_reasoning(
                market["question"],
                ai_result["reasoning"],
                market
            )
            
            if not validation["valid"]:
                logger.error(
                    f"🚨 AI DATA ERROR: {market['question'][:40]}...\n"
                    f"Warnings: {validation.get('warnings', [])}\n"
                    f"REJECTING TRADE due to invalid AI assumptions!"
                )
                return None  # REJECT - AI using wrong data!
            
            # Log successful validation
            if validation.get("details"):
                logger.info(f"✅ Data validated: {validation['details']}")

        # 2. Ön mispricing kontrolü (DeepSeek'i gereksiz yere çağırmamak için)
        pre_mispricing = self.brain.detect_mispricing(fair_value, yes_price)

        if not pre_mispricing["has_edge"]:
            logger.debug(f"⏭️ Edge yok ({edge_raw:.1%} < {settings.mispricing_threshold:.0%}) — atlandı: {question}")
            return None

        # 3. DeepSeek Consensus Check (sadece edge varsa çağır — maliyet optimizasyonu)
        deepseek_fv = 0.0
        combined_fv = fair_value
        consensus = True

        if self.deepseek and self.deepseek.enabled:
            validation = await self.deepseek.validate_signal(market, ai_result)
            api_cost += validation.get("api_cost", 0)
            deepseek_fv = validation["deepseek_probability"]
            consensus = validation["consensus"]

            if validation["recommendation"] == "SKIP":
                logger.info(
                    f"⛔ DeepSeek Veto: {market['question'][:40]}... | "
                    f"Claude={fair_value:.2f} vs DS={deepseek_fv:.2f}"
                )
                return None

            if validation["recommendation"] == "REDUCE":
                # Combined probability kullan, edge küçülecek
                combined_fv = validation["combined_probability"]
                confidence *= 0.8  # Güveni azalt
                logger.info(
                    f"⚠️ DeepSeek Azalt: {market['question'][:40]}... | "
                    f"Combined FV={combined_fv:.2f}"
                )
                # Tam consensus — combined kullan
                combined_fv = validation["combined_probability"]
        
        # 4. Final mispricing tespiti (combined FV ile)
        mispricing = self.brain.detect_mispricing(combined_fv, yes_price)

        if not mispricing["has_edge"]:
            return None

        direction = mispricing["direction"]
        edge = mispricing["edge"]

        # V3.7: PRICE ENTRY VALIDATION (Profitability Fix)
        # Reject trades with negative payoff asymmetry
        price_to_check = yes_price if direction == "YES" else (1.0 - yes_price)
        
        # Rule 1: Never buy above $0.65 (poor risk/reward)
        MAX_ENTRY_PRICE = 0.65
        if price_to_check > MAX_ENTRY_PRICE:
            logger.warning(
                f"⛔ V3.7 REJECT: Price too high ({price_to_check:.2f} > {MAX_ENTRY_PRICE:.2f}) | "
                f"{market['question'][:40]}..."
            )
            return None
        
        # Rule 2: Ensure positive payoff asymmetry (upside >= downside)
        upside = 1.0 - price_to_check
        downside = price_to_check
        if upside < downside * 0.8:  # Allow some slack but not too bad
            logger.warning(
                f"⛔ V3.7 REJECT: Negative asymmetry (upside ${upside:.2f} < downside ${downside:.2f}) | "
                f"{market['question'][:40]}..."
            )
            return None
        
        logger.info(
            f"✅ V3.7 Price OK: Entry=${price_to_check:.2f} | "
            f"Upside=${upside:.2f} vs Downside=${downside:.2f} | R:R={upside/downside:.2f}:1"
        )

        logger.info(
            f"🎯 {'🤝Dual' if deepseek_fv > 0 else '🧠Solo'} Mispricing: "
            f"{market['question'][:50]}... | "
            f"Claude={fair_value:.2f} DS={deepseek_fv:.2f} → FV={combined_fv:.2f} vs "
            f"Price={yes_price:.2f} | Edge={edge:.1%} | {direction}"
        )

        # 5. Kelly Criterion (adaptive multiplier + time bonus)
        hours_to_expiry = market.get("hours_to_expiry", 9999)
        
        # V4.4 SNIPER CHECK 🎯
        # "Sniper" olmak için:
        # 1. Sniper Mode açık
        # 2. Dual-AI Consensus var
        # 3. Confidence >= %90 (Çok emin)
        is_sniper_trade = False
        if settings.sniper_mode and consensus and deepseek_fv > 0:
            if confidence >= 0.90:
                is_sniper_trade = True
                logger.info(f"🎯 SNIPER SİNYAL TESPİT EDİLDİ! ({market['question'][:40]}...)")

        kelly_result = self.kelly.calculate(
            fair_value=combined_fv,
            market_price=yes_price,
            balance=cash,  # Use cash for sizing
            direction=direction,
            confidence=confidence,
            hours_to_expiry=hours_to_expiry,
            is_sniper_trade=is_sniper_trade,
        )

        # Adaptive multiplier uygula
        original_size = kelly_result["position_size"]
        # Default 0.5 ile hesaplanan raw size'ı configdeki multiplier ile oranla
        # Fakat Sniper Mode zaten içeride multiplier'ı seçti.
        # Bu satır V3'ten kalma ve Sniper Mode ile çakışabilir.
        # KellySizer zaten doğru multiplier (0.5 veya 0.2) kullandı.
        # Sadece "Adaptive Kelly" (trade sayısına göre) varsa onu dikkate almalıyız?
        # Main.py'den gelen kelly_multiplier argümanı "Adaptive" olanı taşıyor.
        
        # Eğer Adaptive Kelly (main.py) kullanılıyorsa, KellySizer'ın kullandığı base'i buna göre scale etmeliyiz.
        # Ancak Sniper Mode bunu override etmeli mi?
        # Karar: Sniper Mode her zaman Settings'deki Sniper Multiplier'ı (0.5) kullanır.
        # Normal mod ise Main.py'den gelen Adaptive Multiplier'ı kullanır.
        
        adjusted_size = original_size
        
        if not is_sniper_trade:
             # Normal trade: Adaptive Scaling
             # KellySizer default olarak settings.kelly_multiplier (0.2) kullandı.
             # Eğer main.py bize farklı bir multiplier (örn 0.5) gönderdiyse scale et.
             # Scaling Factor = Passed Multiplier / Config Multiplier
             if settings.kelly_multiplier > 0:
                 scale_factor = kelly_multiplier / settings.kelly_multiplier
                 adjusted_size = original_size * scale_factor
        
        # V4.4: Old Boost Logic REMOVED (Clean implementation)
        # Sadece loglama amacıyla
        if is_sniper_trade:
             logger.info(f"🚀 SNIPER EXECUTION: {adjusted_size:.2f} (0.5x Kelly)")
             
        adjusted_size *= 1.0 # No extra boost
        
        # Hard cap: max 20% of capital per trade (even with boost)
        MAX_POSITION_PCT = 0.20
        adjusted_size = min(adjusted_size, cash * MAX_POSITION_PCT)
        adjusted_size = min(adjusted_size, cash * settings.max_kelly_fraction)

        if adjusted_size < 1.0:
            logger.debug(f"Kelly too small for {market['question'][:40]}")
            return None

        # Shares yeniden hesapla
        price = kelly_result["price"]
        adjusted_shares = adjusted_size / price if price > 0 else 0

        # 6. Trade Signal oluştur
        return TradeSignal(
            market_id=market["id"],
            question=market["question"],
            category=market.get("category", "general"),
            direction=direction,
            fair_value=fair_value,
            market_price=yes_price,
            edge=edge,
            confidence=confidence,
            position_size=round(adjusted_size, 2),
            shares=round(adjusted_shares, 2),
            price=price,
            token_side=kelly_result["token_side"],
            reasoning=reasoning,
            kelly_fraction=kelly_result["adjusted_fraction"],
            api_cost=api_cost,
            tokens=market.get("tokens", []),
            slug=market.get("slug", ""),
            deepseek_fair_value=deepseek_fv,
            consensus=consensus,
            combined_fair_value=combined_fv,
            entry_price=price,
        )

    async def scan_for_signals(
        self, markets: list[dict], cash: float,
        portfolio_value: float = 0.0,
        max_signals: int = 5, kelly_multiplier: float = 0.5
    ) -> list[TradeSignal]:
        """
        Tüm marketleri tara, en iyi sinyalleri döndür.
        V3: adaptive Kelly multiplier + performance context + financial awareness.
        """
        signals = []
        analyzed = 0

        for market in markets:
            try:
                signal = await self.analyze_market(
                    market, 
                    cash=cash,
                    portfolio_value=portfolio_value, 
                    kelly_multiplier=kelly_multiplier
                )
                analyzed += 1

                if signal:
                    signals.append(signal)
                    consensus_emoji = "🤝" if signal.deepseek_fair_value > 0 else "🧠"
                    logger.info(
                        f"📊 Sinyal #{len(signals)}: {signal.question[:40]}... "
                        f"| {consensus_emoji} {signal.direction} @ ${signal.price:.3f} "
                        f"| Edge={signal.edge:.1%} | Size=${signal.position_size:.2f}"
                    )

                if len(signals) >= max_signals:
                    break

            except Exception as e:
                logger.warning(f"Market analiz hatası: {e}")
                continue

        # Edge * confidence ile sırala
        signals.sort(key=lambda s: s.edge * s.confidence, reverse=True)

        logger.info(
            f"📈 {analyzed} market analiz edildi → {len(signals)} sinyal bulundu "
            f"(API maliyeti: ${self.brain.total_api_cost:.4f})"
        )

        return signals[:max_signals]
