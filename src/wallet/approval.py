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
NEG_RISK_ADAPTER = "0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296"  # Neg Risk Adapter
CONDITIONAL_TOKENS = "0x4D97DCd97eC945f40cF65F87097ACe5EA0476045" # Conditional Tokens Framework

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
    """USDC için Polymarket Exchange, Neg Risk Adapter ve CTF'ye harcama izni ver."""
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
        
        # Approve edilecek TÜM kontratlar
        targets = [
            ("CTF Exchange", CTF_EXCHANGE),
            ("Neg Risk Adapter", NEG_RISK_ADAPTER),
            ("Conditional Token Framework", CONDITIONAL_TOKENS)
        ]

        MAX_UINT256 = 2**256 - 1

        for name, spender in targets:
            # Mevcut izni kontrol et
            try:
                allowance = usdc.functions.allowance(my_address, spender).call()
                logger.info(f"💰 {name} Allowance: {allowance / 1e6:.2f} USDC")

                if allowance < 1000 * 1e6:
                    logger.info(f"🔓 {name} allowance artırılıyor (Unlimited)...")
                    
                    # Transaction hazırla
                    nonce = w3.eth.get_transaction_count(my_address)
                    
                    # Gaz fiyatını biraz artır (hızlı onay için)
                    gas_price = int(w3.eth.gas_price * 1.1)

                    tx = usdc.functions.approve(spender, MAX_UINT256).build_transaction({
                        'from': my_address,
                        'nonce': nonce,
                        'gas': 100000,
                        'gasPrice': gas_price,
                    })
                    
                    # İmzala ve gönder
                    signed_tx = w3.eth.account.sign_transaction(tx, pk)
                    
                    # Farklı versiyonlar için attribute kontrolü
                    raw_tx = getattr(signed_tx, 'rawTransaction', None)
                    if raw_tx is None:
                        raw_tx = getattr(signed_tx, 'raw_transaction', None)
                        
                    if raw_tx is None:
                        logger.error(f"❌ {name}: SignedTransaction attribute hatası.")
                        continue

                    tx_hash = w3.eth.send_raw_transaction(raw_tx)
                    
                    logger.info(f"✅ {name} Approve TX gönderildi: {w3.to_hex(tx_hash)}")
                    logger.info("⏳ Onay bekleniyor... (5sn)")
                    
                    # Nonce çakışmasını önlemek ve zincire yazılmasını beklemek için
                    time.sleep(5) 
                else:
                    logger.info(f"✅ {name} allowance yeterli.")
                    
            except Exception as e:
                logger.error(f"❌ {name} işlem hatası: {e}")

    except Exception as e:
        logger.error(f"❌ Genel Wallet Hatası: {e}")
