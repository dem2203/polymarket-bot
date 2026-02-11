"""
Polymarket AI Trading Bot V2 — Main Orchestrator
=================================================
Her 10 dakikada:
  1. 500-1000 market tara (Gamma API)
  2. Claude AI ile fair value hesapla
  3. >%8 mispricing tespit et
  4. Kelly Criterion ile pozisyon büyüklüğü belirle
  5. Risk kontrolünden geçir
  6. Limit emir gönder (veya simüle et)
  7. Pozisyonları izle (SL/TP)
  8. Telegram'dan bildir
  9. Ekonomi raporu güncelle

Bakiye $5'in altına düşerse → bot durur (hayatta kalma modu).
"""

import asyncio
import logging
import signal
import sys
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from rich.logging import RichHandler

from src.config import settings
from src.ai.brain import AIBrain
from src.scanner.market_scanner import MarketScanner
from src.strategy.kelly import KellySizer
from src.strategy.mispricing import MispricingStrategy
from src.strategy.arbitrage import ArbitrageStrategy
from src.trading.executor import TradeExecutor
from src.trading.positions import PositionTracker
from src.trading.risk import RiskManager
from src.economics.tracker import EconomicsTracker
from src.notifications.telegram import TelegramNotifier

# Log dosyası dizini — MUST be before FileHandler
import os
os.makedirs("logs", exist_ok=True)

# ---- Logging Setup ----
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        RichHandler(rich_tracebacks=True, show_path=False),
        logging.FileHandler("logs/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("bot")


# ---- Health Check Server ----
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"alive","bot":"polymarket-ai-v2"}')

    def log_message(self, *args):
        pass  # Sessiz


def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"🏥 Health check: http://0.0.0.0:{port}")


# ---- Bot Class ----
class PolymarketBot:
    """Ana bot orkestrasyonu."""

    def __init__(self):
        # Modüller
        self.brain = AIBrain()
        self.scanner = MarketScanner()
        self.kelly = KellySizer()
        self.strategy = MispricingStrategy(self.brain, self.kelly)
        self.arbitrage = ArbitrageStrategy()
        self.executor = TradeExecutor()
        self.positions = PositionTracker()
        self.risk = RiskManager()
        self.economics = EconomicsTracker(settings.starting_balance)
        self.telegram = TelegramNotifier()

        # Durum
        self.running = True
        self.cycle_count = 0
        self.balance = settings.starting_balance

    async def start(self):
        """Bot'u başlat."""
        logger.info("=" * 60)
        logger.info("🤖 POLYMARKET AI TRADING BOT V2")
        logger.info("=" * 60)
        logger.info(f"Mod: {'🔵 DRY RUN' if settings.dry_run else '🟢 LIVE'}")
        logger.info(f"AI: {settings.ai_model}")
        logger.info(f"Bakiye: ${self.balance:.2f}")
        logger.info(f"Mispricing eşik: >{settings.mispricing_threshold:.0%}")
        logger.info(f"Kelly cap: %{settings.max_kelly_fraction*100:.0f}")
        logger.info(f"Hayatta kalma eşiği: ${settings.survival_balance:.2f}")
        logger.info(f"Tarama aralığı: {settings.scan_interval // 60} dakika")
        logger.info("=" * 60)

        # Ön kontroller
        if not settings.has_anthropic_key:
            logger.error("❌ ANTHROPIC_API_KEY ayarlanmamış!")
            await self.telegram.send("❌ ANTHROPIC_API_KEY ayarlanmamış! Bot duruyor.")
            return

        # AI Health Check
        logger.info("🧠 AI Health Check yapılıyor...")
        health = self.brain.health_check()
        if health["ok"]:
            logger.info(f"✅ AI hazır: {health['model']} — {health['response']}")
            await self.telegram.send(
                f"✅ <b>AI Health Check BAŞARILI</b>\n"
                f"Model: {health['model']}\n"
                f"Yanıt: {health['response']}"
            )
        else:
            logger.error(f"❌ AI HATA: {health['error']}")
            await self.telegram.send(
                f"❌ <b>AI Health Check BAŞARISIZ!</b>\n"
                f"Model: {health['model']}\n"
                f"Hata: <code>{health['error'][:500]}</code>\n\n"
                f"⚠️ Bot çalışmaya devam edecek ama AI analiz yapılamayacak!"
            )

        # Bakiye sorgula
        self.balance = self.executor.get_balance()
        logger.info(f"💰 Mevcut bakiye: ${self.balance:.2f}")

        # Telegram bildirim
        await self.telegram.notify_bot_started(self.balance, settings.dry_run)

        # Ana döngü
        while self.running:
            try:
                await self._trading_cycle()

                # Bekleme
                logger.info(f"⏳ {settings.scan_interval // 60} dakika bekleniyor...\n")
                for _ in range(settings.scan_interval):
                    if not self.running:
                        break
                    await asyncio.sleep(1)

            except Exception as e:
                logger.error(f"❌ Döngü hatası: {e}", exc_info=True)
                await self.telegram.notify_error(str(e))
                await asyncio.sleep(60)

        logger.info("👋 Bot kapatıldı.")

    async def _trading_cycle(self):
        """Tek bir trading döngüsü (10 dakikada bir)."""
        self.cycle_count += 1
        cycle_start = time.time()
        logger.info(f"\n{'='*50}")
        logger.info(f"🔄 DÖNGÜ #{self.cycle_count} — {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
        logger.info(f"{'='*50}")

        # Bakiye güncelle
        self.balance = self.executor.get_balance()

        # HAYATTA KALMA kontrolü
        if self.balance <= settings.survival_balance:
            logger.warning(f"💀 HAYATTA KALMA MODU! Bakiye: ${self.balance:.2f}")
            await self.telegram.notify_survival_mode(self.balance)
            return

        # 1. Market tarama
        logger.info("📡 Marketler taranıyor...")
        markets = await self.scanner.scan_all_markets()

        if not markets:
            logger.warning("⚠️ Hiç market bulunamadı")
            return

        # 2. Arbitraj kontrolü (hızlı, AI gerektirmez)
        arb_signals = self.arbitrage.detect(markets, self.balance)
        if arb_signals:
            logger.info(f"🔄 {len(arb_signals)} arbitraj fırsatı bulundu")

        # 3. AI-powered mispricing analizi
        # Zaten pozisyon olan marketleri çıkar
        markets_to_analyze = [
            m for m in markets if not self.positions.has_position(m["id"])
        ]

        # En fazla 30-50 market analiz et (API maliyet optimizasyonu)
        max_analyze = min(50, len(markets_to_analyze))
        markets_to_analyze = markets_to_analyze[:max_analyze]

        logger.info(f"🧠 {max_analyze} market AI ile analiz ediliyor...")
        pre_cost = self.brain.total_api_cost

        signals = await self.strategy.scan_for_signals(
            markets_to_analyze, self.balance, max_signals=5
        )

        post_cost = self.brain.total_api_cost
        cycle_api_cost = post_cost - pre_cost
        self.economics.record_api_cost(cycle_api_cost, max_analyze)

        # 4. Her sinyal için risk kontrolü ve emir yürütme
        trades_executed = 0

        for signal in signals:
            # Risk kontrolü
            allowed, reason = self.risk.is_trade_allowed(
                signal=signal,
                balance=self.balance,
                total_exposure=self.positions.total_exposure,
                open_positions=len(self.positions.open_positions),
            )

            if not allowed:
                logger.info(f"⛔ Reddedildi: {reason}")
                continue

            # Emir yürüt
            order = await self.executor.execute_signal(signal)
            if order:
                self.positions.open_position(order)
                self.risk.record_trade()
                await self.telegram.notify_trade_opened(signal)
                trades_executed += 1

        # 5. Pozisyon izleme (SL/TP)
        if self.positions.open_positions:
            await self._monitor_positions()

        # 6. Döngü raporu
        cycle_time = time.time() - cycle_start
        ai_report = self.brain.get_cost_report()
        report = {
            "scanned": len(markets) if markets else 0,
            "filtered": len(markets_to_analyze),
            "analyzed": self.brain.total_api_calls,
            "signals": len(signals),
            "trades": trades_executed,
            "api_cost": cycle_api_cost,
            "failures": ai_report["total_failures"],
            "last_error": ai_report["last_error"],
        }

        logger.info(
            f"📊 Döngü #{self.cycle_count} tamamlandı ({cycle_time:.1f}s) | "
            f"Sinyal: {len(signals)} | Trade: {trades_executed} | "
            f"API: ${cycle_api_cost:.4f} | Hata: {ai_report['total_failures']}"
        )

        # Her 6 döngüde ekonomi raporu (1 saat)
        if self.cycle_count % 6 == 0:
            eco_report = self.economics.format_report(self.balance)
            logger.info(f"\n{eco_report}")
            await self.telegram.notify_economics_report(eco_report)

        # Her döngü özet raporu Telegram'a
        await self.telegram.notify_scan_report(report)

    async def _monitor_positions(self):
        """Açık pozisyonları izle — SL/TP kontrolü."""
        # Basitleştirilmiş fiyat güncelleme
        # Gerçek implementasyonda: CLOB API'den güncel fiyat çekilir
        market_prices = {}

        for market_id, position in self.positions.open_positions.items():
            try:
                # Market fiyatını güncelleme
                # DRY_RUN modunda sabit tutuyoruz
                if settings.dry_run:
                    market_prices[market_id] = position.entry_price
                else:
                    # Gerçek fiyat al
                    detail = await self.scanner.get_market_details(market_id)
                    if detail:
                        prices = detail.get("outcomePrices", "")
                        if prices:
                            import json
                            price_list = json.loads(prices) if isinstance(prices, str) else prices
                            if position.token_side == "YES":
                                market_prices[market_id] = float(price_list[0])
                            else:
                                market_prices[market_id] = float(price_list[1]) if len(price_list) > 1 else 1.0 - float(price_list[0])
            except Exception as e:
                logger.debug(f"Fiyat güncelleme hatası {market_id}: {e}")

        # SL/TP kontrol
        to_close = self.positions.check_stop_loss_take_profit(market_prices)

        for market_id in to_close:
            position = self.positions.open_positions.get(market_id)
            if position:
                await self.telegram.notify_stop_loss(position)
                current_price = market_prices.get(market_id, position.current_price)
                closed = self.positions.close_position(market_id, current_price)
                if closed:
                    self.economics.record_trade_pnl(closed.realized_pnl)
                    self.risk.record_trade(closed.realized_pnl)
                    await self.telegram.notify_trade_closed(closed)

    def shutdown(self, signum=None, frame=None):
        """Graceful shutdown."""
        logger.info("🛑 Shutdown sinyali alındı...")
        self.running = False


async def main():
    """Entry point."""
    # Health check (Railway için) — ÖNCE başlat, bot init uzun sürebilir
    start_health_server()

    bot = PolymarketBot()

    # Graceful shutdown
    signal.signal(signal.SIGINT, bot.shutdown)
    signal.signal(signal.SIGTERM, bot.shutdown)

    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
