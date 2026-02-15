"""
Market Scanner — WARRIOR Edition.
Akıllı ön-filtreleme: Sona yakın, iyi fiyatlı, yüksek hacimli marketlere odaklan.
50 rastgele market yerine EN İYİ 10 marketi AI'a gönder.
"""

import logging
import json
from datetime import datetime, timezone
from typing import Optional

import aiohttp

from src.config import settings

logger = logging.getLogger("bot.scanner")

# Bilinen kategori etiketleri — öncelik sırasına göre
CATEGORY_TAGS = {
    "sports": ["sports", "nfl", "nba", "soccer", "football", "tennis", "mma", "ufc", "baseball", "mlb",
               "hockey", "nhl", "boxing", "f1", "formula", "racing", "cricket", "rugby"],
    "crypto": ["crypto", "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "defi", "token", "blockchain",
               "price", "market cap"],
    "weather": ["weather", "temperature", "hurricane", "storm", "climate", "noaa", "rain", "snow", "heat"],
    "politics": ["politics", "election", "president", "congress", "senate", "vote", "trump", "biden",
                 "poll", "approval", "legislation"],
}

# Kategori öncelik puanları (daha yüksek = daha iyi)
CATEGORY_PRIORITY = {
    "sports": 10,    # Net sonuçlar, tahmin edilebilir
    "weather": 8,    # NOAA verisi var, net
    "crypto": 6,     # Volatil ama tahmin edilebilir trendler
    "politics": 4,   # Anketler var ama belirsiz
    "general": 2,    # En düşük öncelik
}


class MarketScanner:
    """Polymarket Gamma API ile AKILLI market tarama motoru."""

    def __init__(self):
        self.gamma_url = settings.gamma_api_url
        self.min_volume = settings.min_volume
        self.min_liquidity = settings.min_liquidity
        self.max_markets = settings.max_markets_per_scan
        
        # ⛔ BLACKLIST: Kumar ve Yüksek Riskli Marketler
        # Bu kelimeleri içeren marketler ASLA taranmayacak.
        self.BLACKLIST_KEYWORDS = [
            "up or down",      # Binary gambling (Coin flip)
            "above", "below",  # Short term technicals
            "tweet", "mention", "post", # Social media noise
            "will elon",       # Musk gambling
            "daily",           # Too short term
            "february 14",     # Specific daily expirations (Example)
        ]

    async def scan_all_markets(self, skip_filters: bool = False) -> list[dict]:
        """
        Tüm aktif marketleri tara.
        skip_filters=True ise ham listeyi döndür (Sync için gerekli).
        """
        all_markets = []
        offset = 0
        limit = 100

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

        if skip_filters:
            return all_markets

        # Filtrele
        filtered = self._apply_filters(all_markets)
        logger.info(f"✅ {len(filtered)} market filtreyi geçti")

        # WARRIOR: Akıllı sıralama — en iyi hedefler üste
        scored = self._score_and_rank(filtered)
        logger.info(f"⚔️ {len(scored)} market puanlandı ve sıralandı")

        return scored

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

                # ⛔ BLACKLIST CHECK (V4.4 FIX)
                # Soru metni veya description içinde yasaklı kelime var mı?
                text_content = (m.get("question", "") + " " + m.get("description", "")).lower()
                is_blacklisted = False
                for kw in self.BLACKLIST_KEYWORDS:
                    if kw in text_content:
                        is_blacklisted = True
                        # logger.debug(f"⛔ Blacklisted ({kw}): {m.get('question', '')[:30]}...")
                        break
                
                if is_blacklisted:
                    continue

                # Token parse logic
                tokens = m.get("clobTokenIds", m.get("tokens", []))

                if isinstance(tokens, str):
                    try:
                        tokens = json.loads(tokens)
                    except json.JSONDecodeError:
                        tokens = tokens.split(",")

                if not tokens:
                    continue

                # Clean tokens
                tokens = [str(t).strip().replace('"', '').replace("'", "") for t in tokens]

                # Fiyat bilgisi
                yes_price = self._extract_price(m, "yes")
                no_price = self._extract_price(m, "no")

                if yes_price <= 0.01 or yes_price >= 0.99:
                    continue  # Çok aşırı fiyatlar — edge yok

                # Spread kontrolü
                spread = abs(1.0 - yes_price - no_price)

                # Kategori tespiti
                category = self._detect_category(m)

                # Bitiş zamanı hesapla
                hours_to_expiry = self._hours_to_expiry(m)

                # V4.0: Hız Limiti (Max Duration)
                # Eğer vade çok uzunsa (örn. >60 gün), direkt ele.
                max_hours = settings.max_days_to_expiry * 24
                if hours_to_expiry > max_hours:
                    # logger.debug(f"⏳ Market çok uzak vadeli: {hours_to_expiry/24:.1f} gün")
                    continue

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
                    "hours_to_expiry": hours_to_expiry,
                    "tokens": tokens if isinstance(tokens, list) else tokens.split(","),
                    "slug": m.get("slug", ""),
                    "raw": m,
                })

            except (ValueError, TypeError, KeyError):
                continue

        return filtered


    def get_market_from_token_map(self, markets: list[dict]) -> dict:
        """
        Token ID -> Market bilgilerini eşleyen bir harita oluştur.
        Startup Sync için kullanılır.
        """
        token_map = {}
        for m in markets:
            # Extract Token IDs
            tokens = m.get("clobTokenIds", m.get("tokens", []))
            
            if isinstance(tokens, str):
                try:
                    tokens = json.loads(tokens)
                except:
                    tokens = tokens.split(",")
            
            if not tokens:
                continue
                
            # Clean tokens
            tokens = [str(t).strip().replace('"', '').replace("'", "") for t in tokens]
            
            # Map YES (0) and NO (1) tokens
            if len(tokens) > 0:
                token_map[tokens[0]] = {
                    "market_id": m.get("conditionId", m.get("id")),
                    "question": m.get("question"),
                    "token_side": "YES",
                    "tokens": tokens
                }
            if len(tokens) > 1:
                token_map[tokens[1]] = {
                    "market_id": m.get("conditionId", m.get("id")),
                    "question": m.get("question"),
                    "token_side": "NO",
                    "tokens": tokens
                }
                
        return token_map


    def _score_and_rank(self, markets: list[dict]) -> list[dict]:
        """
        ⚔️ WARRIOR SCORING — Her markete puan ver, en iyi hedefler üste.

        Scoring:
        - Near expiry (24-72h): +30 puan
        - Sweet spot price (0.15-0.35 or 0.65-0.85): +20 puan
        - High volume: +15 puan
        - Category priority: +10 puan
        - Extreme price (0.05-0.15 or 0.85-0.95): +10 puan (potential moonshot)
        """
        for m in markets:
            score = 0
            yes_price = m["yes_price"]
            hours = m.get("hours_to_expiry", 9999)

            # 1. TIME SCORE — yakın biten eventler çok değerli
            if 0 < hours <= 24:
                score += 50  # 24h: ULTRA VELOCITY (Anında döngü) 🚀
            elif 24 < hours <= 72:
                score += 40  # 3 gün: Yüksek Hız
            elif 72 < hours <= 168:
                score += 25  # 1 hafta: İdeal
            elif 168 < hours <= 720: # 30 gün
                score += 10  # Orta vade
            elif hours > 1080: # 45 gün+
                score -= 20  # Ceza: Para bağlanmasın (sadece çok iyi fiyat varsa girer)


            # 2. PRICE SCORE — sweet spot fiyatlar (büyük hareket potansiyeli)
            if 0.15 <= yes_price <= 0.35 or 0.65 <= yes_price <= 0.85:
                score += 20  # Sweet spot — büyük edge potansiyeli
            elif 0.05 <= yes_price < 0.15 or 0.85 < yes_price <= 0.95:
                score += 10  # Extreme — moonshot potansiyeli
            elif 0.35 < yes_price < 0.65:
                score += 5   # Orta — düşük edge

            # 3. VOLUME SCORE — yüksek hacim = güvenilir fiyat
            volume = m.get("volume", 0)
            if volume > 100000:
                score += 15
            elif volume > 50000:
                score += 10
            elif volume > 20000:
                score += 5

            # 4. MOMENTUM SCORE (V3.4) — Volume/Liquidity Ratio
            # Yüksek ciro / Düşük likidite = Fiyat patlamaya hazır (High Mobility)
            liquidity = m.get("liquidity", 0) or 1
            volume = m.get("volume", 0) or 0
            turnover = volume / liquidity if liquidity > 100 else 0
            
            if turnover > 20: 
                score += 25  # 🚀 ROCKET: Çok yüksek devir (Haber geldi muhtemelen)
            elif turnover > 10:
                score += 15  # 🔥 HOT: Yüksek devir
            elif turnover > 5:
                score += 5   # ⚡ ACTIVE

            # 5. CATEGORY SCORE
            category = m.get("category", "general")
            score += CATEGORY_PRIORITY.get(category, 2)

            m["warrior_score"] = score
            m["momentum_label"] = "🚀" if turnover > 20 else ("🔥" if turnover > 10 else "-")

        # Sıralama: En yüksek skor ilk
        markets.sort(key=lambda x: x.get("warrior_score", 0), reverse=True)

        # Top skorları logla
        for m in markets[:5]:
            logger.info(
                f"🎯 Score={m['warrior_score']:3d} {m.get('momentum_label', '-')} | "
                f"{'⏰' if m.get('hours_to_expiry', 9999) < 72 else '📅'} "
                f"{m.get('hours_to_expiry', '?'):.0f}h | "
                f"${m['yes_price']:.2f} | {m['category'][:6]} | "
                f"{m['question'][:50]}..."
            )

        return markets

    def _hours_to_expiry(self, market: dict) -> float:
        """Market'in bitiş tarihine kaç saat kaldığını hesapla."""
        end_date_str = market.get("endDate", market.get("end_date_iso", ""))
        if not end_date_str or end_date_str == "Unknown":
            return 9999  # Bilinmiyor — düşük öncelik

        try:
            # ISO format parse
            end_date_str = str(end_date_str).replace("Z", "+00:00")
            if "T" in end_date_str:
                end_date = datetime.fromisoformat(end_date_str)
            else:
                end_date = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            delta = end_date - now
            hours = delta.total_seconds() / 3600

            return max(0, hours)  # Negatif olamaz
        except Exception:
            return 9999

    def _extract_price(self, market: dict, side: str) -> float:
        """Market'ten YES veya NO fiyatını çıkar."""
        if side == "yes":
            price = market.get("outcomePrices")
            if price:
                try:
                    if isinstance(price, str):
                        prices = json.loads(price)
                        return float(prices[0]) if prices else 0.5
                    elif isinstance(price, list):
                        return float(price[0]) if price else 0.5
                except (json.JSONDecodeError, IndexError, ValueError):
                    pass

            price = market.get("bestAsk", market.get("lastTradePrice", 0.5))
            return float(price) if price else 0.5
        else:
            yes_price = self._extract_price(market, "yes")
            price = market.get("outcomePrices")
            if price:
                try:
                    if isinstance(price, str):
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
