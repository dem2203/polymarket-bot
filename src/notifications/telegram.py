"""
Telegram Notifier - İşlem bildirimleri, PnL raporları, hata uyarıları.
"""

import asyncio
from datetime import datetime
from typing import Optional
import aiohttp
from src.config import settings
from src.trading.order_manager import Order
from src.trading.position_tracker import Position
from src.utils import logger


class TelegramNotifier:
    """Telegram bildirim sistemi."""

    BASE_URL = "https://api.telegram.org/bot{token}"

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.enabled = settings.has_telegram
        self._session: Optional[aiohttp.ClientSession] = None

        if not self.enabled:
            logger.warning("⚠️ Telegram yapılandırılmamış, bildirimler devre dışı")

    async def _get_session(self) -> aiohttp.ClientSession:
        if not self._session or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def send_message(self, text: str, parse_mode: str = "HTML") -> bool:
        """Telegram mesajı gönder."""
        if not self.enabled:
            return False

        try:
            session = await self._get_session()
            url = f"{self.BASE_URL.format(token=self.token)}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    return True
                else:
                    body = await resp.text()
                    logger.error(f"❌ Telegram API hatası [{resp.status}]: {body}")
                    return False
        except Exception as e:
            logger.error(f"❌ Telegram mesaj gönderme hatası: {e}")
            return False

    def send_message_sync(self, text: str) -> bool:
        """Senkron mesaj gönderme (async olmayan context'ler için)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self.send_message(text))
                return True
            else:
                return loop.run_until_complete(self.send_message(text))
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(self.send_message(text))
            return result

    # ---- Mesaj Şablonları ----

    async def notify_bot_started(self):
        """Bot başlatma bildirimi."""
        mode = "🧪 DRY RUN" if settings.dry_run else "🔴 LIVE TRADING"
        msg = (
            f"🤖 <b>Polymarket Bot Başlatıldı</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Mod: {mode}\n"
            f"💰 Max Emir: ${settings.max_order_size:.0f}\n"
            f"🏦 Max Exposure: ${settings.max_total_exposure:.0f}\n"
            f"🛑 Stop-Loss: {settings.stop_loss_pct:.0%}\n"
            f"🎯 Take-Profit: {settings.take_profit_pct:.0%}\n"
            f"📈 Min Güven: {settings.min_confidence:.0%}\n"
            f"⏱ Tarama Aralığı: {settings.scan_interval}s\n"
            f"🕐 Zaman: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await self.send_message(msg)

    async def notify_trade_opened(self, order: Order, position: Position):
        """Trade açılış bildirimi."""
        mode = "🧪" if settings.dry_run else "💰"
        msg = (
            f"{mode} <b>YENİ POZİSYON AÇILDI</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 {order.market_question[:80]}\n"
            f"{'🟢 ALIŞ' if order.side == 'BUY' else '🔴 SATIŞ'}\n"
            f"💵 Büyüklük: ${order.size:.2f}\n"
            f"📊 Fiyat: {order.price:.4f}\n"
            f"🧠 Strateji: {order.strategy_name}\n"
            f"📈 Güven: {order.signal_confidence:.0%}\n"
            f"📝 Neden: {order.reason}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(msg)

    async def notify_trade_closed(self, position: Position, reason: str = ""):
        """Trade kapanış bildirimi."""
        pnl_emoji = "🟢" if position.realized_pnl >= 0 else "🔴"
        msg = (
            f"{pnl_emoji} <b>POZİSYON KAPANDI</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📋 {position.market_question[:80]}\n"
            f"📊 Giriş: {position.entry_price:.4f} → Çıkış: {position.current_price:.4f}\n"
            f"💰 PnL: ${position.realized_pnl:+.2f} ({position.pnl_pct:+.1%})\n"
            f"📝 Neden: {reason}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(msg)

    async def notify_stop_loss(self, position: Position):
        """Stop-loss tetiklenme bildirimi."""
        await self.notify_trade_closed(position, reason="🛑 STOP-LOSS TETİKLENDİ")

    async def notify_take_profit(self, position: Position):
        """Take-profit tetiklenme bildirimi."""
        await self.notify_trade_closed(position, reason="🎯 TAKE-PROFIT TETİKLENDİ")

    async def notify_daily_report(self, portfolio: dict, risk: dict, order_stats: dict):
        """Günlük performans raporu."""
        msg = (
            f"📊 <b>GÜNLÜK RAPOR</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"📈 Açık Pozisyon: {portfolio.get('open_positions', 0)}\n"
            f"💰 Yatırım: ${portfolio.get('total_invested', 0):.2f}\n"
            f"📊 Unrealized PnL: ${portfolio.get('unrealized_pnl', 0):+.2f}\n"
            f"✅ Realized PnL: ${portfolio.get('realized_pnl', 0):+.2f}\n"
            f"🏆 Win Rate: {portfolio.get('win_rate', 0):.0%}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"🛡 Günlük PnL: ${risk.get('daily_pnl', 0):+.2f}\n"
            f"📊 Exposure: ${risk.get('total_exposure', 0):.2f} / ${risk.get('max_exposure', 0):.2f}\n"
            f"🔢 Bugünkü İşlemler: {risk.get('trades_today', 0)}\n"
            f"📦 Toplam Emirler: {order_stats.get('total_orders', 0)}\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await self.send_message(msg)

    async def notify_error(self, error_msg: str):
        """Hata bildirimi."""
        msg = (
            f"🚨 <b>HATA</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"{error_msg}\n"
            f"🕐 {datetime.now().strftime('%H:%M:%S')}"
        )
        await self.send_message(msg)

    async def close(self):
        """Session'ı kapat."""
        if self._session and not self._session.closed:
            await self._session.close()
