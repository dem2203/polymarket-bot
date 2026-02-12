import os
import requests
import logging
from collections import defaultdict
from dotenv import load_dotenv
from py_clob_client.client import ClobClient
from src.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("checker")

def check_positions():
    load_dotenv()
    
    if not settings.polymarket_private_key:
        print("[X] Private key missing in .env")
        return

    print("[*] Connecting to Polymarket CLOB...")
    host = "https://clob.polymarket.com"
    key = settings.polymarket_private_key
    chain_id = 137
    client = ClobClient(host, key=key, chain_id=chain_id)
    client.set_api_creds(client.create_or_derive_api_creds())
    
    # 1. Try Raw Positions Endpoint
    print("\n[1] Testing /data/positions...")
    headers = {
        "POLY-API-KEY": client.creds.api_key,
        "POLY-API-SECRET": client.creds.api_secret,
        "POLY-PASSPHRASE": client.creds.api_passphrase,
    }
    try:
        resp = requests.get(f"{host}/data/positions", headers=headers, params={"limit": "100"})
        if resp.status_code == 200:
            pos = [p for p in resp.json() if float(p.get("size", 0)) > 0]
            print(f"[OK] /data/positions returned {len(pos)} positions.")
            if pos: return
        else:
            print(f"[X] /data/positions failed: {resp.status_code}")
    except Exception as e:
        print(f"[X] /data/positions error: {e}")

    # 2. Try Trade Reconstruction (V3.3.5 Logic)
    print("\n[2] Testing Trade Reconstruction (Deep Fallback)...")
    try:
        trades = []
        next_cursor = ""
        loop = 0
        while loop < 10: # Check last 1000 trades
            params = {"limit": "100"}
            if next_cursor: params["next_cursor"] = next_cursor
            
            resp = requests.get(f"{host}/data/trades", headers=headers, params=params)
            if resp.status_code != 200:
                print(f"[X] Trade fetch failed: {resp.status_code}")
                break
                
            data = resp.json()
            if isinstance(data, list):
                batch = data
                next_cursor = ""
            elif isinstance(data, dict):
                batch = data.get("data", [])
                next_cursor = data.get("next_cursor", "")
            else:
                break
            
            if not batch: break
            trades.extend(batch)
            if not next_cursor or next_cursor == "MA==": break
            loop += 1
            
        print(f"[INFO] Fetched {len(trades)} trades.")
        
        # Calculate
        holdings = defaultdict(float)
        for t in trades:
            aid = t.get("asset_id")
            side = t.get("side")
            size = float(t.get("size", 0))
            if side == "BUY": holdings[aid] += size
            elif side == "SELL": holdings[aid] -= size
            
        open_pos = {k: v for k, v in holdings.items() if v > 0.001}
        print(f"[OK] Reconstructed Open Positions: {len(open_pos)}")
        
        for aid, size in open_pos.items():
            print(f"   - Asset {aid[:10]}... : {size:.2f}")

    except Exception as e:
        print(f"[X] Reconstruction failed: {e}")

if __name__ == "__main__":
    check_positions()
