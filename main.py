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

print("🚀 POLYMARKET AI BOT V3 BAŞLATILIYOR... (Debug Mode)", flush=True)

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
from src.learning.github_memory import GitHubMemory
from src.wallet.approval import check_and_approve
from src.monitoring.health_monitor import HealthMonitor

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
        self.github_memory = GitHubMemory()
        
        # V3.5: Health & Safety
        self.health_monitor = HealthMonitor(self.telegram)

        # Durum
        self.running = True
        self.cycle_count = 0
        self.balance = settings.starting_balance

    async def start(self):
        """Bot'u başlat."""
        logger.info("=" * 60)
        logger.info("🤖 POLYMARKET AI TRADING BOT V3 — SELF-LEARNING")
        logger.info("=" * 60)
        
        # GitHub Memory Load
        if self.github_memory.enabled:
            logger.info("🌍 GitHub Hafıza yükleniyor...")
            self.github_memory.load_memory()
            self.perf_tracker.reload()
            logger.info(f"📚 {len(self.perf_tracker.trades)} geçmiş trade yüklendi.")

        logger.info(f"Mod: {'🔵 DRY RUN' if settings.dry_run else '🟢 LIVE'}")
        logger.info(f"AI: {settings.ai_model}")
        logger.info(f"DeepSeek: {'✅ aktif' if self.deepseek.enabled else '❌ devre dışı'}")
        logger.info(f"Learning: {'✅ aktif' if settings.enable_self_learning else '❌ devre dışı'}")
        logger.info(f"GitHub Memory: {'✅ aktif' if self.github_memory.enabled else '❌ devre dışı'}")
        logger.info(f"Bakiye: ${self.balance:.2f}")
        logger.info(f"Mispricing eşik: >{settings.mispricing_threshold:.0%}")
        logger.info(f"Kelly cap: %{settings.max_kelly_fraction*100:.0f}")
        logger.info(f"Hayatta kalma: ${settings.survival_balance:.2f}")
        logger.info("=" * 60)

        # API kontrolleri
        if not settings.has_anthropic_key:
            logger.error("ANTHROPIC_API_KEY ayarlanmamış!")
            await self.telegram.send("❌ ANTHROPIC_API_KEY yok! Bot duruyor.")
            return

        # 🔄 PORTFOLIO SYNC (API'den Pozisyonları Kurtar)
        if settings.has_polymarket_key:
            try:
                logger.info("🌊 Portfolyo senkronizasyonu başlıyor...")
                api_positions = await self.executor.get_open_positions()
                
                if api_positions:
                    logger.info(f"⏳ {len(api_positions)} pozisyon için market bilgileri aranıyor...")
                    # Tüm marketleri çek (başlıkları bulmak için) - V3.3.14: Filtresiz çek!
                    all_markets = await self.scanner.scan_all_markets(skip_filters=True)
                    
                    # Token ID -> Market haritası çıkar
                    token_map = {}
                    for m in all_markets:
                        for t in m.get("tokens", []):
                            token_map[t["token_id"]] = m
                    
                    # Eşleştir ve ekle
                    synced_count = 0
                    for p in api_positions:
                        tid = p.get("asset_id")
                        size = float(p.get("size", 0))
                        
                        if size > 0 and tid in token_map:
                            m = token_map[tid]
                            # Tarafı bul (Token ID karşılaştır)
                            side = "UNKNOWN"
                            tokens = m.get("tokens", [])
                            if tokens and len(tokens) >= 2:
                                if tid == tokens[0]["token_id"]:
                                    side = "YES" # Genellikle 0=YES
                                elif tid == tokens[1]["token_id"]:
                                    side = "NO"
                            
                            # Pozisyonu ekle
                            self.positions.add_remote_position(
                                market_id=m["id"],
                                question=m["question"],
                                token_side=side,
                                shares=size,
                                entry_price=float(p.get("avg_price", 0)),
                                token_id=tid
                            )
                            synced_count += 1
                    
                    logger.info(f"✅ {synced_count}/{len(api_positions)} pozisyon kurtarıldı ve eşleştirildi.")
                else:
                    logger.info("ℹ️ API'de açık pozisyon bulunamadı.")
            except Exception as e:
                logger.error(f"❌ Portfolyo sync hatası: {e}")

        # AI Health Check
        logger.info("AI Health Check...")
        health = self.brain.health_check()
        if health["ok"]:
            logger.info(f"✅ AI hazır: {health['model']}")
        else:
            logger.error(f"❌ AI HATA: {health['error']}")
            # Kritik hata değilse devam et, ama bildir

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
            f"GitHub Memory: {'✅' if self.github_memory.enabled else '❌'}\n"
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

                # GitHub Memory Save (her saat)
                if self.cycle_count % 6 == 0 and self.github_memory.enabled:
                    logger.info("🌍 GitHub hafıza yedekleniyor...")
                    self.github_memory.save_memory()

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
                            
                            # Review sonrası da yedekle
                            if self.github_memory.enabled:
                                self.github_memory.save_memory()

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

        # Shutdown'da yedekle
        if self.github_memory.enabled:
            logger.info("🛑 Bot kapanıyor, son hafıza yedeği alınıyor...")
            self.github_memory.save_memory()
        
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
        
        # V3.5: CRITICAL HEALTH CHECKS
        # Defensive validation
        assert self.balance >= 0, f"CRITICAL: Negative balance ${self.balance:.2f} - API error"
        
        # Balance sanity check
        await self.health_monitor.check_balance_sanity(self.balance)

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

        # 0. Açık emirleri temizle (Sermaye yönetimi)
        try:
            await self.executor.cancel_all_open_orders()
        except Exception as e:
            logger.warning(f"Emir iptal hatası: {e}")

        # 1. Market tarama
        logger.info("📡 Marketler taranıyor...")
        markets = await self.scanner.scan_all_markets()

        if not markets:
            logger.warning("⚠️ Hiç market bulunamadı")
            return

        # 2. Arbitraj kontrolü (hızlı, AI gerektirmez) + EXECUTE!
        arb_signals = self.arbitrage.detect(markets, self.balance)
        if arb_signals:
            logger.info(f"🔄 {len(arb_signals)} arbitraj fırsatı bulundu — EXECUTE!")
            for arb in arb_signals[:3]:  # Max 3 arbitraj
                try:
                    # YES tarafını al
                    if arb.tokens and len(arb.tokens) >= 2:
                        from src.strategy.mispricing import TradeSignal
                        arb_signal = TradeSignal(
                            market_id=arb.market_id, question=arb.question,
                            category="arbitrage", direction="BUY_YES",
                            fair_value=0.5, market_price=arb.yes_price,
                            edge=arb.profit_margin, confidence=0.95,
                            position_size=arb.position_size / 2,
                            shares=round((arb.position_size / 2) / arb.yes_price, 1),
                            price=arb.yes_price, token_side="YES",
                            reasoning=f"Arbitrage: YES+NO={arb.total_price:.3f}",
                            kelly_fraction=0.05, tokens=arb.tokens, slug=arb.slug,
                        )
                        order = await self.executor.execute_signal(arb_signal)
                        if order:
                            token_id = arb.tokens[0] if arb.tokens else ""
                            self.positions.open_position(order, token_id=token_id)
                            self.risk.record_trade()
                            logger.info(f"✅ Arbitraj YES alındı: {arb.question[:40]}")
                except Exception as e:
                    logger.warning(f"Arbitraj execute hatası: {e}")

        # 3. Nakit kontrolü
        # FIXED: total_exposure eski pozisyonları içerebilir, direkt balance kullan
        # Eğer open positions varsa monitoring update edecek
        available_cash = self.balance
        positions_exist = bool(self.positions.open_positions)
        
        # V3.5: Check for NEGATIVE CASH (IMPOSSIBLE)
        if await self.health_monitor.check_negative_cash(
            available_cash, 
            self.balance, 
            self.positions.total_exposure
        ):
            logger.critical("🛑 EMERGENCY STOP: Negative cash detected")
            return  # Emergency stop
        
        # V3.5: Check for idle trading (6+ hours with cash)
        await self.health_monitor.check_idle_trading(available_cash)
        
        if available_cash < 2.0 and not positions_exist:
            logger.info(f"💰 Yeterli nakit yok (${available_cash:.2f}), sadece izleme modu")
            return
        
        logger.debug(f"💵 Mevcut nakit: ${available_cash:.2f} | Açık pozisyon: {len(self.positions.open_positions)}")

        # 4. AI-powered mispricing analizi (dual-AI)
        # Nakit varsa yeni trade ara, yoksa sadece mevcut pozisyonları izle
        signals = []
        cycle_api_cost = 0.0
        markets_to_analyze = []

        # Calculate Portfolio Value (Always calculate for accurate logging/risk)
        portfolio_summary = self.positions.get_portfolio_summary(self.balance)
        portfolio_value = portfolio_summary.get("total_exposure", 0.0)
        total_value = self.balance + portfolio_value

        if available_cash >= 2.0:
            markets_to_analyze = [
                m for m in markets if not self.positions.has_position(m["id"])
            ]
            # ⚔️ WARRIOR: Sadece en iyi 10 market (50 değil!)
            max_analyze = min(10, len(markets_to_analyze))
            markets_to_analyze = markets_to_analyze[:max_analyze]

            logger.info(f"🧠 {max_analyze} market {'dual-AI' if self.deepseek.enabled else 'AI'} ile analiz ediliyor...")
            pre_cost = self.brain.total_api_cost

            # Adaptive Kelly multiplier
            kelly_mult = self.adaptive_kelly.get_multiplier()
            
            logger.info(f"💰 Cash: ${self.balance:.2f} | Portfolio: ${portfolio_value:.2f} | Total: ${total_value:.2f}")

            signals = await self.strategy.scan_for_signals(
                markets_to_analyze, 
                cash=self.balance,
                portfolio_value=portfolio_value,
                max_signals=5, kelly_multiplier=kelly_mult
            )

            post_cost = self.brain.total_api_cost
            cycle_api_cost = post_cost - pre_cost
            # DeepSeek maliyetini de ekle
            if self.deepseek.enabled:
                cycle_api_cost += self.deepseek.total_cost
            self.economics.record_api_cost(cycle_api_cost, max_analyze)
        else:
            kelly_mult = self.adaptive_kelly.get_multiplier()
            logger.info(f"⏸️ Nakit yetersiz (${available_cash:.2f}), yeni trade aranmıyor — sadece pozisyon izleme")

        # 5. Her sinyal için risk kontrolü ve emir yürütme
        trades_executed = 0

        for signal in signals:
            if trades_executed >= 5:
                logger.info("⚠️ Döngü başına max 5 trade limitine ulaşıldı.")
                break

            # V3.3.13: Mevcut pozisyon değerini sinyale ekle (Risk Manager için)
            existing_pos = self.positions.open_positions.get(signal.market_id)
            if existing_pos:
                # Token tarafı aynı mı? (YES alırken NO varsa hedge olur, ama şimdilik basit tutalım)
                if existing_pos.token_side == signal.token_side:
                    signal.current_position_value = existing_pos.shares * signal.market_price
            
            # Risk check
            allowed, reason = self.risk.is_trade_allowed(
                signal, self.balance, self.positions.total_exposure, len(self.positions.open_positions)
            )

            if not allowed:
                logger.info(f"⛔ Reddedildi: {reason}")
                continue

            order = await self.executor.execute_signal(signal)
            if order:
                # Token ID'yi kaydet (SELL için gerekli!)
                token_id = self.executor._get_token_id(signal) or ""
                self.positions.open_position(order, token_id=token_id)
                self.risk.record_trade()
                await self.telegram.notify_trade_opened(signal)
                trades_executed += 1
                
                # V3.5: Record trade in health monitor
                self.health_monitor.record_trade()

                # V3: Trade'i kaydet (learning)
                if settings.enable_self_learning:
                    self.perf_tracker.record_trade(
                        signal,
                        cycle_number=self.cycle_count,
                        deepseek_fv=signal.deepseek_fair_value,
                    )

        # 6. Pozisyon izleme (SL/TP + GERÇEK SATIŞ)
        market_prices_count = 0
        if self.positions.open_positions:
            market_prices_count = await self._monitor_positions()
            
            # V3.5: Validate monitoring execution
            await self.health_monitor.check_monitoring_failure(
                len(self.positions.open_positions),
                market_prices_count
            )

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
        
        # V3.5: Her 6 saatte health dashboard (36 cycle @ 10min)
        if self.cycle_count % 36 == 0:
            await self.health_monitor.send_health_dashboard(
                self.balance,
                self.positions,
                self.perf_tracker if settings.enable_self_learning else None
            )

        await self.telegram.notify_scan_report(report)

    async def _monitor_positions(self):
        """Açık pozisyonları izle — SL/TP + Smart Expiry Exit."""
        if not self.positions.open_positions:
            return
            
        logger.info(f"👀 Açık pozisyonlar kontrol ediliyor ({len(self.positions.open_positions)})...")
        
        market_prices = {}
        market_end_dates = {}

        for market_id, position in self.positions.open_positions.items():
            try:
                if settings.dry_run:
                    # Dry run: Test için fake end_date (2 saat kaldı diyelim)
                    market_end_dates[market_id] = None # datetime.now().isoformat()
                    market_prices[market_id] = position.entry_price
                else:
                    # Try to get market details from scanner
                    detail = await self.scanner.get_market_details(market_id)
                    if detail:
                        # End date al
                        ed = detail.get("endDate", detail.get("end_date_iso"))
                        if ed:
                            market_end_dates[market_id] = ed
                        
                        # Fiyat al
                        prices = detail.get("outcomePrices", "")
                        if prices:
                            import json
                            price_list = json.loads(prices) if isinstance(prices, str) else prices
                            if position.token_side == "YES":
                                market_prices[market_id] = float(price_list[0])
                            else:
                                market_prices[market_id] = float(price_list[1]) if len(price_list) > 1 else 1.0 - float(price_list[0])
                            logger.debug(f"✅ Fiyat güncellendi: {market_id[:12]}... = ${market_prices[market_id]:.3f}")
                    else:
                        # Fallback: Entry price kullan (güncel fiyat bilinmiyor)
                        logger.warning(f"⚠️ Market detay yok: {market_id[:12]}... - Entry price kullanılıyor")
                        market_prices[market_id] = position.entry_price
            except Exception as e:
                logger.debug(f"Fiyat güncelleme hatası {market_id[:12]}...: {e}")

        # Pozisyon durumlarını logla ve Expiry Analizi yap
        expiry_exits = []
        import time as time_mod
        from datetime import datetime, timezone, timedelta

        # ISO formatlarını parse etmek için
        def parse_iso(date_str):
            try:
                return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            except:
                return None

        # Şimdiki zaman (UTC)
        now_utc = datetime.now(timezone.utc)

        for market_id, position in self.positions.open_positions.items():
            if market_id in market_prices:
                price = market_prices[market_id]
                pnl_pct = (price - position.entry_price) / position.entry_price if position.entry_price > 0 else 0
                emoji = "🟢" if pnl_pct >= 0 else "🔴"
                
                # Expiry check logic
                end_date_str = market_end_dates.get(market_id)
                expiry_msg = ""
                
                if end_date_str:
                    end_date = parse_iso(end_date_str)
                    if end_date:
                        # Time remaining calculation
                        time_rem = end_date - now_utc
                        hours_rem = time_rem.total_seconds() / 3600
                        expiry_msg = f"| ⏳ {hours_rem:.1f}h"

                        # 1. Last Hour Panic: 1 saatten az kaldı ve kâr > %0 -> SAT
                        if hours_rem < 1.0 and pnl_pct > 0.0:
                            expiry_exits.append({
                                "market_id": market_id,
                                "token_id": position.token_id,
                                "shares": position.shares,
                                "price": price,
                                "reason": f"EXPIRY_PANIC (<1h, PnL={pnl_pct:.1%})",
                            })

                        # 2. Critical Zone: 6 saatten az kaldı
                        elif hours_rem < 6.0:
                            # Eğer kâr %2'nin altındaysa (veya zarardaysa) -> RİSK ALMA, ÇIK.
                            # Ama kâr %2+ ise -> TUT (User'ın isteği: upside kalsın).
                            if pnl_pct < 0.02:
                                expiry_exits.append({
                                    "market_id": market_id,
                                    "token_id": position.token_id,
                                    "shares": position.shares,
                                    "price": price,
                                    "reason": f"EXPIRY_WEAK (<6h, PnL={pnl_pct:.1%})",
                                })

                        # 3. Last 24 Hours: Stop Loss Tighten (-10%)
                        elif hours_rem < 24.0:
                             if pnl_pct < -0.10:
                                 expiry_exits.append({
                                    "market_id": market_id,
                                    "token_id": position.token_id,
                                    "shares": position.shares,
                                    "price": price,
                                    "reason": f"EXPIRY_STOP_TIGHTEN (<24h, PnL={pnl_pct:.1%})",
                                })

                logger.info(
                    f"{emoji} Pozisyon: {position.question[:35]}... | "
                    f"Giriş: ${position.entry_price:.3f} → Şimdi: ${price:.3f} | "
                    f"PnL: {pnl_pct:+.1%} | Shares: {position.shares:.1f} {expiry_msg}"
                )
            else:
                logger.warning(f"⚠️ Fiyat bilgisi yok: {position.question[:40]}... (market_id: {market_id[:12]}...)")

        to_close = self.positions.check_stop_loss_take_profit(market_prices)
        
        # Expiry cleanups
        for exit_info in expiry_exits:
            # Eğer zaten SL/TP listesindeyse tekrar ekleme
            if not any(x["market_id"] == exit_info["market_id"] for x in to_close):
                to_close.append(exit_info)

        for close_info in to_close:
            market_id = close_info["market_id"]
            token_id = close_info["token_id"]
            shares = close_info["shares"]
            price = close_info["price"]
            reason = close_info["reason"]

            position = self.positions.open_positions.get(market_id)
            if not position:
                continue

            # 🔴 GERÇEK SELL EMRİ GÖNDER!
            if token_id:
                sell_result = await self.executor.sell_position(token_id, shares, price)
                if sell_result:
                    logger.info(f"🔴 SELL emri başarılı: {sell_result.order_id} | {reason}")
                else:
                    logger.error(f"❌ SELL emri başarısız: {market_id} | {reason}")
                    continue  # Satış başarısızsa pozisyonu kapatma
            else:
                logger.warning(f"⚠️ Token ID yok, sadece dahili kapatma: {market_id}")

            await self.telegram.notify_stop_loss(position)
            closed = self.positions.close_position(market_id, price)
            if closed:
                self.economics.record_trade_pnl(closed.realized_pnl)
                self.risk.record_trade(closed.realized_pnl)
                await self.telegram.notify_trade_closed(closed)

                # V3: Trade sonucunu kaydet (learning)
                if settings.enable_self_learning:
                    self.perf_tracker.close_trade(
                        market_id, price, closed.realized_pnl
                    )

        # ⚔️ WARRIOR: Stale position exit — 4+ saat, kâr yok → çık
        import time as time_mod
        stale_exits = []
        for market_id, position in self.positions.open_positions.items():
            if market_id in market_prices:
                age_hours = (time_mod.time() - position.opened_at) / 3600
                price = market_prices[market_id]
                pnl_pct = (price - position.entry_price) / position.entry_price if position.entry_price > 0 else 0

                # 4+ saat ve PnL %-2 ile %+3 arası → stale, çık
                if age_hours >= 4 and -0.02 <= pnl_pct <= 0.03:
                    logger.info(
                        f"⏰ STALE EXIT: {position.question[:35]}... | "
                        f"Age={age_hours:.1f}h | PnL={pnl_pct:+.1%} → Çıkıyoruz"
                    )
                    stale_exits.append({
                        "market_id": market_id,
                        "token_id": position.token_id,
                        "shares": position.shares,
                        "price": price,
                        "reason": "STALE_EXIT",
                    })

        for close_info in stale_exits:
            market_id = close_info["market_id"]
            token_id = close_info["token_id"]
            shares = close_info["shares"]
            price = close_info["price"]

            if token_id:
                sell_result = await self.executor.sell_position(token_id, shares, price)
                if sell_result:
                    logger.info(f"⏰ STALE SELL başarılı: {sell_result.order_id}")
                else:
                    continue

            closed = self.positions.close_position(market_id, price)
            if closed:
                self.economics.record_trade_pnl(closed.realized_pnl)
                self.risk.record_trade(closed.realized_pnl)
                await self.telegram.notify_trade_closed(closed)
                if settings.enable_self_learning:
                    self.perf_tracker.close_trade(market_id, price, closed.realized_pnl)

        # 🧟 ZOMBIE CLEANUP: Değeri $0 olan ve süresi dolmuş pozisyonları temizle
        zombies = []
        for market_id, position in self.positions.open_positions.items():
            if market_id in market_prices:
                price = market_prices[market_id]
                # Fiyat 0.2 centin altındaysa (%0.002) ve 1 saatten yaşlıysa -> ZOMBIE
                if price < 0.002 and (time.time() - position.opened_at > 3600):
                    logger.warning(
                        f"🧟 ZOMBIE DETECTED: {position.question[:35]}... | "
                        f"Price=${price:.4f} (~$0) | Takipten çıkarılıyor..."
                    )
                    zombies.append(market_id)

        for mid in zombies:
            self.positions.close_position(mid, exit_price=0.0, local_only=True)
        
        # V3.5: Return number of positions with successfully fetched prices
        return len(market_prices)


    def shutdown(self, signum=None, frame=None):
        logger.info("🛑 Shutdown sinyali alındı...")
        self.running = False


async def main():
    """Entry point."""
    start_health_server()
    
    # Wallet Allowance kontrolü
    check_and_approve()

    bot = PolymarketBot()
    signal.signal(signal.SIGINT, bot.shutdown)
    signal.signal(signal.SIGTERM, bot.shutdown)
    await bot.start()


if __name__ == "__main__":
    asyncio.run(main())
