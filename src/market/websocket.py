"""
WebSocket Client - Gerçek zamanlı fiyat ve order book güncellemeleri.
"""

import asyncio
import json
from typing import Callable, Optional
import websockets
from src.config import settings
from src.utils import logger


class MarketWebSocket:
    """Polymarket WebSocket - Real-time data streaming."""

    WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"

    def __init__(self):
        self._ws = None
        self._running = False
        self._callbacks: dict[str, list[Callable]] = {
            "price_change": [],
            "book_update": [],
            "trade": [],
        }
        self._subscribed_tokens: set[str] = set()
        self._reconnect_delay = 1  # saniye

    def on_price_change(self, callback: Callable):
        """Fiyat değişikliği callback'i ekle."""
        self._callbacks["price_change"].append(callback)

    def on_book_update(self, callback: Callable):
        """Order book güncellemesi callback'i ekle."""
        self._callbacks["book_update"].append(callback)

    def on_trade(self, callback: Callable):
        """Trade callback'i ekle."""
        self._callbacks["trade"].append(callback)

    async def subscribe(self, token_ids: list[str]):
        """Token'lara abone ol."""
        for token_id in token_ids:
            self._subscribed_tokens.add(token_id)

        if self._ws and not self._ws.closed:
            for token_id in token_ids:
                msg = json.dumps({
                    "type": "subscribe",
                    "channel": "market",
                    "assets_ids": [token_id],
                })
                await self._ws.send(msg)
                logger.debug(f"📡 WS Abone: {token_id[:8]}...")

    async def unsubscribe(self, token_ids: list[str]):
        """Token aboneliğini iptal et."""
        for token_id in token_ids:
            self._subscribed_tokens.discard(token_id)

        if self._ws and not self._ws.closed:
            for token_id in token_ids:
                msg = json.dumps({
                    "type": "unsubscribe",
                    "channel": "market",
                    "assets_ids": [token_id],
                })
                await self._ws.send(msg)

    async def connect(self):
        """WebSocket bağlantısını başlat."""
        self._running = True
        logger.info("🔌 WebSocket bağlantısı başlatılıyor...")

        while self._running:
            try:
                async with websockets.connect(
                    self.WS_URL,
                    ping_interval=30,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    self._ws = ws
                    self._reconnect_delay = 1
                    logger.info("✅ WebSocket bağlantısı kuruldu")

                    # Mevcut abonelikleri yenile
                    if self._subscribed_tokens:
                        await self.subscribe(list(self._subscribed_tokens))

                    # Mesajları dinle
                    async for message in ws:
                        await self._handle_message(message)

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(f"⚠️ WebSocket bağlantısı kapandı: {e}")
            except Exception as e:
                logger.error(f"❌ WebSocket hatası: {e}")

            if self._running:
                logger.info(f"🔄 {self._reconnect_delay}s sonra yeniden bağlanılacak...")
                await asyncio.sleep(self._reconnect_delay)
                self._reconnect_delay = min(self._reconnect_delay * 2, 60)

    async def _handle_message(self, raw_message: str):
        """Gelen WebSocket mesajını işle."""
        try:
            data = json.loads(raw_message)
            msg_type = data.get("type", "")

            if msg_type == "price_change":
                for cb in self._callbacks["price_change"]:
                    await self._safe_call(cb, data)
            elif msg_type in ("book", "book_update"):
                for cb in self._callbacks["book_update"]:
                    await self._safe_call(cb, data)
            elif msg_type == "last_trade_price":
                for cb in self._callbacks["trade"]:
                    await self._safe_call(cb, data)
        except json.JSONDecodeError:
            logger.warning(f"⚠️ Geçersiz WS mesajı: {raw_message[:100]}")
        except Exception as e:
            logger.error(f"❌ WS mesaj işleme hatası: {e}")

    @staticmethod
    async def _safe_call(callback: Callable, data: dict):
        """Callback'i güvenli şekilde çağır."""
        try:
            if asyncio.iscoroutinefunction(callback):
                await callback(data)
            else:
                callback(data)
        except Exception as e:
            logger.error(f"❌ Callback hatası: {e}")

    async def disconnect(self):
        """WebSocket bağlantısını kapat."""
        self._running = False
        if self._ws and not self._ws.closed:
            await self._ws.close()
        logger.info("🔌 WebSocket bağlantısı kapatıldı")
