import os
import sys
from dotenv import load_dotenv
load_dotenv()

from py_clob_client.client import ClobClient
from src.config import settings

def diagnose():
    try:
        if not settings.polymarket_private_key:
            print("[X] Private key missing")
            return

        pk = settings.polymarket_private_key.strip().replace('"', '').replace("'", "")
        client = ClobClient(
            host=settings.clob_api_url,
            key=pk,
            chain_id=137
        )
        print("[OK] Client init success")
        
        # Inspect methods
        methods = [m for m in dir(client) if not m.startswith("_")]
        print(f"[INFO] Available methods ({len(methods)}):")
        for m in methods:
            print(f" - {m}")
            
    except Exception as e:
        print(f"[X] Error: {e}")

if __name__ == "__main__":
    diagnose()
