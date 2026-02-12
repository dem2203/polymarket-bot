import os
import sys

# Add src to path just in case
sys.path.append(os.getcwd())

from py_clob_client.constants import POLYGON
from py_clob_client.client import ClobClient

def check_addresses():
    print("--- Checking Client Addresses ---")
    
    # Initialize minimal client
    # We don't need keys to check constants/methods usually, but instantiation might require them
    # We will try to inspect the class or constants directly if possible, or instance.
    
    try:
        from py_clob_client.constants import (
            POLYGON_EXCHANGE, 
            POLYGON_NEG_RISK_ADAPTER, 
            POLYGON_NEG_RISK_EXCHANGE
        )
        print(f"POLYGON_EXCHANGE: {POLYGON_EXCHANGE}")
        print(f"POLYGON_NEG_RISK_ADAPTER: {POLYGON_NEG_RISK_ADAPTER}")
        print(f"POLYGON_NEG_RISK_EXCHANGE: {POLYGON_NEG_RISK_EXCHANGE}")
    except ImportError as e:
        print(f"Direct import failed: {e}")
        
    # Try dynamic inspection of constants module
    import py_clob_client.constants as C
    print("\nAll Constants in module:")
    for key in dir(C):
        if "ADDR" in key or "EXCHANGE" in key or "NEG" in key:
            print(f"{key}: {getattr(C, key)}")

if __name__ == "__main__":
    check_addresses()
