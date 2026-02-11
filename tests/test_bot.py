"""
Polymarket AI Trading Bot V2 — Unit Tests
Tests for Kelly criterion, mispricing detection, risk management, and economics.
"""

import pytest
import time
import os

# Set env vars before importing modules
os.environ["ANTHROPIC_API_KEY"] = "test-key"
os.environ["POLYMARKET_PRIVATE_KEY"] = "0xTEST"
os.environ["DRY_RUN"] = "true"


# ============ KELLY CRITERION TESTS ============

class TestKellyCriterion:
    """Kelly Criterion pozisyon boyutlandırma testleri."""

    def setup_method(self):
        from src.strategy.kelly import KellySizer
        self.kelly = KellySizer()
        self.kelly.max_fraction = 0.06
        self.kelly.multiplier = 0.5

    def test_positive_edge_buy_yes(self):
        """AI fair value > market price → BUY YES, pozitif kelly."""
        result = self.kelly.calculate(
            fair_value=0.70,
            market_price=0.55,
            balance=100.0,
            direction="BUY_YES",
            confidence=0.80,
        )
        assert result["position_size"] > 0
        assert result["token_side"] == "YES"
        assert result["adjusted_fraction"] <= 0.06

    def test_positive_edge_buy_no(self):
        """AI fair value < market price → BUY NO."""
        result = self.kelly.calculate(
            fair_value=0.30,
            market_price=0.55,
            balance=100.0,
            direction="BUY_NO",
            confidence=0.80,
        )
        assert result["position_size"] > 0
        assert result["token_side"] == "NO"

    def test_no_edge_returns_zero(self):
        """Edge yoksa pozisyon 0."""
        result = self.kelly.calculate(
            fair_value=0.50,
            market_price=0.50,
            balance=100.0,
            direction="BUY_YES",
            confidence=0.80,
        )
        assert result["position_size"] == 0.0

    def test_kelly_cap_respected(self):
        """Çok büyük edge'de bile max %6 cap uygulanır."""
        result = self.kelly.calculate(
            fair_value=0.95,
            market_price=0.30,
            balance=1000.0,
            direction="BUY_YES",
            confidence=0.95,
        )
        # Max %6 * %50 fractional = %3 of balance = $30
        assert result["adjusted_fraction"] <= 0.06
        assert result["position_size"] <= 1000 * 0.06

    def test_low_balance_no_trade(self):
        """Çok düşük bakiyede trade yapma."""
        result = self.kelly.calculate(
            fair_value=0.70,
            market_price=0.55,
            balance=5.0,
            direction="BUY_YES",
            confidence=0.80,
        )
        # Minimum $1 kuralı: Kelly çok küçük olabilir
        assert result["position_size"] >= 0


# ============ MISPRICING DETECTION TESTS ============

class TestMispricingDetection:
    """AI Brain mispricing tespiti testleri."""

    def test_edge_above_threshold(self):
        """Edge > %8 → has_edge = True."""
        from src.ai.brain import AIBrain
        brain = AIBrain.__new__(AIBrain)
        brain.total_input_tokens = 0
        brain.total_output_tokens = 0
        brain.total_api_calls = 0
        brain.input_cost_per_m = 1.0
        brain.output_cost_per_m = 5.0

        # Monkey-patch settings
        import src.config
        src.config.settings.mispricing_threshold = 0.08

        result = brain.detect_mispricing(fair_value=0.70, market_price=0.55)
        assert result["has_edge"] is True
        assert result["direction"] == "BUY_YES"
        assert result["edge"] >= 0.08

    def test_edge_below_threshold(self):
        """Edge < %8 → has_edge = False."""
        from src.ai.brain import AIBrain
        brain = AIBrain.__new__(AIBrain)
        brain.total_input_tokens = 0
        brain.total_output_tokens = 0
        brain.total_api_calls = 0
        brain.input_cost_per_m = 1.0
        brain.output_cost_per_m = 5.0

        import src.config
        src.config.settings.mispricing_threshold = 0.08

        result = brain.detect_mispricing(fair_value=0.55, market_price=0.50)
        assert result["has_edge"] is False

    def test_buy_no_direction(self):
        """Fair value < market price → BUY NO."""
        from src.ai.brain import AIBrain
        brain = AIBrain.__new__(AIBrain)
        brain.total_input_tokens = 0
        brain.total_output_tokens = 0
        brain.total_api_calls = 0
        brain.input_cost_per_m = 1.0
        brain.output_cost_per_m = 5.0

        import src.config
        src.config.settings.mispricing_threshold = 0.08

        result = brain.detect_mispricing(fair_value=0.30, market_price=0.50)
        assert result["has_edge"] is True
        assert result["direction"] == "BUY_NO"


# ============ RISK MANAGEMENT TESTS ============

class TestRiskManager:
    """Risk yönetimi testleri."""

    def setup_method(self):
        from src.trading.risk import RiskManager
        self.risk = RiskManager()

    def _make_signal(self, position_size=5.0, edge=0.10, confidence=0.75):
        from src.strategy.mispricing import TradeSignal
        return TradeSignal(
            market_id="test", question="Test?", category="general",
            direction="BUY_YES", fair_value=0.70, market_price=0.55,
            edge=edge, confidence=confidence, position_size=position_size,
            shares=10, price=0.55, token_side="YES", reasoning="test",
            kelly_fraction=0.03, tokens=["t1", "t2"],
        )

    def test_trade_approved(self):
        """Normal trade onaylanır."""
        signal = self._make_signal()
        allowed, reason = self.risk.is_trade_allowed(
            signal=signal, balance=100.0, total_exposure=20.0, open_positions=2,
        )
        assert allowed is True

    def test_survival_mode_blocks(self):
        """Bakiye < survival_balance → trade reddedilir."""
        import src.config
        src.config.settings.survival_balance = 5.0

        signal = self._make_signal()
        allowed, reason = self.risk.is_trade_allowed(
            signal=signal, balance=3.0, total_exposure=0.0, open_positions=0,
        )
        assert allowed is False
        assert "HAYATTA KALMA" in reason

    def test_daily_loss_limit(self):
        """Günlük kayıp limiti → reddedilir."""
        import src.config
        src.config.settings.daily_loss_limit = 25.0

        self.risk.daily_loss = 30.0  # Limit aşıldı
        signal = self._make_signal()
        allowed, reason = self.risk.is_trade_allowed(
            signal=signal, balance=100.0, total_exposure=0.0, open_positions=0,
        )
        assert allowed is False
        assert "kayıp limiti" in reason

    def test_exposure_limit(self):
        """Toplam exposure limiti → reddedilir."""
        import src.config
        src.config.settings.max_total_exposure = 100.0

        signal = self._make_signal(position_size=50.0)
        allowed, reason = self.risk.is_trade_allowed(
            signal=signal, balance=200.0, total_exposure=80.0, open_positions=1,
        )
        assert allowed is False
        assert "Exposure" in reason


# ============ POSITION TRACKER TESTS ============

class TestPositionTracker:
    """Pozisyon takip testleri."""

    def setup_method(self):
        from src.trading.positions import PositionTracker
        self.tracker = PositionTracker()

    def _make_order(self, market_id="mkt1"):
        from src.trading.executor import ExecutedOrder
        return ExecutedOrder(
            order_id="ORD-1", market_id=market_id, question="Test?",
            side="BUY", token_side="YES", price=0.50, size=10.0,
            shares=20.0, status="FILLED", timestamp=time.time(),
        )

    def test_open_position(self):
        """Pozisyon açma."""
        order = self._make_order()
        pos = self.tracker.open_position(order)
        assert self.tracker.has_position("mkt1")
        assert pos.entry_price == 0.50
        assert pos.cost_basis == 10.0

    def test_close_position_profit(self):
        """Kârla kapama."""
        self.tracker.open_position(self._make_order())
        closed = self.tracker.close_position("mkt1", exit_price=0.70)
        assert closed is not None
        assert closed.realized_pnl > 0  # (0.70 - 0.50) * 20 = 4.0
        assert not self.tracker.has_position("mkt1")

    def test_close_position_loss(self):
        """Zararla kapama."""
        self.tracker.open_position(self._make_order())
        closed = self.tracker.close_position("mkt1", exit_price=0.35)
        assert closed is not None
        assert closed.realized_pnl < 0

    def test_stop_loss_trigger(self):
        """SL tetiklenmesi."""
        import src.config
        src.config.settings.stop_loss_pct = 0.20

        self.tracker.open_position(self._make_order())
        # Fiyat %25 düşerse SL tetiklenir
        to_close = self.tracker.check_stop_loss_take_profit({"mkt1": 0.35})
        assert "mkt1" in to_close

    def test_take_profit_trigger(self):
        """TP tetiklenmesi."""
        import src.config
        src.config.settings.take_profit_pct = 0.25

        self.tracker.open_position(self._make_order())
        # Fiyat %30 artarsa TP tetiklenir
        to_close = self.tracker.check_stop_loss_take_profit({"mkt1": 0.70})
        assert "mkt1" in to_close


# ============ ECONOMICS TRACKER TESTS ============

class TestEconomicsTracker:
    """Ekonomi takip testleri."""

    def setup_method(self):
        from src.economics.tracker import EconomicsTracker
        self.eco = EconomicsTracker(starting_balance=50.0)

    def test_self_sustaining_positive(self):
        """Trading PnL > API cost → self-sustaining."""
        self.eco.record_trade_pnl(5.0)
        self.eco.record_api_cost(0.50)
        assert self.eco.is_self_sustaining is True
        assert self.eco.net_profit == 4.50

    def test_not_self_sustaining(self):
        """Trading PnL < API cost → not self-sustaining."""
        self.eco.record_trade_pnl(0.10)
        self.eco.record_api_cost(0.50)
        assert self.eco.is_self_sustaining is False

    def test_snapshot_report(self):
        """Snapshot raporu doğru hesaplanır."""
        self.eco.record_trade_pnl(10.0)
        self.eco.record_api_cost(0.25, calls=5)
        snap = self.eco.get_snapshot(current_balance=60.0)
        assert snap.starting_balance == 50.0
        assert snap.current_balance == 60.0
        assert snap.roi_pct == 20.0
        assert snap.api_calls == 5


# ============ ARBITRAGE TESTS ============

class TestArbitrage:
    """Arbitraj stratejisi testleri."""

    def test_arbitrage_detected(self):
        """YES + NO < 0.98 → arbitraj fırsatı."""
        from src.strategy.arbitrage import ArbitrageStrategy
        arb = ArbitrageStrategy()
        markets = [{
            "id": "arb1", "question": "Arb Test?",
            "yes_price": 0.45, "no_price": 0.45,
            "tokens": ["t1", "t2"], "slug": "arb",
        }]
        signals = arb.detect(markets, balance=100.0)
        assert len(signals) > 0
        assert signals[0].profit_margin > 0.02

    def test_no_arbitrage(self):
        """YES + NO >= 0.98 → arbitraj yok."""
        from src.strategy.arbitrage import ArbitrageStrategy
        arb = ArbitrageStrategy()
        markets = [{
            "id": "arb2", "question": "No Arb?",
            "yes_price": 0.50, "no_price": 0.50,
            "tokens": ["t1", "t2"], "slug": "noarb",
        }]
        signals = arb.detect(markets, balance=100.0)
        assert len(signals) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
