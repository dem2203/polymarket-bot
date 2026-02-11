"""
Trade Journal + AI Self-Review — Bot her gün kendi trade'lerini analiz eder.
Claude geçmiş trade'lere bakıp:
- Hangi kategorilerde iyi/kötü?
- Hangi tür edge tahminleri doğru çıktı?
- Bir sonraki gün için ne değişmeli?
Bu dersler sonraki döngülerde prompt'a eklenir.
"""

import json
import logging
import time
from datetime import datetime, timezone

import anthropic

from src.config import settings

logger = logging.getLogger("bot.learning.journal")


SELF_REVIEW_PROMPT = """You are a trading performance analyst reviewing your own prediction market trades.

TRADE HISTORY (last 24h):
{trades_json}

OVERALL STATS:
- Total closed trades: {total_trades}
- Wins: {wins} | Losses: {losses}
- Win rate: {win_rate:.0%}
- Total PnL: ${total_pnl:+.2f}
- AI accuracy: {ai_accuracy:.0%}

CATEGORY PERFORMANCE:
{category_text}

Analyze this trading performance and output a JSON object:
{{
    "performance_grade": "A/B/C/D/F",
    "lesson": "One critical lesson learned (max 50 words)",
    "strong_categories": ["category1", "category2"],
    "weak_categories": ["category1"],
    "edge_calibration": "too_aggressive / well_calibrated / too_conservative",
    "recommended_actions": [
        "specific action 1",
        "specific action 2"
    ],
    "confidence_adjustment": "increase / maintain / decrease",
    "risk_adjustment": "increase_position_sizes / maintain / decrease_position_sizes"
}}

Be brutally honest. This analysis directly affects the bot's survival — wrong lessons = lost money.
Output ONLY the JSON, no other text."""


class TradeJournal:
    """Günlük AI self-review motoru."""

    def __init__(self, performance_tracker):
        self.tracker = performance_tracker
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.last_review_time: float = 0.0
        self.latest_review: dict = {}

    async def should_review(self) -> bool:
        """Günlük review zamanı geldi mi?"""
        now = datetime.now(timezone.utc)
        hours_since = (time.time() - self.last_review_time) / 3600

        # Her 12 saatte bir review (hızlı öğrenme)
        return hours_since >= 12 and len(self.tracker.closed_trades) >= 3

    async def run_self_review(self) -> dict:
        """
        Claude kendi trade'lerini analiz eder.
        Sonucu kaydeder ve sonraki döngülerde kullanır.
        """
        try:
            stats = self.tracker.get_stats()
            recent = self.tracker.get_recent_trades_for_review(hours=24)

            if not recent and not self.tracker.closed_trades:
                return {"status": "no_data"}

            # Kategori bilgisi
            cat_text = ""
            cat_stats = stats.get("category_stats", {})
            for cat, cs in cat_stats.items():
                cat_text += f"- {cat}: {cs['wins']}W/{cs['losses']}L ({cs['win_rate']:.0%}), PnL: ${cs['pnl']:+.2f}\n"

            if not cat_text:
                cat_text = "No category data yet."

            prompt = SELF_REVIEW_PROMPT.format(
                trades_json=json.dumps(recent[:20], indent=2, default=str),
                total_trades=stats["total_trades"],
                wins=stats["wins"],
                losses=stats["losses"],
                win_rate=stats["win_rate"],
                total_pnl=stats["total_pnl"],
                ai_accuracy=stats["ai_accuracy"],
                category_text=cat_text,
            )

            response = self.client.messages.create(
                model=settings.ai_model,
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}],
            )

            text = response.content[0].text.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            review = json.loads(text)
            review["reviewed_at"] = time.time()
            review["trades_reviewed"] = len(recent)

            self.latest_review = review
            self.last_review_time = time.time()

            # Tracker'a kaydet (persist)
            self.tracker.save_daily_review(review)

            logger.info(
                f"📓 Self-Review tamamlandı: Grade={review.get('performance_grade', '?')} | "
                f"Lesson: {review.get('lesson', 'N/A')[:60]}"
            )

            return review

        except json.JSONDecodeError as e:
            logger.warning(f"Self-review parse hatası: {e}")
            return {"status": "parse_error", "error": str(e)}
        except Exception as e:
            logger.error(f"Self-review hatası: {e}")
            return {"status": "error", "error": str(e)}

    def get_latest_lesson(self) -> str:
        """En son review'dan öğrenilen ders."""
        if self.latest_review:
            return self.latest_review.get("lesson", "")

        # Persist'ten yükle
        if self.tracker.daily_reviews:
            return self.tracker.daily_reviews[-1].get("lesson", "")

        return ""

    def format_review_report(self) -> str:
        """Telegram'a gönderilecek review raporu."""
        r = self.latest_review
        if not r or r.get("status") == "no_data":
            return ""

        grade = r.get("performance_grade", "?")
        lesson = r.get("lesson", "N/A")
        edge_cal = r.get("edge_calibration", "unknown")
        risk_adj = r.get("risk_adjustment", "maintain")
        actions = r.get("recommended_actions", [])

        grade_emoji = {
            "A": "🏆", "B": "✅", "C": "⚠️", "D": "🔻", "F": "💀"
        }.get(grade, "❓")

        strong = ", ".join(r.get("strong_categories", [])) or "—"
        weak = ", ".join(r.get("weak_categories", [])) or "—"

        report = (
            f"📓 AI SELF-REVIEW\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Grade: {grade_emoji} {grade}\n"
            f"Lesson: {lesson}\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Strong: {strong}\n"
            f"Weak: {weak}\n"
            f"Edge: {edge_cal}\n"
            f"Risk: {risk_adj}\n"
        )

        if actions:
            report += "━━━━━━━━━━━━━━━\nActions:\n"
            for a in actions[:3]:
                report += f"• {a}\n"

        return report
