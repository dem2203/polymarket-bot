"""
Polymarket AI Trading Bot V3 — Self-Learning Orchestrator
=========================================================
V3 Yenilikler:
  - Performance Tracker: Trade geçmişinden öğrenme
  - Adaptive Kelly: Win rate'e göre dinamik pozisyon boyutu
  - Trade Journal: AI self-review (her 12 saat)
  - DeepSeek Validator: Dual-AI consensus doğrulama

Bot $5 altına düşerse durur (hayatta kalma).
Kazandıkça agresifleşir, kaybettikçe temkinleşir.
"""

import asyncio
import logging
import signal
import sys
import time
import os
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from rich.logging import RichHandler

from src.config import settings
from src.ai.brain import AIBrain
from src.ai.deepseek_validator import DeepSeekValidator
from src.scanner.market_scanner import MarketScanner
from src.strategy.kelly import KellySizer
from src.strategy.mispricing import MispricingStrategy
from src.strategy.arbitrage import ArbitrageStrategy
from src.trading.executor import TradeExecutor
from src.trading.positions import PositionTracker
from src.trading.risk import RiskManager
from src.economics.tracker import EconomicsTracker
from src.notifications.telegram import TelegramNotifier
from src.learning.performance_tracker import PerformanceTracker
from src.learning.adaptive_kelly import AdaptiveKelly
from src.learning.trade_journal import TradeJournal

# Log + data dizinleri
os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)

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
        self.wfile.write(b'{"status":"alive","bot":"polymarket-ai-v3"}')

    def log_message(self, *args):
        pass


def start_health_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info(f"Health check: http://0.0.0.0:{port}")


# ---- Bot Class ----
class PolymarketBot:
    """V3 Ana bot — self-learning + dual-AI."""

    def __init__(self):
        # Core modüller
        self.brain = AIBrain()
        self.deepseek = DeepSeekValidator()
        self.scanner = MarketScanner()
        self.kelly = KellySizer()
        self.strategy = MispricingStrategy(self.brain, self.kelly, self.deepseek)
        self.arbitrage = ArbitrageStrategy()
        self.executor = TradeExecutor()
        self.positions = PositionTracker()
        self.risk = RiskManager()
        self.economics = EconomicsTracker(settings.starting_balance)
        self.telegram = TelegramNotifier()

        # V3: Learning modüller
        self.perf_tracker = PerformanceTracker()
        self.adaptive_kelly = AdaptiveKelly()
        self.journal = TradeJournal(self.perf_tracker)

        # Durum
        self.running = True
        self.cycle_count = 0
        self.balance = settings.starting_balance

    async def start(self):
        """Bot'u başlat."""
        logger.info("=" * 60)
        logger.info("🤖 POLYMARKET AI TRADING BOT V3 — SELF-LEARNING")
        logger.info("=" * 60)
        logger.info(f"Mod: {'🔵 DRY RUN' if settings.dry_run else '🟢 LIVE'}")
        logger.info(f"AI: {settings.ai_model}")
        logger.info(f"DeepSeek: {'✅ aktif' if self.deepseek.enabled else '❌ devre dışı'}")
        logger.info(f"Learning: {'✅ aktif' if settings.enable_self_learning else '❌ devre dışı'}")
        logger.info(f"Bakiye: ${self.balance:.2f}")
        logger.info(f"Mispricing eşik: >{settings.mispricing_threshold:.0%}")
        logger.info(f"Kelly cap: %{settings.max_kelly_fraction*100:.0f}")
        logger.info(f"Hayatta kalma: ${settings.survival_balance:.2f}")
        logger.info(f"Trade geçmişi: {len(self.perf_tracker.trades)} trade yüklendi")
        logger.info("=" * 60)

        # API kontrolleri
        if not settings.has_anthropic_key:
            logger.error("ANTHROPIC_API_KEY ayarlanmamış!")
            await self.telegram.send("❌ ANTHROPIC_API_KEY yok! Bot duruyor.")
            return

        # AI Health Check
        logger.info("AI Health Check...")
        health = self.brain.health_check()
        if health["ok"]:
            logger.info(f"✅ AI hazır: {health['model']}")
        else:
            logger.error(f"❌ AI HATA: {health['error']}")

        # Bakiye sorgula
        self.balance = self.executor.get_balance()

        # Learning state yükle
        if settings.enable_self_learning:
            stats = self.perf_tracker.get_stats()
            self.adaptive_kelly.update_from_stats(stats)
            perf_context = self.perf_tracker.get_performance_context()
            self.strategy.set_performance_context(perf_context)
            logger.info(f"📊 Adaptive Kelly: {self.adaptive_kelly.get_report()}")

        # Başlangıç bildirimi
        await self.telegram.send(
            f"🤖 <b>POLYMARKET AI BOT V3 BAŞLADI</b>\n\n"
            f"Mod: {'🔵 DRY RUN' if settings.dry_run else '🟢 LIVE'}\n"
            f"Bakiye: ${self.balance:.2f}\n"
            f"AI: {settings.ai_model}\n"
            f"DeepSeek: {'✅' if self.deepseek.enabled else '❌'}\n"
            f"Learning: {'✅' if settings.enable_self_learning else '❌'}\n"
            f"Trade geçmişi: {len(self.perf_tracker.trades)} trade\n"
            f"Kelly: {self.adaptive_kelly.global_multiplier:.2f}\n"
            f"Tarama: Her {settings.scan_interval // 60} dk\n"
            f"Mispricing eşik: >{settings.mispricing_threshold:.0%}\n"
            f"Kelly cap: %{settings.max_kelly_fraction*100:.0f}\n"
            f"Stop-Loss: %{settings.stop_loss_pct*100:.0f} | TP: %{settings.take_profit_pct*100:.0f}"
        )

        # Ana döngü
        while self.running:
            try:
                await self._trading_cycle()

                # Self-review zamanı mı?
                if settings.enable_self_learning:
                    if await self.journal.should_review():
                        logger.info("📓 AI Self-Review başlatılıyor...")
                        review = await self.journal.run_self_review()
                        if review.get("performance_grade"):
                            report = self.journal.format_review_report()
                            await self.telegram.send(report)

                            # Review'dan öğren
                            stats = self.perf_tracker.get_stats()
                            self.adaptive_kelly.update_from_stats(stats)
                            self.strategy.set_performance_context(
                                self.perf_tracker.get_performance_context()
                            )

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

        logger.info("Bot kapatıldı.")

    async def _trading_cycle(self):
        """Tek bir trading döngüsü."""
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

        # Learning context güncelle
        if settings.enable_self_learning:
            stats = self.perf_tracker.get_stats()
            self.adaptive_kelly.update_from_stats(stats)
            self.strategy.set_performance_context(
                self.perf_tracker.get_performance_context()
            )

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

        # 3. AI-powered mispricing analizi (dual-AI)
        markets_to_analyze = [
            m for m in markets if not self.positions.has_position(m["id"])
        ]
        max_analyze = min(50, len(markets_to_analyze))
        markets_to_analyze = markets_to_analyze[:max_analyze]

        logger.info(f"🧠 {max_analyze} market {'dual-AI' if self.deepseek.enabled else 'AI'} ile analiz ediliyor...")
        pre_cost = self.brain.total_api_cost

        # Adaptive Kelly multiplier
        kelly_mult = self.adaptive_kelly.get_multiplier()

        signals = await self.strategy.scan_for_signals(
            markets_to_analyze, self.balance,
            max_signals=5, kelly_multiplier=kelly_mult
        )

        post_cost = self.brain.total_api_cost
        cycle_api_cost = post_cost - pre_cost
        # DeepSeek maliyetini de ekle
        if self.deepseek.enabled:
            cycle_api_cost += self.deepseek.total_cost
        self.economics.record_api_cost(cycle_api_cost, max_analyze)

        # 4. Her sinyal için risk kontrolü ve emir yürütme
        trades_executed = 0

        for signal in signals:
            allowed, reason = self.risk.is_trade_allowed(
                signal=signal,
                balance=self.balance,
                total_exposure=self.positions.total_exposure,
                open_positions=len(self.positions.open_positions),
            )

            if not allowed:
                logger.info(f"⛔ Reddedildi: {reason}")
                continue

            order = await self.executor.execute_signal(signal)
            if order:
                self.positions.open_position(order)
                self.risk.record_trade()
                await self.telegram.notify_trade_opened(signal)
                trades_executed += 1

                # V3: Trade'i kaydet (learning)
                if settings.enable_self_learning:
                    self.perf_tracker.record_trade(
                        signal,
                        cycle_number=self.cycle_count,
                        deepseek_fv=signal.deepseek_fair_value,
                    )

        # 5. Pozisyon izleme (SL/TP)
        if self.positions.open_positions:
            await self._monitor_positions()

        # 6. Döngü raporu
        cycle_time = time.time() - cycle_start
        ai_report = self.brain.get_cost_report()
        ds_report = self.deepseek.get_report() if self.deepseek.enabled else {}

        report = {
            "scanned": len(markets) if markets else 0,
            "filtered": len(markets_to_analyze),
            "analyzed": self.brain.total_api_calls,
            "signals": len(signals),
            "trades": trades_executed,
            "api_cost": cycle_api_cost,
            "failures": ai_report["total_failures"],
            "last_error": ai_report["last_error"],
            "deepseek_agreements": ds_report.get("agreements", 0),
            "deepseek_disagreements": ds_report.get("disagreements", 0),
            "kelly_multiplier": kelly_mult,
        }

        # Learning stats
        if settings.enable_self_learning:
            stats = self.perf_tracker.get_stats()
            report["win_rate"] = stats["win_rate"]
            report["total_historical_trades"] = stats["total_trades"]

        logger.info(
            f"📊 Döngü #{self.cycle_count} ({cycle_time:.1f}s) | "
            f"Sinyal: {len(signals)} | Trade: {trades_executed} | "
            f"API: ${cycle_api_cost:.4f} | Kelly: {kelly_mult:.2f}"
        )

        # Her 6 döngüde ekonomi raporu (1 saat)
        if self.cycle_count % 6 == 0:
            eco_report = self.economics.format_report(self.balance)
            logger.info(f"\n{eco_report}")
            await self.telegram.notify_economics_report(eco_report)

        await self.telegram.notify_scan_report(report)

    async def _monitor_positions(self):
        """Açık pozisyonları izle — SL/TP kontrolü."""
        market_prices = {}

        for market_id, position in self.positions.open_positions.items():
            try:
                if settings.dry_run:
                    market_prices[market_id] = position.entry_price
                else:
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

                    # V3: Trade sonucunu kaydet (learning)
                    if settings.enable_self_learning:
                        self.perf_tracker.close_trade(
                            market_id, current_price, closed.realized_pnl
                        )

    def shutdown(self, signum=None, frame=None):
        logger.info("🛑 Shutdown sinyali alındı...")
        self.running = False


async def main():
    """Entry point."""
    start_health_server()
    bot = PolymarketBot()
    signal.signal(signal.SIGINT, bot.shutdown)
    signal.signal(signal.SIGTERM, bot.shutdown)
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
