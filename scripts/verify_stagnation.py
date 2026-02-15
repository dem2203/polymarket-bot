
import unittest
import time
from unittest.mock import MagicMock
import sys
import os

sys.path.append(os.getcwd())
from src.config import settings
from src.trading.positions import PositionTracker, Position

class TestStagnationKiller(unittest.TestCase):
    def setUp(self):
        self.tracker = PositionTracker()
        settings.stagnation_days = 7
        settings.stagnation_threshold = 0.03
        settings.stop_loss_pct = 0.15
        settings.take_profit_pct = 0.40

    def test_stagnation_trigger(self):
        """Test if stagnation killer triggers for >7 days old flat positions"""
        
        # Case 1: Active Stagnant Position
        # Held 8 days (192 hours), PnL 1% (Flat)
        p1 = Position(
            market_id="stagnant_1",
            question="Stagnant Market",
            token_side="YES",
            entry_price=0.50,
            shares=10.0,
            cost_basis=5.0,
            current_price=0.50,
            token_id="123"
        )
        # Mock opened_at to 8 days ago
        p1.opened_at = time.time() - (8 * 24 * 3600) 
        p1.pnl_pct = 0.01 # < 3% threshold
        self.tracker.open_positions["stagnant_1"] = p1
        
        # Case 2: Fresh Position
        # Held 2 days, PnL 0%
        p2 = Position(
            market_id="fresh_1",
            question="Fresh Market",
            token_side="YES",
            entry_price=0.50,
            shares=10.0,
            cost_basis=5.0,
            current_price=0.50,
            token_id="456"
        )
        p2.opened_at = time.time() - (2 * 24 * 3600)
        p2.pnl_pct = 0.01
        self.tracker.open_positions["fresh_1"] = p2
        
        # Case 3: Profitable Old Position
        # Held 8 days, PnL 10% (Alive and kicking) -> Should NOT sell
        p3 = Position(
            market_id="profitable_old",
            question="Profitable Old",
            token_side="YES",
            entry_price=0.50,
            shares=10.0,
            cost_basis=5.0,
            current_price=0.55,
            token_id="789"
        )
        p3.opened_at = time.time() - (8 * 24 * 3600)
        p3.pnl_pct = 0.10 # > 3% threshold
        self.tracker.open_positions["profitable_old"] = p3

        # Run Check
        # Price updates:
        # P1: 0.505 (+1%) -> Should SELL (Stagnant < 3%)
        # P2: 0.505 (+1%) -> Should HOLD (Fresh)
        # P3: 0.55 (+10%) -> Should HOLD (Moving > 3%)
        
        market_prices = {
            "stagnant_1": 0.505,
            "fresh_1": 0.505,
            "profitable_old": 0.55
        }
        
        exits = self.tracker.check_stop_loss_take_profit(market_prices)
        
        # Assertions
        exit_reasons = [e['reason'] for e in exits]
        market_ids = [e['market_id'] for e in exits]
        
        print(f"Exits Triggered: {len(exits)}")
        for e in exits:
            print(f" - {e['market_id']}: {e['reason']}")
            
        self.assertIn("stagnant_1", market_ids)
        self.assertTrue(any("STAGNATION" in r for r in exit_reasons))
        
        self.assertNotIn("fresh_1", market_ids)
        self.assertNotIn("profitable_old", market_ids)
        
        print("Stagnation Killer Verification PASSED")

if __name__ == "__main__":
    unittest.main()

if __name__ == "__main__":
    unittest.main()
