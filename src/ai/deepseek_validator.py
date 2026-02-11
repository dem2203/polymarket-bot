"""
DeepSeek Validator — İkinci AI ile dual-consensus doğrulama.
Claude sinyal verdiğinde DeepSeek'e de sorar.
İki AI uyuşursa → güçlü sinyal, uyuşmazsa → reddet.
DeepSeek çok ucuz ($0.07/M input) — doğrulama maliyeti düşük.
"""

import json
import logging
from typing import Optional
from openai import OpenAI

from src.config import settings

logger = logging.getLogger("bot.ai.deepseek")


DEEPSEEK_SYSTEM = """You are a professional prediction market analyst. Your job is to independently estimate the TRUE probability that a prediction market question resolves YES.

Rules:
- Output ONLY a JSON object: {"probability": 0.XX, "confidence": 0.XX, "reasoning": "brief reason"}
- probability: your estimated probability of YES outcome (0.00 to 1.00)
- confidence: how confident you are (0.50 = uncertain, 0.95 = very confident)
- reasoning: 1-2 sentences max
- Be calibrated and independent. Do NOT anchor to the market price.
- If unsure, output probability close to 0.50 with low confidence
- Do NOT add any text outside the JSON"""

DEEPSEEK_PROMPT = """Analyze this prediction market:

Question: {question}
Description: {description}
Category: {category}
Current Date: {current_date}
End Date: {end_date}
24h Volume: ${volume:,.0f}

Estimate the TRUE probability of this question resolving YES.
Output ONLY the JSON object."""


class DeepSeekValidator:
    """
    DeepSeek ile ikinci AI doğrulama.
    Claude sinyal verdiğinde DeepSeek'e de sorar → consensus check.
    """

    def __init__(self):
        self.enabled = bool(settings.deepseek_api_key)
        self.client = None
        self.model = settings.deepseek_model

        # Maliyet takibi
        self.total_calls = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_agreements = 0
        self.total_disagreements = 0

        # DeepSeek fiyatları ($0.07/M input cache miss, $0.28/M output)
        self.input_cost_per_m = 0.27   # $0.27/M input (no cache)
        self.output_cost_per_m = 1.10  # $1.10/M output

        if self.enabled:
            self.client = OpenAI(
                api_key=settings.deepseek_api_key,
                base_url="https://api.deepseek.com",
            )
            logger.info("✅ DeepSeek validator hazır")
        else:
            logger.info("⚠️ DeepSeek API key yok — validation devre dışı")

    async def validate_signal(self, market: dict, claude_result: dict) -> dict:
        """
        Claude'un sinyalini DeepSeek ile doğrula.

        Returns:
            {
                "consensus": True/False,
                "deepseek_probability": 0.XX,
                "claude_probability": 0.XX,
                "direction_match": True/False,
                "confidence_avg": 0.XX,
                "recommendation": "TRADE" / "SKIP" / "REDUCE",
                "combined_probability": 0.XX,
                "api_cost": 0.XXX,
            }
        """
        if not self.enabled or not self.client:
            # DeepSeek yok → Claude'a güven
            return {
                "consensus": True,
                "deepseek_probability": claude_result["probability"],
                "claude_probability": claude_result["probability"],
                "direction_match": True,
                "confidence_avg": claude_result["confidence"],
                "recommendation": "TRADE",
                "combined_probability": claude_result["probability"],
                "api_cost": 0.0,
            }

        try:
            from datetime import datetime, timezone
            prompt = DEEPSEEK_PROMPT.format(
                question=market.get("question", ""),
                description=market.get("description", "")[:500],
                category=market.get("category", "general"),
                current_date=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                end_date=market.get("end_date", "Unknown"),
                volume=float(market.get("volume", 0)),
            )

            response = self.client.chat.completions.create(
                model=self.model,
                max_tokens=256,
                messages=[
                    {"role": "system", "content": DEEPSEEK_SYSTEM},
                    {"role": "user", "content": prompt},
                ],
            )

            # Token takibi
            self.total_input_tokens += response.usage.prompt_tokens
            self.total_output_tokens += response.usage.completion_tokens
            self.total_calls += 1

            text = response.choices[0].message.content.strip()
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            ds_result = json.loads(text)
            ds_prob = float(ds_result.get("probability", 0.5))
            ds_conf = float(ds_result.get("confidence", 0.5))
            ds_prob = max(0.0, min(1.0, ds_prob))
            ds_conf = max(0.0, min(1.0, ds_conf))

            claude_prob = claude_result["probability"]
            claude_conf = claude_result["confidence"]

            # API cost
            api_cost = (
                (response.usage.prompt_tokens / 1_000_000) * self.input_cost_per_m +
                (response.usage.completion_tokens / 1_000_000) * self.output_cost_per_m
            )

            # ---- Consensus Logic ----
            result = self._check_consensus(
                claude_prob, claude_conf, ds_prob, ds_conf,
                float(market.get("yes_price", 0.5))
            )
            result["api_cost"] = api_cost
            result["deepseek_reasoning"] = ds_result.get("reasoning", "")

            if result["consensus"]:
                self.total_agreements += 1
            else:
                self.total_disagreements += 1

            logger.info(
                f"🤖 DeepSeek: {ds_prob:.2f} (conf={ds_conf:.0%}) | "
                f"Claude: {claude_prob:.2f} | "
                f"Consensus: {'✅' if result['consensus'] else '❌'} → {result['recommendation']}"
            )

            return result

        except json.JSONDecodeError as e:
            logger.warning(f"DeepSeek yanıtı parse edilemedi: {e}")
            return self._fallback(claude_result)
        except Exception as e:
            logger.error(f"DeepSeek hatası: {e}")
            return self._fallback(claude_result)

    def _check_consensus(self, claude_p: float, claude_c: float,
                         ds_p: float, ds_c: float,
                         market_price: float) -> dict:
        """
        İki AI arasında consensus kontrolü.

        Aynı yön = consensus var
        Fark < %15 = güçlü consensus → TRADE
        Fark %15-30 = zayıf consensus → REDUCE (edge küçült)
        Farklı yön veya fark > %30 = consensus yok → SKIP
        """
        # Yön kontrolü (ikisi de aynı tarafta mı?)
        claude_direction = "YES" if claude_p > market_price else "NO"
        ds_direction = "YES" if ds_p > market_price else "NO"
        direction_match = claude_direction == ds_direction

        # Tahmin farkı
        prob_diff = abs(claude_p - ds_p)

        # Ağırlıklı ortalama (confidence bazlı)
        total_conf = claude_c + ds_c
        if total_conf > 0:
            combined = (claude_p * claude_c + ds_p * ds_c) / total_conf
        else:
            combined = (claude_p + ds_p) / 2

        avg_conf = (claude_c + ds_c) / 2

        if not direction_match:
            # İki AI farklı yönde → SKIP
            recommendation = "SKIP"
            consensus = False
        elif prob_diff <= 0.15:
            # Yakın tahminler → güçlü sinyal
            recommendation = "TRADE"
            consensus = True
        elif prob_diff <= 0.30:
            # Orta fark → trade ama dikkatli
            recommendation = "REDUCE"
            consensus = True
        else:
            # Çok farklı tahminler → riskli
            recommendation = "SKIP"
            consensus = False

        return {
            "consensus": consensus,
            "deepseek_probability": ds_p,
            "claude_probability": claude_p,
            "direction_match": direction_match,
            "confidence_avg": round(avg_conf, 4),
            "recommendation": recommendation,
            "combined_probability": round(combined, 4),
            "prob_difference": round(prob_diff, 4),
        }

    def _fallback(self, claude_result: dict) -> dict:
        """DeepSeek başarısız olursa Claude'a güven."""
        return {
            "consensus": True,
            "deepseek_probability": claude_result["probability"],
            "claude_probability": claude_result["probability"],
            "direction_match": True,
            "confidence_avg": claude_result["confidence"],
            "recommendation": "TRADE",
            "combined_probability": claude_result["probability"],
            "api_cost": 0.0,
        }

    @property
    def total_cost(self) -> float:
        inp = (self.total_input_tokens / 1_000_000) * self.input_cost_per_m
        out = (self.total_output_tokens / 1_000_000) * self.output_cost_per_m
        return inp + out

    def get_report(self) -> dict:
        return {
            "total_calls": self.total_calls,
            "agreements": self.total_agreements,
            "disagreements": self.total_disagreements,
            "agreement_rate": round(
                self.total_agreements / max(self.total_calls, 1), 4
            ),
            "total_cost": round(self.total_cost, 4),
        }
