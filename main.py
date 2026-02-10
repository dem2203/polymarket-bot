"""
Polymarket Professional Trading Bot - Ana Giriş Noktası
Otonom trading loop: market tarama → strateji → risk → emir yürütme → izleme
"""

import asyncio
import signal
import sys
from datetime import datetime, timedelta
from typing import Optional

from src.config import settings
from src.utils import logger
from src.wallet.auth import PolymarketAuth
from src.wallet.manager import WalletManager
from src.market.gamma_client import GammaClient
from src.market.clob_client import ClobManager
from src.trading.strategy import StrategyEngine, SignalType
from src.trading.order_manager import OrderManager, OrderStatus
from src.trading.position_tracker import PositionTracker
from src.trading.risk_manager import RiskManager
from src.notifications.telegram import TelegramNotifier


class PolymarketBot:
    """Profesyonel Polymarket Trading Bot."""

    def __init__(self):
        # Core
        self.auth = PolymarketAuth()
        self.wallet = WalletManager(self.auth)
        self.gamma = GammaClient()
        self.clob = ClobManager(self.auth)

        # Trading engine
        self.strategy_engine = StrategyEngine()
        self.order_manager = OrderManager(self.auth)
        self.position_tracker = PositionTracker()
        self.risk_manager = RiskManager(self.position_tracker)

        # Notifications
        self.telegram = TelegramNotifier()

        # State
        self._running = False
        self._last_report_time = datetime.now()
        self._report_interval = timedelta(hours=6)  # 6 saatte bir rapor

    async def start(self):
        """Botu başlat."""
        logger.info("=" * 60)
        logger.info("🤖 POLYMARKET PROFESSIONAL TRADING BOT")
        logger.info("=" * 60)

        mode = "🧪 DRY RUN" if settings.dry_run else "🔴 LIVE TRADING"
        logger.info(f"📊 Mod: {mode}")
        logger.info(f"💰 Max Emir: ${settings.max_order_size} | Max Exposure: ${settings.max_total_exposure}")
        logger.info(f"🛑 Stop-Loss: {settings.stop_loss_pct:.0%} | 🎯 Take-Profit: {settings.take_profit_pct:.0%}")

        # Bağlantı kontrolü
        if not settings.has_credentials:
            logger.error("❌ Private key yapılandırılmamış! .env dosyasını kontrol edin.")
            sys.exit(1)

        if not await self._verify_connection():
            logger.error("❌ Polymarket bağlantısı kurulamadı!")
            sys.exit(1)

        # Telegram bildirimi
        await self.telegram.notify_bot_started()

        # Trading loop
        self._running = True
        logger.info(f"🔄 Trading loop başlıyor | Tarama aralığı: {settings.scan_interval}s")

        while self._running:
            try:
                await self._trading_cycle()
                await self._check_positions()
                await self._send_periodic_report()
                await asyncio.sleep(settings.scan_interval)
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"❌ Trading döngüsü hatası: {e}")
                await self.telegram.notify_error(f"Trading döngüsü hatası: {str(e)[:200]}")
                await asyncio.sleep(30)  # Hata durumunda 30s bekle

        await self.shutdown()

    async def _verify_connection(self) -> bool:
        """Bağlantı ve wallet durumunu doğrula."""
        logger.info("🔌 Bağlantı doğrulanıyor...")

        try:
            connected = self.auth.verify_connection()
            if not connected:
                return False

            # Wallet durumu
            health = self.wallet.get_health_report()
            logger.info(
                f"💰 Wallet: Bakiye=${health['balance']:.2f} | "
                f"Allowance=${health['allowance']:.2f} | "
                f"Trading Hazır: {'✅' if health['ready_to_trade'] else '❌'}"
            )

            # Allowance yoksa ayarla
            if health["balance"] > 0 and health["allowance"] == 0:
                logger.info("🔧 Allowance ayarlanıyor...")
                self.wallet.setup_allowances()

            return True
        except Exception as e:
            logger.error(f"❌ Bağlantı doğrulama hatası: {e}")
            return False

    async def _trading_cycle(self):
        """Ana trading döngüsü: Tara → Analiz → Trade."""
        logger.info("━" * 40)
        logger.info(f"🔍 Market taraması başlıyor... [{datetime.now().strftime('%H:%M:%S')}]")

        # 1. Tradeable marketleri al
        markets = self.gamma.get_tradeable_markets()
        if not markets:
            logger.info("📭 Trading için uygun market bulunamadı")
            return

        # 2. Her market için strateji analizi
        signals_evaluated = 0
        trades_executed = 0

        for market in markets:
            try:
                # Token ID'lerini al
                tokens = market.get("tokens", [])
                if isinstance(tokens, list) and len(tokens) > 0:
                    # CLOB token çiftinin YES tarafını kullan
                    if isinstance(tokens[0], dict):
                        token_id = tokens[0].get("token_id", "")
                    else:
                        token_id = str(tokens[0])
                elif isinstance(tokens, str):
                    token_id = tokens
                else:
                    continue

                if not token_id:
                    continue

                # Market snapshot al
                snapshot = self.clob.get_market_snapshot(token_id)
                if snapshot["price"] <= 0:
                    continue

                signals_evaluated += 1

                # Strateji sinyali al
                signal = self.strategy_engine.get_best_signal(
                    market, snapshot, min_confidence=settings.min_confidence
                )

                if not signal:
                    continue

                # Risk kontrolü
                approved, reason, size = self.risk_manager.approve_trade(signal)
                if not approved:
                    logger.debug(f"⛔ Trade reddedildi: {reason}")
                    continue

                # Emir gönder
                signal.suggested_size = size
                order = self.order_manager.execute_signal(signal, size)

                if order and order.status in (OrderStatus.PLACED, OrderStatus.FILLED, OrderStatus.SIMULATED):
                    trades_executed += 1
                    # Pozisyon aç
                    position = self.position_tracker.open_position(order)
                    # Telegram bildirimi
                    await self.telegram.notify_trade_opened(order, position)

            except Exception as e:
                logger.error(f"❌ Market analiz hatası [{market.get('question', '')[:40]}]: {e}")
                continue

        logger.info(
            f"📊 Tarama tamamlandı: {len(markets)} market | "
            f"{signals_evaluated} analiz | {trades_executed} trade"
        )

    async def _check_positions(self):
        """Açık pozisyonları kontrol et - stop-loss / take-profit."""
        positions = self.position_tracker.get_open_positions()
        if not positions:
            return

        logger.debug(f"🔍 {len(positions)} açık pozisyon kontrol ediliyor...")

        for pos in positions:
            try:
                # Güncel fiyatı al
                current_price = self.clob.get_price(pos.token_id)
                if current_price <= 0:
                    continue

                pos.update_price(current_price)

                # Stop-loss kontrolü
                if self.risk_manager.check_stop_loss(pos.token_id, current_price, pos.entry_price):
                    closed = self.position_tracker.close_position(pos.token_id, current_price)
                    if closed:
                        self.risk_manager.record_trade_result(closed.realized_pnl)
                        await self.telegram.notify_stop_loss(closed)
                    continue

                # Take-profit kontrolü
                if self.risk_manager.check_take_profit(pos.token_id, current_price, pos.entry_price):
                    closed = self.position_tracker.close_position(pos.token_id, current_price)
                    if closed:
                        self.risk_manager.record_trade_result(closed.realized_pnl)
                        await self.telegram.notify_take_profit(closed)

            except Exception as e:
                logger.error(f"❌ Pozisyon kontrol hatası [{pos.token_id[:8]}...]: {e}")

    async def _send_periodic_report(self):
        """Periyodik durum raporu gönder."""
        now = datetime.now()
        if now - self._last_report_time < self._report_interval:
            return

        self._last_report_time = now

        portfolio = self.position_tracker.get_portfolio_summary()
        risk = self.risk_manager.get_risk_report()
        order_stats = self.order_manager.get_stats()

        await self.telegram.notify_daily_report(portfolio, risk, order_stats)
        logger.info("📊 Periyodik rapor gönderildi")

    async def shutdown(self):
        """Bot'u güvenli şekilde kapat."""
        logger.info("🛑 Bot kapatılıyor...")
        self._running = False

        # Açık emirleri iptal et
        open_orders = self.order_manager.get_open_orders()
        if open_orders:
            logger.info(f"🚫 {len(open_orders)} açık emir iptal ediliyor...")
            self.order_manager.cancel_all_orders()

        # Son rapor gönder
        portfolio = self.position_tracker.get_portfolio_summary()
        risk = self.risk_manager.get_risk_report()
        order_stats = self.order_manager.get_stats()
        await self.telegram.notify_daily_report(portfolio, risk, order_stats)

        # Telegram session kapat
        await self.telegram.close()

        logger.info("✅ Bot güvenli şekilde kapatıldı")


# ---- Health Check HTTP Server ----
async def health_check_handler(reader, writer):
    """Basit health check endpoint (Railway için)."""
    request = await reader.read(1024)
    response = (
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        "Connection: close\r\n\r\n"
        '{"status":"ok","service":"polymarket-bot"}'
    )
    writer.write(response.encode())
    await writer.drain()
    writer.close()


async def start_health_server(port: int = 8080):
    """Health check server başlat."""
    try:
        server = await asyncio.start_server(health_check_handler, "0.0.0.0", port)
        logger.info(f"🌐 Health check server: http://0.0.0.0:{port}")
        return server
    except Exception as e:
        logger.warning(f"⚠️ Health check server başlatılamadı: {e}")
        return None


# ---- Entry Point ----
async def main():
    """Ana giriş noktası."""
    # Health check server (Railway için)
    health_server = await start_health_server()

    # Bot başlat
    bot = PolymarketBot()

    # Graceful shutdown
    def handle_signal(signum, frame):
        logger.info(f"📡 Sinyal alındı: {signum}")
        bot._running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        await bot.start()
    finally:
        if health_server:
            health_server.close()
            await health_server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
