
import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from src.config import settings
from src.trading.executor import TradeExecutor
from src.scanner.market_scanner import MarketScanner
import aiohttp

import logging

# Configure logging to show INFO level
logging.basicConfig(level=logging.INFO)

async def main():
    print("DIAGNOSIS: Fetching Open Positions...")
    
    executor = TradeExecutor()
    scanner = MarketScanner()
    
    # 1. Get Positions
    positions = await executor.get_open_positions()
    
    if not positions:
        print("No open positions found via API/Trade History.")
        return

    print(f"Found {len(positions)} positions:")
    for p in positions:
        print(f"   - {p}")

    # 2. Try to resolve Market ID for the first position
    first_token = positions[0].get("asset_id")
    if not first_token:
        print("No asset_id in position data.")
        return

    print(f"\nResolving Market for Token: {first_token}")
    
    # Try Gamma API with various params
    async with aiohttp.ClientSession() as session:
        # Try finding by token_id (guessing endpoint)
        # Gamma API usually supports filtering by token_id
        url = f"{settings.gamma_api_url}/markets"
        params = {"clob_token_id": first_token}
        
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data:
                    m = data[0] if isinstance(data, list) else data
                    print(f"SUCCESS! Found Market: {m.get('question')}")
                    print(f"   ID: {m.get('id')}")
                    print(f"   Condition ID: {m.get('conditionId')}")
                else:
                    print("Gamma API returned empty list for token_id.")
            else:
                print(f"Gamma API Error: {resp.status}")

if __name__ == "__main__":
    asyncio.run(main())
