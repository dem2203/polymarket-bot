import os
import sys
from web3 import Web3
from eth_account import Account
import logging

# Add src to path
sys.path.append(os.getcwd())
from src.config import settings

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("diagnose")

# Constants
RPC_URL = "https://polygon-rpc.com"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174" # USDC.e
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"
NEG_RISK_EXCHANGE = "0xC5d563A36AE78145C45a50134d48A1215220f80a"

ERC20_ABI = [
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}], "name": "balanceOf", "outputs": [{"name": "balance", "type": "uint256"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "_owner", "type": "address"}, {"name": "_spender", "type": "address"}], "name": "allowance", "outputs": [{"name": "", "type": "uint256"}], "type": "function"}
]

def diagnose():
    if not settings.polymarket_private_key:
        logger.error("No Private Key found.")
        return

    pk = settings.polymarket_private_key.strip().replace('"', '').replace("'", "")
    account = Account.from_key(pk)
    eoa_address = account.address
    
    logger.info(f"🔑 EOA Address: {eoa_address}")

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        logger.error("RPC Connection failed")
        return

    usdc = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)

    # 1. Check EOA Balance
    eoa_bal = usdc.functions.balanceOf(eoa_address).call()
    logger.info(f"💰 EOA Balance: {eoa_bal / 1e6:.2f} USDC")

    # 2. Check EOA Allowances
    allow_ctf = usdc.functions.allowance(eoa_address, CTF_EXCHANGE).call()
    allow_neg = usdc.functions.allowance(eoa_address, NEG_RISK_EXCHANGE).call()
    
    logger.info(f"🔓 EOA -> CTF Exchange Allowance: {allow_ctf / 1e6:.2f} USDC")
    logger.info(f"🔓 EOA -> Neg Risk Exchange Allowance: {allow_neg / 1e6:.2f} USDC")

    # 3. Try to find Proxy
    # We can try to guess/derive or use ClobClient if installed
    try:
        from py_clob_client.client import ClobClient
        from py_clob_client.clob_types import ApiCreds
        
        # Init ClobClient (L1)
        client = ClobClient(
            "https://clob.polymarket.com", 
            key=pk, 
            chain_id=137
        )
        
        # Try to get API Creds derived
        creds = client.derive_api_key()
        logger.info("✅ API Key Derived successfully")
        
        # Check if we can get user info (which usually returns proxy)
        # Assuming there is a method for this, otherwise we skip
        # client.get_profile()? No such method usually exposed easily.
        
        # But we can try to get balance via Client
        client_bal = client.get_balance()
        logger.info(f"🏦 Client Reported Balance (API): {client_bal}")
        
    except Exception as e:
        logger.error(f"Failed to init Client: {e}")

if __name__ == "__main__":
    diagnose()
