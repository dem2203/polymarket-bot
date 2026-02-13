"""
Crypto Price Validator - Hızlı kripto fiyat doğrulama.

Uses CoinGecko API (Free, fast, reliable)
- Aggressive caching (10 min for crypto prices)
- Parallel async requests
- Automatic price extraction from AI reasoning
- >10% error = REJECT trade
"""

import re
import logging
import aiohttp
from typing import Optional, Dict

from src.data.validators.base import BaseValidator

logger = logging.getLogger("bot.validators.crypto")


class CryptoValidator(BaseValidator):
    """Validate crypto price assumptions in AI reasoning."""
    
    COINGECKO_API = "https://api.coingecko.com/api/v3"
    
    # Crypto ID mapping
    CRYPTO_MAP = {
        "bitcoin": "bitcoin",
        "btc": "bitcoin",
        "ethereum": "ethereum",
        "eth": "ethereum",
        "solana": "solana",
        "sol": "solana",
    }
    
    def __init__(self):
        # 10 minute cache for crypto (prices don't change that fast for our purposes)
        super().__init__(cache_ttl=600)
    
    async def get_price(self, crypto_id: str) -> Optional[float]:
        """
        Get current crypto price in USD.
        
        Args:
            crypto_id: CoinGecko ID (e.g. 'bitcoin', 'ethereum')
            
        Returns:
            Price in USD or None if failed
        """
        # Check cache first
        cached = self._get_from_cache(crypto_id)
        if cached is not None:
            return cached
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.COINGECKO_API}/simple/price"
                params = {"ids": crypto_id, "vs_currencies": "usd"}
                
                async with session.get(
                    url, 
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=self.api_timeout)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        price = data.get(crypto_id, {}).get("usd")
                        
                        if price:
                            self._set_cache(crypto_id, price)
                            logger.info(f"✅ {crypto_id.upper()} price: ${price:,.2f}")
                            return price
        except Exception as e:
            logger.warning(f"CoinGecko API error for {crypto_id}: {e}")
        
        return None
    
    def _extract_price_from_text(self, text: str) -> Optional[float]:
        """
        Extract price from AI reasoning.
        
        Patterns matched:
        - $52,000
        - $52000
        - 52k
        - 52K
        - around $50,000
        """
        patterns = [
            r'\$[\d,]+(?:\.\d{2})?',  # $52,000 or $52,000.00
            r'([\d,]+)k',              # 52k (thousands)
            r'([\d,]+)',               # Plain numbers (last resort)
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    # Clean and parse
                    if isinstance(match, tuple):
                        match = match[0] if match[0] else match[1]
                    
                    price_str = str(match).replace('$', '').replace(',', '')
                    
                    # Handle 'k' suffix
                    if 'k' in text[text.find(price_str):text.find(price_str)+10].lower():
                        price = float(price_str) * 1000
                    else:
                        price = float(price_str)
                    
                    # Sanity check (reasonable crypto price range)
                    if 0.01 < price < 1_000_000:
                        return price
                except (ValueError, AttributeError):
                    continue
        
        return None
    
    def _detect_crypto(self, text: str) -> Optional[str]:
        """Detect which crypto is mentioned in text."""
        text_lower = text.lower()
        
        for keyword, crypto_id in self.CRYPTO_MAP.items():
            if keyword in text_lower:
                return crypto_id
        
        return None
    
    async def validate(self, question: str, reasoning: str, market: dict) -> dict:
        """
        Validate crypto price assumptions.
        
        Returns:
            {
                "valid": bool,
                "confidence": float,
                "warning": str | None,
                "details": {
                    "crypto": str,
                    "ai_price": float,
                    "actual_price": float,
                    "error_pct": float
                }
            }
        """
        combined_text = f"{question} {reasoning}"
        
        # 1. Detect crypto mention
        crypto_id = self._detect_crypto(combined_text)
        if not crypto_id:
            return {"valid": True, "confidence": 1.0, "warning": None, "details": {}}
        
        # 2. Extract AI's price assumption
        ai_price = self._extract_price_from_text(reasoning)
        if not ai_price:
            # Crypto mentioned but no price in reasoning → allow (can't validate)
            logger.debug(f"Crypto '{crypto_id}' mentioned but no price in reasoning")
            return {"valid": True, "confidence": 0.8, "warning": None, "details": {}}
        
        # 3. Get actual price
        actual_price = await self.get_price(crypto_id)
        if not actual_price:
            # API failed → fallback: allow trade (don't block on API failure)
            logger.warning(f"⚠️ Could not fetch {crypto_id} price - allowing trade")
            return {"valid": True, "confidence": 0.6, "warning": "Price API unavailable"}
        
        # 4. Calculate error
        error_pct = abs(actual_price - ai_price) / actual_price
        
        # 5. Validate
        if error_pct > 0.10:  # >10% error
            warning = (
                f"🚨 AI PRICE ERROR: {crypto_id.upper()}\n"
                f"AI thinks: ${ai_price:,.0f}\n"
                f"Actually: ${actual_price:,.0f}\n"
                f"Error: {error_pct:.1%}"
            )
            logger.error(warning)
            return {
                "valid": False,
                "confidence": 0.0,
                "warning": warning,
                "details": {
                    "crypto": crypto_id,
                    "ai_price": ai_price,
                    "actual_price": actual_price,
                    "error_pct": error_pct
                }
            }
        
        # Price is accurate enough
        logger.info(f"✅ {crypto_id.upper()} price validated (error: {error_pct:.1%})")
        return {
            "valid": True,
            "confidence": 1.0 - error_pct,  # Confidence decreases with error
            "warning": None,
            "details": {
                "crypto": crypto_id,
                "ai_price": ai_price,
                "actual_price": actual_price,
                "error_pct": error_pct
            }
        }
