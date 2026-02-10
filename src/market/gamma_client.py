"""
Gamma API Client - Market keşfi, metadata, event bilgileri.
https://gamma-api.polymarket.com
"""

import requests
from typing import Optional
from src.config import settings
from src.utils import logger


class GammaClient:
    """Polymarket Gamma API - Market keşfi ve metadata."""

    def __init__(self):
        self.base_url = settings.gamma_api_url
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "User-Agent": "PolymarketBot/1.0",
        })

    def get_markets(
        self,
        limit: int = 100,
        offset: int = 0,
        active: bool = True,
        closed: bool = False,
        order: str = "volume24hr",
        ascending: bool = False,
    ) -> list[dict]:
        """Aktif marketleri listele ve filtrele."""
        try:
            params = {
                "limit": limit,
                "offset": offset,
                "active": str(active).lower(),
                "closed": str(closed).lower(),
                "order": order,
                "ascending": str(ascending).lower(),
            }
            resp = self.session.get(f"{self.base_url}/markets", params=params, timeout=15)
            resp.raise_for_status()
            markets = resp.json()
            logger.info(f"📊 {len(markets)} market alındı (Gamma API)")
            return markets
        except Exception as e:
            logger.error(f"❌ Gamma API market listesi hatası: {e}")
            return []

    def get_market(self, condition_id: str) -> Optional[dict]:
        """Tek bir market'in detaylarını getir."""
        try:
            resp = self.session.get(
                f"{self.base_url}/markets/{condition_id}", timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"❌ Market detay hatası [{condition_id}]: {e}")
            return None

    def get_events(self, limit: int = 50, active: bool = True) -> list[dict]:
        """Aktif event'leri listele."""
        try:
            params = {
                "limit": limit,
                "active": str(active).lower(),
            }
            resp = self.session.get(f"{self.base_url}/events", params=params, timeout=15)
            resp.raise_for_status()
            events = resp.json()
            logger.info(f"📅 {len(events)} event alındı")
            return events
        except Exception as e:
            logger.error(f"❌ Event listesi hatası: {e}")
            return []

    def search_markets(
        self,
        query: str = "",
        tag: str = "",
        min_volume: float = 0,
        min_liquidity: float = 0,
    ) -> list[dict]:
        """Marketleri filtrele - hacim, likidite, tag bazlı."""
        markets = self.get_markets(limit=200)
        filtered = []
        for m in markets:
            # Query filtresi
            if query:
                question = (m.get("question") or "").lower()
                description = (m.get("description") or "").lower()
                if query.lower() not in question and query.lower() not in description:
                    continue

            # Tag filtresi
            if tag:
                tags = m.get("tags") or []
                if tag.lower() not in [t.lower() for t in tags]:
                    continue

            # Hacim filtresi
            volume = float(m.get("volume", 0) or 0)
            if volume < min_volume:
                continue

            # Likidite filtresi
            liquidity = float(m.get("liquidity", 0) or 0)
            if liquidity < min_liquidity:
                continue

            filtered.append(m)

        logger.info(f"🔍 Arama sonucu: {len(filtered)} market bulundu")
        return filtered

    def get_tradeable_markets(self) -> list[dict]:
        """Trading için uygun marketleri getir (likidite ve hacim filtrelemeli)."""
        markets = self.get_markets(limit=200, active=True)
        tradeable = []

        for m in markets:
            # Temel filtreleme
            liquidity = float(m.get("liquidity", 0) or 0)
            volume = float(m.get("volume24hr", 0) or 0)

            if liquidity < settings.min_liquidity:
                continue

            # Token bilgisi kontrolü
            tokens = m.get("tokens") or m.get("clobTokenIds")
            if not tokens:
                continue

            tradeable.append({
                "condition_id": m.get("conditionId") or m.get("condition_id", ""),
                "question": m.get("question", ""),
                "slug": m.get("slug", ""),
                "liquidity": liquidity,
                "volume_24h": volume,
                "end_date": m.get("endDate") or m.get("end_date_iso", ""),
                "tokens": tokens,
                "outcome_prices": m.get("outcomePrices", ""),
                "best_bid": m.get("bestBid", 0),
                "best_ask": m.get("bestAsk", 0),
                "spread": m.get("spread", 0),
                "raw": m,  # Orijinal data'yı sakla
            })

        logger.info(f"✅ {len(tradeable)} tradeable market bulundu (min liq: ${settings.min_liquidity})")
        return tradeable
