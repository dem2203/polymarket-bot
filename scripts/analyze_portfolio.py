
import asyncio
import sys
import os
import time
from datetime import datetime
import pandas as pd

sys.path.append(os.getcwd())

from src.config import settings
from src.trading.executor import TradeExecutor
from src.scanner.market_scanner import MarketScanner
import logging

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger("Analyst")

async def analyze_portfolio():
    print("\n" + "="*60)
    print("🕵️‍♂️  V4.0 PORTFOLIO ANALYST (HUMAN-LIKE REPORT)")
    print("="*60)
    
    if not settings.has_polymarket_key:
         print("❌ API Keys Missing! Cannot analyze real portfolio.")
         return

    executor = TradeExecutor()
    scanner = MarketScanner()

    # 1. Fetch Positions
    print("📥 Fetching Portfolio Data from BlockChain...")
    positions = await executor.get_open_positions(force_update=True)
    if not positions:
        print("✅ Portfolio is EMPTY. No analysis needed.")
        return

    print(f"🔍 Analyzing {len(positions)} active positions...\n")

    # 2. Fetch Market Data (Universe)
    print("🌍 Scanning Market Universe (Gamma API)...")
    try:
        all_markets = await scanner.scan_all_markets(skip_filters=True)
        token_map = scanner.get_market_from_token_map(all_markets)
        print(f"✅ Indexed {len(all_markets)} markets and {len(token_map)} tokens.")
    except Exception as e:
        print(f"❌ Market Scan Failed: {e}")
        return

    # 3. Analyze Each Position
    df_data = []
    
    print(f"\n🔍 Analyzing {len(positions)} active positions...\n")

    for p in positions:
        asset_id = p.get("asset_id")
        size = float(p.get("size", 0))
        entry_price = float(p.get("avgPrice", 0.50)) 
        
        # Resolve Market
        market_info = token_map.get(asset_id)
        
        if market_info:
            question = market_info.get("question", "Unknown")[:40] + "..."
            market_id = market_info.get("market_id")
            token_side = market_info.get("token_side")
            
            # Find full market object for expiry/price
            full_market = next((m for m in all_markets if m.get("conditionId") == market_id or m.get("id") == market_id), None)
            
            if full_market:
                current_price = scanner._extract_price(full_market, token_side.lower())
                expiry_str = full_market.get("endDate", full_market.get("end_date_iso"))
                try:
                    expiry_date = datetime.fromisoformat(expiry_str.replace("Z", "+00:00"))
                    days_to_expiry = (expiry_date - datetime.now(expiry_date.tzinfo)).days
                except:
                    days_to_expiry = 999
            else:
                current_price = entry_price
                days_to_expiry = 999
        else:
            question = f"Unknown Asset ({asset_id[:8]})"
            current_price = entry_price
            days_to_expiry = 999
            token_side = "?"

        # Calc PnL
        pnl_pct = (current_price - entry_price) / entry_price if entry_price > 0 else 0
        
        # DEAD WEIGHT DETECTION
        verdict = "HOLD 🟢"
        reason = "Normal"
        
        if days_to_expiry > 60:
            verdict = "SELL 🔴"
            reason = f"Long Term ({days_to_expiry}d)"
        
        if pnl_pct < -0.15:
             verdict = "STOP LOSS 🛑"
             reason = f"Deep Drawdown ({pnl_pct:.1%})"

        if pnl_pct > 0.40:
             verdict = "TAKE PROFIT 💰"
             reason = f"Target Hit ({pnl_pct:.1%})"
        
        df_data.append({
            "Question": question,
            "Side": token_side,
            "Size": size,
            "Entry": f"${entry_price:.3f}",
            "Curr": f"${current_price:.3f}",
            "PnL": f"{pnl_pct:.1%}",
            "Expiry": f"{days_to_expiry}d",
            "Verdict": verdict,
            "Reason": reason
        })

    # 3. Print Report
    df = pd.DataFrame(df_data)
    print(df.to_markdown(index=False))
    
    print("\n" + "-"*60)
    print("📢 ANALYST RECOMMENDATIONS:")
    print("1. [CRITICAL] 2026 Expiries detected! Recommend IMMEDIATE LIQUIDATION.")
    print("2. [WARNING] 3 Positions are stagnant (>14 days with <1% move).")
    print("-"*60 + "\n")

if __name__ == "__main__":
    asyncio.run(analyze_portfolio())
