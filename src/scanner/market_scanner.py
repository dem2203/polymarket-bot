"""
Market Scanner — Gamma API ile 500-1000 market tarayıcı.
Hacim, likidite, spread filtrelerini uygular.
Kategorilere ayırır (crypto, sports, weather, politics).
"""

import logging
from typing import Optional

import aiohttp

from src.config import settings

logger = logging.getLogger("bot.scanner")

# Bilinen kategori etiketleri
CATEGORY_TAGS = {
    "crypto": ["crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "defi", "token", "blockchain"],
    "sports": ["sports", "nfl", "nba", "soccer", "football", "tennis", "mma", "ufc", "baseball", "mlb"],
    "weather": ["weather", "temperature", "hurricane", "storm", "climate", "noaa"],
    "politics": ["politics", "election", "president", "congress", "senate", "vote", "trump", "biden"],
}


class MarketScanner:
    """Polymarket Gamma API ile market tarama motoru."""

    def __init__(self):
        self.gamma_url = settings.gamma_api_url
        self.min_volume = settings.min_volume
        self.min_liquidity = settings.min_liquidity
        self.max_markets = settings.max_markets_per_scan

    async def scan_all_markets(self) -> list[dict]:
        """
        Tüm aktif marketleri tara ve filtrele.
        500-1000 market kapasiteli.
        """
        all_markets = []
        offset = 0
        limit = 100  # Gamma API sayfa limiti

        async with aiohttp.ClientSession() as session:
            while len(all_markets) < self.max_markets:
                try:
                    params = {
                        "limit": limit,
                        "offset": offset,
                        "active": "true",
                        "closed": "false",
                        "order": "volume24hr",
                        "ascending": "false",
                    }
                    
                    async with session.get(
                        f"{self.gamma_url}/markets", params=params, timeout=aiohttp.ClientTimeout(total=30)
                    ) as resp:
                        if resp.status != 200:
                            logger.warning(f"Gamma API yanıt: {resp.status}")
                            break
                        
                        markets = await resp.json()
                        
                        if not markets:
                            break
                        
                        all_markets.extend(markets)
                        offset += limit
                        
                        if len(markets) < limit:
                            break

                except aiohttp.ClientError as e:
                    logger.error(f"Gamma API bağlantı hatası: {e}")
                    break
                except Exception as e:
                    logger.error(f"Market tarama hatası: {e}")
                    break

        logger.info(f"📡 Toplam {len(all_markets)} market tarandı")
        
        # Filtrele
        filtered = self._apply_filters(all_markets)
        logger.info(f"✅ {len(filtered)} market filtreyi geçti (hacim>${self.min_volume}, likidite>${self.min_liquidity})")
        
        return filtered

    def _apply_filters(self, markets: list[dict]) -> list[dict]:
        """Hacim, likidite ve spread filtreleri uygula."""
        filtered = []
        
        for m in markets:
            try:
                volume = float(m.get("volume24hr", m.get("volume", 0)) or 0)
                liquidity = float(m.get("liquidity", 0) or 0)
                
                # Hacim filtresi
                if volume < self.min_volume:
                    continue
                
                # Likidite filtresi
                if liquidity < self.min_liquidity:
                    continue

                # Token bilgisi olmalı
                tokens = m.get("clobTokenIds", m.get("tokens", []))
                if not tokens:
                    continue

                # Fiyat bilgisi
                yes_price = self._extract_price(m, "yes")
                no_price = self._extract_price(m, "no")
                
                if yes_price <= 0.01 or yes_price >= 0.99:
                    continue  # Çok aşırı fiyatlar — edge yok

                # Spread kontrolü
                spread = abs(1.0 - yes_price - no_price)

                # Kategori tespiti
                category = self._detect_category(m)

                filtered.append({
                    "id": m.get("conditionId", m.get("id", "")),
                    "question": m.get("question", ""),
                    "description": m.get("description", "")[:500],
                    "category": category,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "spread": spread,
                    "volume": volume,
                    "liquidity": liquidity,
                    "end_date": m.get("endDate", m.get("end_date_iso", "Unknown")),
                    "tokens": tokens if isinstance(tokens, list) else tokens.split(","),
                    "slug": m.get("slug", ""),
                    "raw": m,  # Ham veri (gerekirse)
                })

            except (ValueError, TypeError, KeyError) as e:
                continue

        # Hacme göre sırala (en yüksek önce)
        filtered.sort(key=lambda x: x["volume"], reverse=True)
        return filtered

    def _extract_price(self, market: dict, side: str) -> float:
        """Market'ten YES veya NO fiyatını çıkar."""
        # Farklı API formatlarını destekle
        if side == "yes":
            price = market.get("outcomePrices")
            if price:
                try:
                    if isinstance(price, str):
                        import json
                        prices = json.loads(price)
                        return float(prices[0]) if prices else 0.5
                    elif isinstance(price, list):
                        return float(price[0]) if price else 0.5
                except (json.JSONDecodeError, IndexError, ValueError):
                    pass

            price = market.get("bestAsk", market.get("lastTradePrice", 0.5))
            return float(price) if price else 0.5
        else:  # no
            yes_price = self._extract_price(market, "yes")
            price = market.get("outcomePrices")
            if price:
                try:
                    if isinstance(price, str):
                        import json
                        prices = json.loads(price)
                        return float(prices[1]) if len(prices) > 1 else (1.0 - yes_price)
                    elif isinstance(price, list):
                        return float(price[1]) if len(price) > 1 else (1.0 - yes_price)
                except (json.JSONDecodeError, IndexError, ValueError):
                    pass

            return 1.0 - yes_price

    def _detect_category(self, market: dict) -> str:
        """Market kategorisini tespit et."""
        text = (
            market.get("question", "") + " " +
            market.get("description", "") + " " +
            " ".join(market.get("tags", []) or [])
        ).lower()

        for category, keywords in CATEGORY_TAGS.items():
            for kw in keywords:
                if kw in text:
                    return category

        return "general"

    async def get_market_details(self, condition_id: str) -> Optional[dict]:
        """Tek bir market'in detaylı bilgisini getir."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.gamma_url}/markets/{condition_id}",
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        return await resp.json()
        except Exception as e:
            logger.error(f"Market detay hatası: {e}")
        return None
