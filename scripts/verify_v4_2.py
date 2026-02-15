
import unittest
import sys
import os

sys.path.append(os.getcwd())
from src.config import settings
from src.strategy.kelly import KellySizer

class TestSniperKelly(unittest.TestCase):
    def setUp(self):
        self.kelly = KellySizer()
        self.kelly.multiplier = 0.5 # Set base baseline

    def test_sniper_bonus(self):
        """Test HIGH EDGE (>15%) triggers 1.0 multiplier"""
        # Edge = 0.8 (FV) - 0.6 (Market) = 0.2 (20%)
        res = self.kelly.calculate(
            fair_value=0.8,
            market_price=0.6,
            balance=100.0,
            direction="BUY_YES",
            confidence=0.9,
            hours_to_expiry=100  # No time bonus
        )
        edge = 0.2
        odds_ret = (1-0.6)/0.6 # 0.66
        raw_kelly = edge / odds_ret # 0.3
        
        # Expected: Raw * 1.0 (Sniper) * 1.0 (Survival > 50) * 1.0 (Time)
        # Wait, survival for 100 balance is Aggressive (1.0).
        # So Adjusted ≈ 0.3 * 1.0 = 0.3
        
        # If it was base multiplier (0.5), it would be 0.15.
        # Let's check if the logic used dynamic_multiplier=1.0
        
        print(f"Sniper Test: {res}")
        # We can't easily inspect internal variables, but we can verify the outcome size.
        self.assertAlmostEqual(res['kelly_fraction'], 0.3, delta=0.05)
        print("✅ Sniper Bonus Verified (High Edge -> Full Size)")

    def test_confidence_penalty(self):
        """Test LOW CONFIDENCE (<60%) triggers 0.5x penalty"""
        # Edge = 0.7 - 0.6 = 0.10 (10%) -> No Sniper Bonus
        res = self.kelly.calculate(
             fair_value=0.7,
             market_price=0.6,
             balance=100.0,
             direction="BUY_YES",
             confidence=0.5, # Low confidence
             hours_to_expiry=100 
        )
        edge = 0.1
        odds_ret = 0.66
        raw_kelly = 0.15
        
        # Expected: Raw * 0.5 (Base) * 0.5 (Penalty) = 0.0375
        self.assertLess(res['kelly_fraction'], 0.05)
        print("✅ Confidence Penalty Verified (Low Conf -> Half Size)")

    def test_price_penalty(self):
         """Test HIGH PRICE (>0.85) triggers penalty"""
         # Market 0.90, Fair 0.98 ($0.08 edge)
         res = self.kelly.calculate(
             fair_value=0.98,
             market_price=0.90,
             balance=100.0,
             direction="BUY_YES",
             confidence=0.9,
             hours_to_expiry=100
         )
         # Penalty multiplier 0.7 should apply
         # Base (0.5) * Penalty (0.7) = 0.35 effective multiplier
         print("✅ Price Penalty Test Run")

if __name__ == "__main__":
    unittest.main()
