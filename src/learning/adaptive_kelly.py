"""
Adaptive Kelly — Win rate'e göre dinamik pozisyon boyutlama.
Bot kazandıkça daha agresif, kaybettikçe daha temkinli olur.
Kategori bazlı ayarlama: politics'te iyi → politics'te daha büyük pozisyon.
"""

import logging
from typing import Optional

logger = logging.getLogger("bot.learning.kelly")


class AdaptiveKelly:
    """
    Win rate tracking ile Kelly multiplier'ı dinamik ayarlar.

    Win rate > %60 → multiplier artır (agresif)
    Win rate %45-60 → default (temkinli)
    Win rate < %45 → multiplier düşür (hayatta kalma)
    """

    # Sınırlar
    MIN_MULTIPLIER = 0.15      # Minimum Kelly multiplier
    DEFAULT_MULTIPLIER = 0.50  # Default (fractional Kelly)
    MAX_MULTIPLIER = 0.75      # Maximum (agresif)
    MIN_TRADES_REQUIRED = 5    # Adaptif mod için min trade sayısı

    # Win rate -> multiplier eşlemeleri
    TIERS = [
        (0.75, 0.75),   # %75+ win rate → %75 Kelly (çok agresif)
        (0.65, 0.65),   # %65-75 → %65 Kelly (agresif)
        (0.55, 0.50),   # %55-65 → %50 Kelly (normal)
        (0.45, 0.35),   # %45-55 → %35 Kelly (temkinli)
        (0.35, 0.25),   # %35-45 → %25 Kelly (çok temkinli)
        (0.00, 0.15),   # <%35 → %15 Kelly (hayatta kalma)
    ]

    def __init__(self):
        self.global_multiplier = self.DEFAULT_MULTIPLIER
        self.category_multipliers: dict[str, float] = {}

    def update_from_stats(self, stats: dict):
        """
        PerformanceTracker.get_stats() çıktısıyla güncelle.
        """
        total = stats.get("total_trades", 0)

        if total < self.MIN_TRADES_REQUIRED:
            logger.info(
                f"📊 Adaptive Kelly: {total} trade (min {self.MIN_TRADES_REQUIRED}) "
                f"— default {self.DEFAULT_MULTIPLIER} kullanılıyor"
            )
            self.global_multiplier = self.DEFAULT_MULTIPLIER
            return

        win_rate = stats.get("win_rate", 0.5)
        old_mult = self.global_multiplier
        self.global_multiplier = self._win_rate_to_multiplier(win_rate)

        if abs(old_mult - self.global_multiplier) > 0.01:
            logger.info(
                f"📊 Adaptive Kelly güncellendi: {old_mult:.2f} → {self.global_multiplier:.2f} "
                f"(win rate: {win_rate:.0%}, {total} trade)"
            )

        # Kategori bazlı ayarlama
        cat_stats = stats.get("category_stats", {})
        for cat, cs in cat_stats.items():
            if cs["total"] >= 3:
                cat_wr = cs["win_rate"]
                self.category_multipliers[cat] = self._win_rate_to_multiplier(cat_wr)

    def get_multiplier(self, category: str = "general") -> float:
        """
        Bir trade için kullanılacak Kelly multiplier.
        Kategori varsa kategori-spesifik, yoksa global.
        """
        cat_mult = self.category_multipliers.get(category)
        if cat_mult is not None:
            # Kategori ve global'in ağırlıklı ortalaması
            # %60 kategori, %40 global — kategoriye daha fazla ağırlık
            blended = 0.6 * cat_mult + 0.4 * self.global_multiplier
            return max(self.MIN_MULTIPLIER, min(self.MAX_MULTIPLIER, blended))
        return self.global_multiplier

    def _win_rate_to_multiplier(self, win_rate: float) -> float:
        """Win rate'e göre tier'dan multiplier bul."""
        for threshold, multiplier in self.TIERS:
            if win_rate >= threshold:
                return multiplier
        return self.MIN_MULTIPLIER

    def get_report(self) -> str:
        """Mevcut Kelly durumu raporu."""
        lines = [
            f"Kelly Multiplier: {self.global_multiplier:.2f}",
        ]
        if self.category_multipliers:
            for cat, mult in sorted(self.category_multipliers.items(),
                                     key=lambda x: x[1], reverse=True):
                lines.append(f"  {cat}: {mult:.2f}")
        return " | ".join(lines)
