"""
AI Prompt Templates — Claude'a gönderilen promptlar.
Her prompt, marketi analiz edip 0-1 arası fair value döndürmeye odaklı.
"""

FAIR_VALUE_SYSTEM = """You are a professional prediction market analyst.
Your ONLY job: estimate the TRUE probability (0.00 to 1.00) that a given prediction market question resolves YES.

Rules:
- Output ONLY a JSON object: {"probability": 0.XX, "confidence": 0.XX, "reasoning": "brief reason"}
- probability: your estimated fair value (0.00 to 1.00)
- confidence: how confident you are in your estimate (0.50 = uncertain, 0.95 = very confident)
- reasoning: 1 sentence max
- Consider the question carefully, the current date, any context provided
- Be calibrated: if you truly don't know, output probability close to 0.50 with low confidence
- Do NOT add any other text outside the JSON"""

FAIR_VALUE_PROMPT = """Prediction Market Analysis:

Question: {question}
Description: {description}
Category: {category}
Current Market Price (YES): ${yes_price:.2f}
Current Market Price (NO): ${no_price:.2f}
End Date: {end_date}
Current Date: {current_date}
24h Volume: ${volume:,.0f}

Analyze this market and estimate the TRUE probability of YES outcome.
Output ONLY the JSON object."""

BATCH_ANALYSIS_PROMPT = """Analyze these {count} prediction markets. For EACH, estimate true probability.

Output a JSON array of objects, one per market:
[{{"market_id": "...", "probability": 0.XX, "confidence": 0.XX, "reasoning": "..."}}]

Markets:
{markets_text}

Output ONLY the JSON array, no other text."""
