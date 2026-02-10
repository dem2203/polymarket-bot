"""Trading strateji ve risk testleri."""

import pytest
from src.trading.strategy import (
    MomentumStrategy,
    ValueStrategy,
    ArbitrageStrategy,
    StrategyEngine,
    SignalType,
    Side,
)
from src.trading.position_tracker import PositionTracker, Position
from src.trading.risk_manager import RiskManager
from src.trading.order_manager import Order, OrderStatus


# ---- Strateji Testleri ----

def test_momentum_buy_signal():
    """Momentum stratejisi düşük fiyatta BUY sinyali üretmeli."""
    strategy = MomentumStrategy(buy_threshold=0.35)
    market = {
        "condition_id": "test_cond_1",
        "question": "Will BTC hit $100k?",
    }
    snapshot = {
        "token_id": "token_abc",
        "price": 0.20,
        "midpoint": 0.25,
        "spread": 0.02,
    }
    signal = strategy.analyze(market, snapshot)
    assert signal is not None
    assert signal.signal_type == SignalType.BUY
    assert signal.side == Side.YES
    assert signal.confidence > 0.3


def test_momentum_sell_signal():
    """Momentum stratejisi yüksek fiyatta SELL sinyali üretmeli."""
    strategy = MomentumStrategy(sell_threshold=0.70)
    market = {
        "condition_id": "test_cond_2",
        "question": "Test sell market?",
    }
    snapshot = {
        "token_id": "token_xyz",
        "price": 0.85,
        "midpoint": 0.83,
        "spread": 0.01,
    }
    signal = strategy.analyze(market, snapshot)
    assert signal is not None
    assert signal.signal_type == SignalType.SELL
    assert signal.confidence > 0.3


def test_momentum_no_signal_wide_spread():
    """Geniş spread'de sinyal üretmemeli."""
    strategy = MomentumStrategy()
    market = {"condition_id": "test", "question": "Test?"}
    snapshot = {
        "token_id": "token_1",
        "price": 0.25,
        "midpoint": 0.26,
        "spread": 0.10,  # Çok geniş
    }
    signal = strategy.analyze(market, snapshot)
    assert signal is None


def test_value_strategy_mispricing():
    """Value stratejisi fiyat sapmasını tespit etmeli."""
    import json

    strategy = ValueStrategy(mispricing_threshold=0.03)
    market = {
        "condition_id": "test_val",
        "question": "Value test?",
        "outcome_prices": json.dumps([0.35, 0.55]),  # Total = 0.90
    }
    snapshot = {
        "token_id": "token_val",
        "price": 0.35,
    }
    signal = strategy.analyze(market, snapshot)
    assert signal is not None
    assert signal.signal_type == SignalType.BUY


def test_arbitrage_strategy():
    """Arbitraj stratejisi YES+NO < 1.0 durumunu tespit etmeli."""
    import json

    strategy = ArbitrageStrategy(min_profit_pct=0.02)
    market = {
        "condition_id": "test_arb",
        "question": "Arbitrage test?",
        "outcome_prices": json.dumps([0.40, 0.50]),  # Total = 0.90
    }
    snapshot = {
        "token_id": "token_arb",
        "price": 0.40,
    }
    signal = strategy.analyze(market, snapshot)
    assert signal is not None
    assert signal.strategy_name == "Arbitrage"
    assert "Arbitraj" in signal.reason


def test_strategy_engine_best_signal():
    """StrategyEngine en yüksek güvenli sinyali döndürmeli."""
    engine = StrategyEngine()
    import json

    market = {
        "condition_id": "test_engine",
        "question": "Engine test?",
        "outcome_prices": json.dumps([0.30, 0.50]),
    }
    snapshot = {
        "token_id": "token_eng",
        "price": 0.30,
        "midpoint": 0.35,
        "spread": 0.02,
    }
    signal = engine.get_best_signal(market, snapshot, min_confidence=0.1)
    # En az bir sinyal dönmeli (muhtemelen birden fazla strateji tetiklenir)
    assert signal is not None
    assert signal.confidence >= 0.1


# ---- Position Tracker Testleri ----

def test_position_open_and_close():
    """Pozisyon aç ve kapat."""
    tracker = PositionTracker()
    order = Order(
        id="test1",
        token_id="token_pos",
        condition_id="cond_pos",
        market_question="Position test?",
        side="BUY",
        price=0.40,
        size=10.0,
        order_type="LIMIT",
        status=OrderStatus.FILLED,
        strategy_name="Momentum",
        signal_confidence=0.75,
        reason="Test",
        fill_price=0.40,
    )

    pos = tracker.open_position(order)
    assert pos.is_open is True
    assert pos.entry_price == 0.40
    assert tracker.has_position("token_pos") is True

    # Fiyat güncelle
    pos.update_price(0.55)
    assert pos.unrealized_pnl > 0

    # Kapat
    closed = tracker.close_position("token_pos", 0.55)
    assert closed is not None
    assert closed.is_open is False
    assert closed.realized_pnl > 0
    assert tracker.has_position("token_pos") is False


def test_portfolio_summary():
    """Portfolio özeti hesaplanmalı."""
    tracker = PositionTracker()
    order = Order(
        id="t2", token_id="tok_2", condition_id="c_2",
        market_question="Summary test?", side="BUY", price=0.50,
        size=20.0, order_type="LIMIT", status=OrderStatus.FILLED,
        strategy_name="Test", signal_confidence=0.8, reason="Test",
        fill_price=0.50,
    )
    tracker.open_position(order)
    summary = tracker.get_portfolio_summary()
    assert summary["open_positions"] == 1
    assert summary["total_invested"] == 20.0


# ---- Risk Manager Testleri ----

def test_risk_approve_trade():
    """Risk onayı - normal koşullarda geçmeli."""
    tracker = PositionTracker()
    risk = RiskManager(tracker)

    from src.trading.strategy import TradingSignal, SignalType, Side
    signal = TradingSignal(
        signal_type=SignalType.BUY,
        side=Side.YES,
        token_id="token_risk",
        condition_id="cond_risk",
        market_question="Risk test?",
        price=0.30,
        confidence=0.80,
        strategy_name="Momentum",
        reason="Test",
    )

    approved, reason, size = risk.approve_trade(signal)
    assert approved is True
    assert size > 0


def test_risk_reject_low_confidence():
    """Düşük güvenli sinyal reddedilmeli."""
    tracker = PositionTracker()
    risk = RiskManager(tracker)

    from src.trading.strategy import TradingSignal, SignalType, Side
    signal = TradingSignal(
        signal_type=SignalType.BUY,
        side=Side.YES,
        token_id="token_low",
        condition_id="cond_low",
        market_question="Low conf test?",
        price=0.30,
        confidence=0.10,  # Çok düşük
        strategy_name="Test",
        reason="Test",
    )

    approved, reason, size = risk.approve_trade(signal)
    assert approved is False
    assert "eşiği altında" in reason.lower() or "güven" in reason.lower()


def test_stop_loss_trigger():
    """Stop-loss tetiklenmeli."""
    tracker = PositionTracker()
    risk = RiskManager(tracker)

    # %20 kayıp (stop-loss default %15)
    triggered = risk.check_stop_loss("tok_sl", 0.32, 0.40)
    assert triggered is True

    # %5 kayıp - tetiklenmemeli
    not_triggered = risk.check_stop_loss("tok_sl2", 0.38, 0.40)
    assert not_triggered is False


def test_take_profit_trigger():
    """Take-profit tetiklenmeli."""
    tracker = PositionTracker()
    risk = RiskManager(tracker)

    # %40 kar (take-profit default %30)
    triggered = risk.check_take_profit("tok_tp", 0.56, 0.40)
    assert triggered is True

    # %10 kar - tetiklenmemeli
    not_triggered = risk.check_take_profit("tok_tp2", 0.44, 0.40)
    assert not_triggered is False
