"""
Telegram Remote Control - Uzaktan bot kontrolü.

Commands:
  /status - Sağlık durumu
  /stop - Acil durdur
  /resume - Devam et
  /balance - Bakiye
  /positions - Açık pozisyonlar
  /help - Yardım
"""

import logging
import time
from datetime import datetime, timezone

logger = logging.getLogger("bot.telegram_commands")


class TelegramCommandHandler:
    """Telegram komutlarını işle - remote bot control."""
    
    def __init__(self, bot_instance, telegram_notifier):
        """
        Args:
            bot_instance: Ana PolymarketBot instance
            telegram_notifier: TelegramNotifier instance
        """
        self.bot = bot_instance
        self.telegram = telegram_notifier
        self.enabled = telegram_notifier.enabled
        
        # Command registry
        self.commands = {
            "/status": self._cmd_status,
            "/stop": self._cmd_stop,
            "/resume": self._cmd_resume,
            "/balance": self._cmd_balance,
            "/positions": self._cmd_positions,
            "/help": self._cmd_help,
        }
        
        logger.info(f"✅ Telegram commands ready: {list(self.commands.keys())}")
        
    async def _cmd_status(self) -> str:
        """Bot sağlık durumu."""
        try:
            # Health score
            health_score = self.bot.health_monitor.calculate_health_score(
                self.bot.balance
            )
            emoji, status_text = self.bot.health_monitor.get_health_status(health_score)
            
            # Uptime
            uptime_sec = time.time() - self.bot.start_time
            uptime_hours = uptime_sec / 3600
            
            # Last trade
            last_trade = "Never"
            if self.bot.health_monitor.metrics.last_trade_time:
                delta = datetime.now(timezone.utc) - self.bot.health_monitor.metrics.last_trade_time
                minutes = delta.total_seconds() / 60
                if minutes < 60:
                    last_trade = f"{int(minutes)} min ago"
                else:
                    last_trade = f"{minutes/60:.1f}h ago"
            
            return (
                f"🤖 <b>BOT STATUS</b> {emoji}\n\n"
                f"Health: {health_score:.0f}/100\n"
                f"Status: {status_text}\n"
                f"Running: {'✅ Yes' if self.bot.running else '🛑  Stopped'}\n"
                f"Uptime: {uptime_hours:.1f}h\n"
                f"Cycle: #{self.bot.cycle_count}\n"
                f"Last Trade: {last_trade}\n"
                f"Trades Today: {self.bot.health_monitor.metrics.trades_today}"
            )
        except Exception as e:
            logger.error(f"Status command error: {e}")
            return f"❌ Error getting status: {e}"
    
    async def _cmd_stop(self) -> str:
        """Acil durdur - all trading halt."""
        self.bot.running = False
        logger.critical("🛑 EMERGENCY STOP via Telegram /stop command")
        
        return (
            "🛑 <b>EMERGENCY STOP ACTIVATED</b>\n\n"
            "✅ All trading halted\n"
            "✅ No new positions will open\n"
            "⚠️ Existing positions remain open\n\n"
            "Commands:\n"
            "/resume - Restart trading\n"
            "/positions - View open positions"
        )
    
    async def _cmd_resume(self) -> str:
        """Trading'i devam ettir."""
        was_running = self.bot.running
        self.bot.running = True
        
        if was_running:
            return "ℹ️ Bot was already running"
        
        logger.info("▶️ Trading RESUMED via Telegram /resume command")
        return (
            "▶️ <b>TRADING RESUMED</b>\n\n"
            "✅ Bot restarted\n"
            "✅ Will resume normal operations\n\n"
            "Use /status to check health"
        )
    
    async def _cmd_balance(self) -> str:
        """Bakiye ve portfolio."""
        try:
            positions_value = sum(
                p.shares * p.entry_price 
                for p in self.bot.positions.open_positions.values()
            )
            total_value = self.bot.balance + positions_value
            
            return (
                f"💰 <b>BALANCE & PORTFOLIO</b>\n\n"
                f"Cash: <b>${self.bot.balance:.2f}</b>\n"
                f"Open Positions: {len(self.bot.positions.open_positions)}\n"
                f"Positions Value: ${positions_value:.2f}\n"
                f"Total: <b>${total_value:.2f}</b>"
            )
        except Exception as e:
            logger.error(f"Balance command error: {e}")
            return f"❌ Error: {e}"
    
    async def _cmd_positions(self) -> str:
        """Açık pozisyonları listele."""
        if not self.bot.positions.open_positions:
            return "ℹ️ No open positions"
        
        try:
            positions_list = []
            for i, (market_id, pos) in enumerate(
                list(self.bot.positions.open_positions.items())[:10],  # Max 10
                1
            ):
                emoji = "🟢" if pos.unrealized_pnl >= 0 else "🔴"
                positions_list.append(
                    f"{i}. {emoji} {pos.question[:35]}...\n"
                    f"   Entry: ${pos.entry_price:.3f} | "
                    f"PnL: {pos.pnl_pct:+.1%}"
                )
            
            if len(self.bot.positions.open_positions) > 10:
                positions_list.append(f"\n... and {len(self.bot.positions.open_positions) - 10} more")
            
            return (
                f"📊 <b>OPEN POSITIONS ({len(self.bot.positions.open_positions)})</b>\n\n"
                + "\n\n".join(positions_list)
            )
        except Exception as e:
            logger.error(f"Positions command error: {e}")
            return f"❌ Error: {e}"
    
    async def _cmd_help(self) -> str:
        """Komut listesi."""
        return (
            "🤖 <b>REMOTE CONTROL COMMANDS</b>\n\n"
            "/status - Bot health check\n"
            "/stop - Emergency stop trading\n"
            "/resume - Resume trading\n"
            "/balance - Current balance\n"
            "/positions - List open positions\n"
            "/help - This message"
        )
    
    async def handle_command(self, command: str) -> str:
        """
        Handle incoming command.
        
        Args:
            command: Command string (e.g. "/status")
            
        Returns:
            Response message
        """
        command = command.strip().lower()
        
        logger.info(f"📱 Telegram command received: {command}")
        
        if command in self.commands:
            handler = self.commands[command]
            try:
                response = await handler()
                logger.info(f"✅ Command {command} executed successfully")
                return response
            except Exception as e:
                logger.error(f"❌ Command {command} failed: {e}")
                return f"❌ Error executing {command}: {e}"
        
        return (
            f"❌ Unknown command: {command}\n\n"
            "Use /help to see available commands"
        )
