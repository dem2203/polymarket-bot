"""
Telegram Notifications — Trade, rapor ve hata bildirimleri.
"""

import logging
from typing import Optional

import aiohttp

from src.config import settings

logger = logging.getLogger("bot.telegram")


class TelegramNotifier:
    """Telegram Bot API ile bildirim gönderici."""

    def __init__(self):
        self.token = settings.telegram_bot_token
        self.chat_id = settings.telegram_chat_id
        self.enabled = settings.has_telegram
        self.api_url = f"https://api.telegram.org/bot{self.token}"

    async def send(self, message: str, parse_mode: str = "HTML"):
        """Telegram mesajı gönder."""
        if not self.enabled:
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.api_url}/sendMessage",
                    json={
                        "chat_id": self.chat_id,
                        "text": message[:4000],
                        "parse_mode": parse_mode,
                        "disable_web_page_preview": True,
                    },
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status != 200:
                        logger.warning(f"Telegram yanıt: {resp.status}")
        except Exception as e:
            logger.warning(f"Telegram gönderme hatası: {e}")

    async def notify_bot_started(self, balance: float, dry_run: bool):
        """Bot başladı bildirimi."""
        mode = "🔵 DRY RUN" if dry_run else "🟢 LIVE"
        github_status = "✅" if settings.github_token and settings.github_repo else "❌"
        
        await self.send(
            f"⚔️ <b>WARRIOR BOT V3.5 BAŞLADI</b>\n\n"
            f"Mod: {mode}\n"
            f"Bakiye: <b>${balance:.2f}</b>\n"
            f"AI: {settings.ai_model}\n"
            f"GitHub Memory: {github_status}\n"
            f"🛡️ Health Monitor: ✅\n"
            f"Tarama: {settings.scan_interval}s ({settings.scan_interval // 60} dk)\n"
            f"Mispricing: >{settings.mispricing_threshold:.0%} (Warrior)\n"
            f"Kelly: {settings.kelly_multiplier}x (Max %{settings.max_kelly_fraction*100:.0f})\n"
            f"Stop-Loss: %{settings.stop_loss_pct*100:.0f} | TP: %{settings.take_profit_pct*100:.0f}"
        )

    async def notify_trade_opened(self, signal):
        """Trade açıldı bildirimi."""
        await self.send(
            f"📊 <b>YENİ TRADE</b>\n\n"
            f"Market: {signal.question[:80]}\n"
            f"Yön: <b>{signal.direction}</b>\n"
            f"AI Fair Value: {signal.fair_value:.2f}\n"
            f"Market Fiyat: ${signal.market_price:.3f}\n"
            f"Edge: <b>{signal.edge:.1%}</b>\n"
            f"Pozisyon: <b>${signal.position_size:.2f}</b>\n"
            f"Kelly: {signal.kelly_fraction:.2%}\n"
            f"AI Gerekçe: <i>{signal.reasoning}</i>\n"
            f"Güven: {signal.confidence:.0%}"
        )

    async def notify_trade_closed(self, closed):
        """Trade kapatıldı bildirimi."""
        emoji = "🟢" if closed.realized_pnl >= 0 else "🔴"
        await self.send(
            f"{emoji} <b>TRADE KAPANDI</b>\n\n"
            f"Market: {closed.question[:80]}\n"
            f"Giriş: ${closed.entry_price:.3f} → Çıkış: ${closed.exit_price:.3f}\n"
            f"PnL: <b>${closed.realized_pnl:+.2f}</b> ({closed.pnl_pct:+.1%})\n"
            f"Süre: {closed.hold_time / 3600:.1f} saat"
        )

    async def notify_stop_loss(self, position):
        """Stop-loss tetiklendi bildirimi."""
        await self.send(
            f"🛑 <b>STOP-LOSS TETİKLENDİ</b>\n\n"
            f"Market: {position.question[:80]}\n"
            f"Giriş: ${position.entry_price:.3f}\n"
            f"Mevcut: ${position.current_price:.3f}\n"
            f"PnL: <b>${position.unrealized_pnl:.2f}</b> ({position.pnl_pct:.1%})"
        )

    async def notify_survival_mode(self, balance: float):
        """Hayatta kalma modu bildirimi."""
        await self.send(
            f"💀 <b>HAYATTA KALMA MODU AKTİF</b>\n\n"
            f"Bakiye: <b>${balance:.2f}</b>\n"
            f"Eşik: ${settings.survival_balance:.2f}\n\n"
            f"⚠️ Tüm işlemler durduruldu!\n"
            f"Bakiye artana kadar bot bekleme modunda."
        )

    async def notify_scan_report(self, report: dict):
        """Tarama raporu bildirimi."""
        failures = report.get('failures', 0)
        last_error = report.get('last_error', '')
        error_line = f"\n⚠️ AI Hata: {failures} | Son: {last_error[:100]}" if failures > 0 else ""

        await self.send(
            f"📡 <b>TARAMA RAPORU</b>\n\n"
            f"Taranan market: {report.get('scanned', 0)}\n"
            f"Filtreyi geçen: {report.get('filtered', 0)}\n"
            f"AI analiz edilen: {report.get('analyzed', 0)}\n"
            f"Sinyal bulunan: {report.get('signals', 0)}\n"
            f"Trade açılan: {report.get('trades', 0)}\n"
            f"API maliyeti: ${report.get('api_cost', 0):.4f}"
            f"{error_line}"
        )

    async def notify_economics_report(self, report: str):
        """Ekonomi raporu bildirimi."""
        await self.send(f"<pre>{report}</pre>")

    async def notify_error(self, error: str):
        """Hata bildirimi."""
        await self.send(f"⚠️ <b>HATA</b>\n\n<code>{error[:500]}</code>")

    # ==================== V3.5: HEALTH & SAFETY ALERTS ====================
    
    async def send_critical_alert(self, title: str, message: str):
        """
        CRITICAL alert - Emergency situations requiring immediate attention.
        
        Examples: Negative cash, monitoring failures, balance sanity failures.
        """
        alert_message = (
            f"🚨🚨🚨 <b>{title}</b> 🚨🚨🚨\n\n"
            f"{message}\n\n"
            f"⚠️ This is a CRITICAL alert requiring immediate attention."
        )
        await self.send(alert_message)
        
    async def send_warning_alert(self, title: str, message: str):
        """
        WARNING alert - Degraded functionality or suspicious activity.
        
        Examples: Idle trading, degraded monitoring, unexpected patterns.
        """
        alert_message = (
            f"⚠️ <b>{title}</b>\n\n"
            f"{message}"
        )
        await self.send(alert_message)
        
    async def send_message(self, message: str):
        """
        Generic message - Info, dashboards, regular updates.
        
        Examples: Health dashboard, activity reports.
        """
        await self.send(message, parse_mode="Markdown")
