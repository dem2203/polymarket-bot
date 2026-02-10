"""
Wallet Manager - Bakiye sorgulama, token allowance yönetimi.
"""

from py_clob_client.client import ClobClient
from src.wallet.auth import PolymarketAuth
from src.utils import logger


class WalletManager:
    """Polymarket wallet ve bakiye yönetimi."""

    def __init__(self, auth: PolymarketAuth):
        self.auth = auth
        self._client: ClobClient | None = None

    @property
    def client(self) -> ClobClient:
        if not self._client:
            self._client = self.auth.get_authenticated_client()
        return self._client

    def setup_allowances(self) -> bool:
        """USDC ve Conditional Token allowance'larını ayarla."""
        try:
            logger.info("🔧 Token allowance'ları ayarlanıyor...")
            self.client.set_allowances()
            logger.info("✅ Token allowance'ları başarıyla ayarlandı")
            return True
        except Exception as e:
            logger.error(f"❌ Allowance ayarlama hatası: {e}")
            return False

    def get_balance(self) -> dict:
        """Wallet USDC bakiyesini ve pozisyonları getir."""
        try:
            # Bakiye bilgilerini al
            balance_allowance = self.client.get_balance_allowance()
            result = {
                "balance": float(balance_allowance.get("balance", 0)),
                "allowance": float(balance_allowance.get("allowance", 0)),
            }
            logger.info(
                f"💰 Wallet Bakiye: ${result['balance']:.2f} USDC | "
                f"Allowance: ${result['allowance']:.2f}"
            )
            return result
        except Exception as e:
            logger.error(f"❌ Bakiye sorgulama hatası: {e}")
            return {"balance": 0, "allowance": 0}

    def get_health_report(self) -> dict:
        """Wallet sağlık durumu raporu."""
        report = {
            "connected": False,
            "balance": 0,
            "allowance": 0,
            "ready_to_trade": False,
        }

        try:
            if self.auth.verify_connection():
                report["connected"] = True
                balance_info = self.get_balance()
                report["balance"] = balance_info["balance"]
                report["allowance"] = balance_info["allowance"]
                report["ready_to_trade"] = (
                    report["balance"] > 0 and report["allowance"] > 0
                )
        except Exception as e:
            logger.error(f"❌ Sağlık kontrolü hatası: {e}")

        return report
