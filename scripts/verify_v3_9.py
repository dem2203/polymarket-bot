
import sys
import os
import asyncio
import logging

sys.path.append(os.getcwd())

# Setup logging
logging.basicConfig(level=logging.INFO)


def verify_codebase():
    print("Verifying V3.9 Implementation...")
    
    try:
        from src.scanner.market_scanner import MarketScanner
        scanner = MarketScanner()
        if hasattr(scanner, "get_market_from_token_map"):
            print("MarketScanner.get_market_from_token_map exists.")
        else:
            print("MarketScanner.get_market_from_token_map MISSING!")
            
    except Exception as e:
        print(f"MarketScanner Import Error: {e}")

    try:
        from src.trading.executor import TradeExecutor
        executor = TradeExecutor()
        import inspect
        sig = inspect.signature(executor.get_open_positions)
        if "force_update" in sig.parameters:
             print("TradeExecutor.get_open_positions has 'force_update' param.")
        else:
             print("TradeExecutor.get_open_positions missing 'force_update'!")

    except Exception as e:
        print(f"TradeExecutor Import Error: {e}")

    try:
        from main import PolymarketBot
        bot = PolymarketBot()
        if hasattr(bot, "sync_positions_on_startup"):
            print("PolymarketBot.sync_positions_on_startup exists.")
        else:
            print("PolymarketBot.sync_positions_on_startup MISSING!")
        
        # Check start method source for sync call
        import inspect
        src = inspect.getsource(bot.start)
        if "self.sync_positions_on_startup()" in src:
            print("start() calls sync_positions_on_startup().")
        else:
            print("start() does NOT call sync_positions_on_startup()!")

    except Exception as e:
        print(f"Main Bot Import Error: {e}")

if __name__ == "__main__":
    verify_codebase()
