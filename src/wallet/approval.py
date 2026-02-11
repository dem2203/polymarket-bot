import logging
import time
from web3 import Web3
from eth_account import Account

from src.config import settings

logger = logging.getLogger("bot.wallet")

# Polygon Constants
RPC_URL = "https://polygon-rpc.com"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"  # USDC.e (Bridged)
CTF_EXCHANGE = "0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E"  # Polymarket Exchange
MAX_UINT256 = 2**256 - 1

# Minimal ERC20 ABI for approve/allowance
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [
            {"name": "_owner", "type": "address"},
            {"name": "_spender", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [{"name": "", "type": "uint256"}],
        "type": "function"
    },
    {
        "constant": False,
        "inputs": [
            {"name": "_spender", "type": "address"},
            {"name": "_value", "type": "uint256"}
        ],
        "name": "approve",
        "outputs": [{"name": "", "type": "bool"}],
        "type": "function"
    }
]

def check_and_approve():
    """USDC için Polymarket Exchange'e harcama izni (allowance) ver."""
    if not settings.polymarket_private_key:
        logger.warning("Private key yok, approval atlanıyor.")
        return

    try:
        # Key temizle
        pk = settings.polymarket_private_key.strip().replace('"', '').replace("'", "")
        account = Account.from_key(pk)
        my_address = account.address
        
        logger.info(f"💳 Cüzdan kontrol ediliyor: {my_address}")

        w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if not w3.is_connected():
            logger.error("❌ Polygon RPC bağlantısı başarısız.")
            return

        usdc = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
        
        # Mevcut izni kontrol et
        allowance = usdc.functions.allowance(my_address, CTF_EXCHANGE).call()
        logger.info(f"💰 Mevcut Allowance: {allowance / 1e6:.2f} USDC")

        if allowance < 1000 * 1e6:  # 1000 USDC'den azsa yenile
            logger.info("🔓 Allowance artırılıyor (Unlimited)...")
            
            # Transaction hazırla
            tx = usdc.functions.approve(CTF_EXCHANGE, MAX_UINT256).build_transaction({
                'from': my_address,
                'nonce': w3.eth.get_transaction_count(my_address),
                'gas': 100000,
                'gasPrice': w3.eth.gas_price,
            })
            
            # İmzala ve gönder
            signed_tx = w3.eth.account.sign_transaction(tx, pk)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            logger.info(f"✅ Approve TX gönderildi: {w3.to_hex(tx_hash)}")
            logger.info("⏳ Onay bekleniyor...")
            
            # Basit bekleme
            time.sleep(5) 
            
            # Tekrar kontrol (opsiyonel)
            new_allowance = usdc.functions.allowance(my_address, CTF_EXCHANGE).call()
            logger.info(f"💰 Yeni Allowance: {new_allowance / 1e6:.2f} USDC")
        else:
            logger.info("✅ Allowance yeterli.")

    except Exception as e:
        logger.error(f"❌ Allowance hatası: {e}")
