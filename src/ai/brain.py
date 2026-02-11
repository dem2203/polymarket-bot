"""
AI Brain — Claude Fair Value Engine
Claude Haiku ile her market için adil değer (fair value) hesaplar.
Mispricing tespiti yapar. API maliyetini takip eder.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import anthropic

from src.config import settings
from src.ai.prompts import FAIR_VALUE_SYSTEM, FAIR_VALUE_PROMPT

logger = logging.getLogger("bot.ai")


class AIBrain:
    """Claude AI ile fair value hesaplama motoru."""

    def __init__(self):
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.ai_model
        self.max_tokens = settings.ai_max_tokens

        # Maliyet takibi
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_api_calls = 0
        self.total_failures = 0
        self.last_error = ""

        # Claude Haiku 4.5 fiyatları (USD per million tokens)
        self.input_cost_per_m = 1.0    # $1 / M input tokens
        self.output_cost_per_m = 5.0   # $5 / M output tokens

    def health_check(self) -> dict:
        """
        Startup health check — Claude API'yi test et.
        Returns: {"ok": bool, "model": str, "error": str}
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=30,
                messages=[{"role": "user", "content": "Reply with: OK"}],
            )
            text = response.content[0].text.strip()
            logger.info(f"✅ AI Health Check: {self.model} — {text}")
            return {"ok": True, "model": self.model, "response": text, "error": ""}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"❌ AI Health Check FAILED: {error_msg}")
            return {"ok": False, "model": self.model, "response": "", "error": error_msg}

    @property
    def total_api_cost(self) -> float:
        """Toplam API maliyeti ($)."""
        input_cost = (self.total_input_tokens / 1_000_000) * self.input_cost_per_m
        output_cost = (self.total_output_tokens / 1_000_000) * self.output_cost_per_m
        return input_cost + output_cost

    async def estimate_fair_value(self, market: dict,
                                    performance_context: str = "") -> Optional[dict]:
        """
        Tek bir market için Claude'dan fair value hesapla.
        performance_context: PerformanceTracker'dan gelen öğrenme bilgisi.

        Returns:
            {"probability": 0.XX, "confidence": 0.XX, "reasoning": "..."} veya None
        """
        try:
            question = market.get("question", "")
            description = market.get("description", "")
            category = market.get("category", "general")
            yes_price = float(market.get("yes_price", 0.5))
            no_price = float(market.get("no_price", 0.5))
            end_date = market.get("end_date", "Unknown")
            volume = float(market.get("volume", 0))

            prompt = FAIR_VALUE_PROMPT.format(
                question=question,
                description=description[:500],
                category=category,
                yes_price=yes_price,
                no_price=no_price,
                end_date=end_date,
                current_date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                volume=volume,
            )

            # Performance context'i system prompt'a enjekte et
            system = FAIR_VALUE_SYSTEM.format(
                performance_context=performance_context or ""
            )

            response = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )

            # Token takibi
            self.total_input_tokens += response.usage.input_tokens
            self.total_output_tokens += response.usage.output_tokens
            self.total_api_calls += 1

            # Yanıtı parse et
            text = response.content[0].text.strip()

            # JSON'u çıkar (bazen markdown code block içinde olabilir)
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            result = json.loads(text)

            # Validate
            prob = float(result.get("probability", 0.5))
            conf = float(result.get("confidence", 0.5))
            reasoning = result.get("reasoning", "")

            if not (0.0 <= prob <= 1.0):
                prob = max(0.0, min(1.0, prob))
            if not (0.0 <= conf <= 1.0):
                conf = max(0.0, min(1.0, conf))

            return {
                "probability": prob,
                "confidence": conf,
                "reasoning": reasoning,
                "api_cost": self._last_call_cost(response),
            }

        except json.JSONDecodeError as e:
            self.total_failures += 1
            self.last_error = f"JSON parse: {e}"
            logger.warning(f"AI yanıtı parse edilemedi: {e}")
            return None
        except anthropic.APIError as e:
            self.total_failures += 1
            self.last_error = f"API: {e}"
            logger.error(f"Claude API hatası: {e}")
            return None
        except Exception as e:
            self.total_failures += 1
            self.last_error = f"Genel: {e}"
            logger.error(f"AI analiz hatası: {e}")
            return None

    def _last_call_cost(self, response) -> float:
        """Son API çağrısının maliyeti."""
        inp = (response.usage.input_tokens / 1_000_000) * self.input_cost_per_m
        out = (response.usage.output_tokens / 1_000_000) * self.output_cost_per_m
        return inp + out

    def detect_mispricing(self, fair_value: float, market_price: float) -> dict:
        """
        Fair value ile market fiyatı arasındaki mispricing'i tespit et.
        
        Returns:
            {
                "has_edge": bool,
                "edge": float,         # Mutlak fark
                "direction": "BUY_YES" | "BUY_NO" | None,
                "expected_profit": float
            }
        """
        edge = fair_value - market_price
        abs_edge = abs(edge)
        threshold = settings.mispricing_threshold

        if abs_edge < threshold:
            return {
                "has_edge": False,
                "edge": abs_edge,
                "direction": None,
                "expected_profit": 0.0,
            }

        if edge > 0:
            # AI daha yüksek olasılık veriyor → YES ucuz → BUY YES
            direction = "BUY_YES"
            # Beklenen kâr: $1 * (fair_value - market_price) per share
            expected_profit = edge
        else:
            # AI daha düşük olasılık veriyor → NO ucuz → BUY NO
            direction = "BUY_NO"
            expected_profit = abs_edge

        return {
            "has_edge": True,
            "edge": abs_edge,
            "direction": direction,
            "expected_profit": expected_profit,
        }

    def get_cost_report(self) -> dict:
        """API maliyet raporu."""
        return {
            "total_api_calls": self.total_api_calls,
            "total_input_tokens": self.total_input_tokens,
            "total_output_tokens": self.total_output_tokens,
            "total_api_cost_usd": round(self.total_api_cost, 4),
            "total_failures": self.total_failures,
            "last_error": self.last_error,
        }
