import sys
import os
sys.path.append(os.getcwd())

from src.config import settings
from src.strategy.kelly import KellySizer

def test_sniper_sizing():
    print("Testing Sniper Mode Sizing...")
    
    # Force Sniper Mode
    settings.sniper_mode = True
    settings.sniper_multiplier = 0.5
    settings.kelly_multiplier = 0.2
    settings.max_kelly_fraction = 0.20 # Cap
    
    kelly = KellySizer()
    balance = 100.0
    
    # 1. Normal Trade
    print("\n--- Normal Trade (Conf=0.70, Not Sniper) ---")
    res_normal = kelly.calculate(
        fair_value=0.60, market_price=0.50, balance=balance, 
        direction="BUY_YES", confidence=0.70, is_sniper_trade=False
    )
    print(f"Normal Size: ${res_normal['position_size']} (Fract: {res_normal['kelly_fraction']:.4f})")
    
    # 2. Sniper Trade
    print("\n--- Sniper Trade (Conf=0.95, Sniper=True) ---")
    res_sniper = kelly.calculate(
        fair_value=0.60, market_price=0.50, balance=balance, 
        direction="BUY_YES", confidence=0.95, is_sniper_trade=True
    )
    print(f"Sniper Size: ${res_sniper['position_size']} (Fract: {res_sniper['kelly_fraction']:.4f})")
    
    # Verification
    ratio = res_sniper['position_size'] / max(res_normal['position_size'], 0.01)
    print(f"\nBoost Ratio: {ratio:.2f}x")
    
    if res_sniper['position_size'] > res_normal['position_size']:
        print("SUCCESS: Sniper trade has larger size.")
    else:
        print("FAIL: Sniper trade size is not larger.")

if __name__ == "__main__":
    test_sniper_sizing()
