"""
Performance Tracker — Bot'un trade hafızası.
Her trade'in sonucunu kaydeder, win rate ve kategori bazlı performansı takip eder.
Bu bilgiyi AI prompt'una verir → bot geçmişinden öğrenir.
"""

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Optional
from collections import defaultdict

logger = logging.getLogger("bot.learning.perf")

DATA_DIR = "data"
HISTORY_FILE = os.path.join(DATA_DIR, "trade_history.json")


@dataclass
class TradeRecord:
    """Tek bir trade kaydı."""
    trade_id: str
    market_id: str
    question: str
    category: str
    direction: str          # BUY_YES / BUY_NO
    entry_price: float
    fair_value_claude: float
    fair_value_deepseek: float = 0.0
    confidence: float = 0.5
    position_size: float = 0.0
    kelly_fraction: float = 0.0
    edge: float = 0.0
    reasoning: str = ""
    # Sonuç
    outcome: str = "OPEN"   # OPEN / WIN / LOSS / EXPIRED
    exit_price: float = 0.0
    pnl: float = 0.0
    # Zaman
    opened_at: float = 0.0
    closed_at: float = 0.0
    # Meta
    cycle_number: int = 0
    ai_was_correct: bool = False   # AI'ın yönü doğru muydu?
    edge_accuracy: float = 0.0    # Gerçek edge vs tahmin edge


class PerformanceTracker:
    """
    Trade geçmişini takip eden ve öğrenme context'i üreten motor.
    JSON'a persist eder — Railway restart'larında kaybolmaz.
    """

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.trades: list[TradeRecord] = []
        self.daily_reviews: list[dict] = []
        self._load()

    def _load(self):
        """Trade geçmişini diskten yükle."""
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.trades = [TradeRecord(**t) for t in data.get("trades", [])]
                self.daily_reviews = data.get("daily_reviews", [])
                logger.info(f"📚 {len(self.trades)} trade geçmişi yüklendi")
            except Exception as e:
                logger.warning(f"Trade geçmişi yüklenemedi: {e}")
                self.trades = []

    def _save(self):
        """Trade geçmişini diske kaydet."""
        try:
            data = {
                "trades": [asdict(t) for t in self.trades],
                "daily_reviews": self.daily_reviews[-30:],  # Son 30 gün
                "last_saved": time.time(),
            }
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Trade geçmişi kaydedilemedi: {e}")

    def reload(self):
        """Diskten trade geçmişini yeniden yükle."""
        self._load()

    def record_trade(self, signal, cycle_number: int = 0,
                     deepseek_fv: float = 0.0) -> str:
        """Yeni trade kaydet. Trade ID döner."""
        trade_id = f"T-{len(self.trades)+1:05d}"

        record = TradeRecord(
            trade_id=trade_id,
            market_id=signal.market_id,
            question=signal.question,
            category=signal.category,
            direction=signal.direction,
            entry_price=signal.price,
            fair_value_claude=signal.fair_value,
            fair_value_deepseek=deepseek_fv,
            confidence=signal.confidence,
            position_size=signal.position_size,
            kelly_fraction=signal.kelly_fraction,
            edge=signal.edge,
            reasoning=signal.reasoning,
            outcome="OPEN",
            opened_at=time.time(),
            cycle_number=cycle_number,
        )

        self.trades.append(record)
        self._save()
        logger.info(f"📝 Trade kaydedildi: {trade_id} | {signal.question[:40]}...")
        return trade_id

    def close_trade(self, market_id: str, exit_price: float, pnl: float):
        """Trade'i kapat, sonucu kaydet."""
        for trade in reversed(self.trades):
            if trade.market_id == market_id and trade.outcome == "OPEN":
                trade.outcome = "WIN" if pnl > 0 else "LOSS"
                trade.exit_price = exit_price
                trade.pnl = pnl
                trade.closed_at = time.time()

                # AI doğru muydu?
                if trade.direction == "BUY_YES":
                    trade.ai_was_correct = exit_price > trade.entry_price
                else:
                    trade.ai_was_correct = exit_price < trade.entry_price

                # Edge doğruluğu
                actual_edge = abs(exit_price - trade.entry_price)
                trade.edge_accuracy = min(actual_edge / max(trade.edge, 0.01), 2.0)

                self._save()
                logger.info(
                    f"{'✅' if pnl > 0 else '❌'} Trade kapandı: {trade.trade_id} | "
                    f"PnL: ${pnl:+.2f} | AI {'doğru' if trade.ai_was_correct else 'yanlış'}"
                )
                return
        logger.warning(f"Kapanacak trade bulunamadı: {market_id}")

    def save_daily_review(self, review: dict):
        """Günlük AI self-review sonucunu kaydet."""
        self.daily_reviews.append({
            **review,
            "timestamp": time.time(),
        })
        self._save()

    # ---- İstatistikler ----

    @property
    def closed_trades(self) -> list[TradeRecord]:
        return [t for t in self.trades if t.outcome in ("WIN", "LOSS")]

    @property
    def open_trades(self) -> list[TradeRecord]:
        return [t for t in self.trades if t.outcome == "OPEN"]

    def get_stats(self, last_n: int = 50) -> dict:
        """Genel performans istatistikleri."""
        closed = self.closed_trades[-last_n:]
        if not closed:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "total_pnl": 0.0,
                "avg_win": 0.0, "avg_loss": 0.0,
                "best_category": "unknown", "worst_category": "unknown",
                "ai_accuracy": 0.0,
            }

        wins = [t for t in closed if t.outcome == "WIN"]
        losses = [t for t in closed if t.outcome == "LOSS"]
        win_rate = len(wins) / len(closed) if closed else 0

        # Kategori bazlı performans
        cat_stats = self._category_stats(closed)
        best_cat = max(cat_stats, key=lambda c: cat_stats[c]["win_rate"]) if cat_stats else "unknown"
        worst_cat = min(cat_stats, key=lambda c: cat_stats[c]["win_rate"]) if cat_stats else "unknown"

        return {
            "total_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 4),
            "total_pnl": round(sum(t.pnl for t in closed), 2),
            "avg_win": round(sum(t.pnl for t in wins) / max(len(wins), 1), 2),
            "avg_loss": round(sum(t.pnl for t in losses) / max(len(losses), 1), 2),
            "best_category": best_cat,
            "worst_category": worst_cat,
            "category_stats": cat_stats,
            "ai_accuracy": round(sum(1 for t in closed if t.ai_was_correct) / max(len(closed), 1), 4),
        }

    def _category_stats(self, trades: list[TradeRecord]) -> dict:
        """Kategori bazlı win rate."""
        cats = defaultdict(lambda: {"wins": 0, "losses": 0, "total": 0, "pnl": 0.0})
        for t in trades:
            cat = t.category or "general"
            cats[cat]["total"] += 1
            cats[cat]["pnl"] += t.pnl
            if t.outcome == "WIN":
                cats[cat]["wins"] += 1
            else:
                cats[cat]["losses"] += 1

        for cat in cats:
            total = cats[cat]["total"]
            cats[cat]["win_rate"] = round(cats[cat]["wins"] / max(total, 1), 4)
            cats[cat]["pnl"] = round(cats[cat]["pnl"], 2)

        return dict(cats)

    def get_performance_context(self) -> str:
        """
        AI prompt'una eklenecek performans özeti.
        Bot bu bilgiyle geçmişinden öğrenir.
        """
        stats = self.get_stats()

        if stats["total_trades"] < 3:
            return ""  # Yeterli veri yok

        cat_stats = stats.get("category_stats", {})

        # En iyi ve en kötü kategorileri bul
        good_cats = []
        bad_cats = []
        for cat, cs in cat_stats.items():
            if cs["total"] >= 3:
                if cs["win_rate"] >= 0.60:
                    good_cats.append(f"{cat} ({cs['win_rate']:.0%})")
                elif cs["win_rate"] <= 0.40:
                    bad_cats.append(f"{cat} ({cs['win_rate']:.0%})")

        # Son review'dan öğrenilen ders
        last_lesson = ""
        if self.daily_reviews:
            last_review = self.daily_reviews[-1]
            last_lesson = last_review.get("lesson", "")

        lines = [
            f"PERFORMANCE HISTORY (last {stats['total_trades']} trades):",
            f"- Win rate: {stats['win_rate']:.0%} ({stats['wins']}W / {stats['losses']}L)",
            f"- Total PnL: ${stats['total_pnl']:+.2f}",
            f"- AI accuracy: {stats['ai_accuracy']:.0%}",
        ]

        if good_cats:
            lines.append(f"- Strong categories: {', '.join(good_cats)}")
        if bad_cats:
            lines.append(f"- Weak categories (be cautious): {', '.join(bad_cats)}")
        if last_lesson:
            lines.append(f"- Latest self-review lesson: {last_lesson}")

        lines.append(
            "USE THIS HISTORY: be more aggressive in strong categories, "
            "more conservative in weak ones. Adjust probability estimates "
            "based on your past accuracy."
        )

        return "\n".join(lines)

    def get_recent_trades_for_review(self, hours: int = 24) -> list[dict]:
        """Son N saatteki trade'leri self-review için döndür."""
        cutoff = time.time() - (hours * 3600)
        recent = [t for t in self.trades if t.opened_at > cutoff]
        return [asdict(t) for t in recent]

    def get_daily_pnl_report(self) -> dict:
        """
        V3.8: Günlük P&L Raporu (Compound Growth Tracking).
        Bugünkü işlemleri ve performansı özetler.
        """
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")
        
        # Bugün kapanan veya açılan trade'leri bul
        # Not: Basitlik için kapanış zamanına göre bakalım
        trades_today = []
        for t in self.trades:
            if t.outcome in ["WIN", "LOSS"]:
                # Kapanış zamanı bugün mü?
                if t.closed_at > 0:
                    dt = datetime.fromtimestamp(t.closed_at, timezone.utc)
                    if dt.strftime("%Y-%m-%d") == today_str:
                        trades_today.append(t)
        
        if not trades_today:
            return {
                "date": today_str,
                "total_pnl": 0.0,
                "num_trades": 0,
                "wins": 0,
                "losses": 0,
                "win_rate": 0.0,
                "best_win": 0.0,
                "worst_loss": 0.0,
                "categories": {}
            }
            
        wins = [t for t in trades_today if t.outcome == "WIN"]
        losses = [t for t in trades_today if t.outcome == "LOSS"]
        total_pnl = sum(t.pnl for t in trades_today)
        win_rate = len(wins) / len(trades_today)
        
        # Kategori bazlı
        categories = defaultdict(float)
        for t in trades_today:
            cat = t.category or "general"
            categories[cat] += t.pnl
            
        return {
            "date": today_str,
            "total_pnl": round(total_pnl, 2),
            "num_trades": len(trades_today),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(win_rate, 2),
            "best_win": round(max([t.pnl for t in trades_today], default=0), 2),
            "worst_loss": round(min([t.pnl for t in trades_today], default=0), 2),
            "categories": dict(categories)
        }
