"""
Kelly Criterion — WARRIOR Edition.
Survival-aware pozisyon büyüklüğü hesaplayıcı.
f* = (b*p - q) / b
Bakiye durumuna göre agresif/muhafazakar mod.
"""

import logging
from src.config import settings

logger = logging.getLogger("bot.kelly")


class KellySizer:
    """WARRIOR Kelly — bakiye durumuna göre pozisyon büyüklüğü."""

    def __init__(self):
        self.max_fraction = settings.max_kelly_fraction
        self.multiplier = settings.kelly_multiplier

    def _get_survival_multiplier(self, balance: float) -> float:
        """
        ⚔️ Bakiye durumuna göre agresiflik ayarla.

        - $0-10: HAYATTA KAL modu (muhafazakâr)
        - $10-50: STANDART savaşçı
        - $50-200: AGRESİF savaşçı
        - $200+: FULL POWER
        """
        if balance < 10:
            return 0.4   # Muhafazakâr — hayatta kal
        elif balance < 50:
            return 0.7   # Standart — temkinli ama cesur
        elif balance < 200:
            return 1.0   # Agresif — büyü
        else:
            return 1.2   # Full power — dominasyon

    def _get_time_bonus(self, hours_to_expiry: float) -> float:
        """
        ⏰ Sona yakın eventler için pozisyon bonusu.
        Sona yakın = daha net prediction = daha büyük pozisyon.
        """
        if hours_to_expiry <= 6:
            return 1.5   # 6 saat kala — çok net, büyük bas
        elif hours_to_expiry <= 24:
            return 1.3   # 24 saat kala — iyi
        elif hours_to_expiry <= 72:
            return 1.1   # 72 saat kala — hafif bonus
        else:
            return 1.0   # Uzak — bonus yok

    def calculate(
        self,
        fair_value: float,
        market_price: float,
        balance: float,
        direction: str,
        confidence: float = 0.7,
        hours_to_expiry: float = 9999,
        is_sniper_trade: bool = False,
    ) -> dict:
        """
        ⚔️ WARRIOR Kelly — survival-aware pozisyon hesabı.
        V4.4: Sniper Mode support.
        """
        if direction == "BUY_YES":
            p = fair_value
            price = market_price
        else:  # BUY_NO
            p = 1.0 - fair_value
            price = 1.0 - market_price

        # 1. Edge Calculation
        edge = p - price
        
        # 2. V4.4 SNIPER MODU: Dynamic Multiplier 🎯
        # Config'den gelen sniper_multiplier (0.5) veya kelly_multiplier (0.2) kullanılır.
        
        base_multiplier = self.multiplier # Default (0.2)

        if settings.sniper_mode and is_sniper_trade:
            base_multiplier = settings.sniper_multiplier # 0.5 (Sniper)
            logger.info(f"🎯 SNIPER MODE: High Conviction Trade -> Multiplier boosted to {base_multiplier}x")
        
        dynamic_multiplier = base_multiplier

        # BONUS: Büyük Fırsat (>%15 edge) - SADECE Sniper değilse uygula (Sniper zaten yüksek)
        if edge >= 0.15 and not is_sniper_trade:
            dynamic_multiplier = min(dynamic_multiplier * 1.5, 0.5) # Max 0.5
            
        # PENALTY: Düşük Güven (<%60)
        if confidence < 0.60:
            dynamic_multiplier *= 0.5 # Güven yoksa yarıya indir
            logger.info(f"🛡️ CONFIDENCE PENALTY: Conf {confidence:.1%} < %60 -> 0.5x Size")
            
        # PENALTY: Yüksek Fiyat (Pahalı opsiyon riski)
        # Eğer fiyat 85 cent üzerindeyse downside risk (100 -> 0) çok büyük.
        if price > 0.85:
            dynamic_multiplier *= 0.7 
            
        # Survival Adjustment (Bakiye durumuna göre genel katsayı)
        survival_mult = self._get_survival_multiplier(balance)
        
        # Time Bonus (Sona yaklaşan eventler)
        time_mult = self._get_time_bonus(hours_to_expiry)

        # Final Kriteri: f* = p/a - q/b (Genelleştirilmiş Kelly değil, basit Edge/Odds)
        # Pratik formül: f = edge / odds_return
        # Odds Return = (1 - price) / price
        
        if edge <= 0:
             return self._zero_result(price, direction)

        # Handle edge cases for price to avoid division by zero or extreme odds
        if price <= 0.01 or price >= 0.99:
            return self._zero_result(price, direction)

        odds_return = (1.0 - price) / price
        if odds_return <= 0: # Should not happen if price is between 0.01 and 0.99
             return self._zero_result(price, direction)

        kelly_fraction = edge / odds_return
        
        # 3. Apply Multipliers
        # Adjusted = Raw Kelly * Sniper * Survival * Time
        adjusted_fraction = kelly_fraction * dynamic_multiplier * survival_mult * time_mult

        # Max fraction cap uygula
        final_fraction = min(adjusted_fraction, self.max_fraction)

        # Pozisyon büyüklüğü ($)
        position_size = balance * final_fraction

        # Minimum $1, maximum kontrol
        if position_size < 1.0:
            position_size = 0.0

        # Share sayısı
        shares = position_size / price if price > 0 else 0

        logger.info(
            f"⚔️ Kelly: raw={kelly_fraction:.4f}, adj={adjusted_fraction:.4f}, "
            f"size=${position_size:.2f}, shares={shares:.1f} @ ${price:.3f} | "
            f"survival={survival_mult:.1f}x, time={time_mult:.1f}x"
        )

        return {
            "position_size": round(position_size, 2),
            "shares": round(shares, 1),
            "kelly_fraction": round(kelly_fraction, 4),
            "adjusted_fraction": round(adjusted_fraction, 4),
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
