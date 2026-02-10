"""
Polymarket L1/L2 Kimlik Doğrulama
- L1: Private key ile EIP-712 imzalama
- L2: API key/secret/passphrase oluşturma
"""

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import ApiCreds
from src.config import settings
from src.utils import logger


class PolymarketAuth:
    """Polymarket CLOB API kimlik doğrulama yöneticisi."""

    def __init__(self):
        self._client: ClobClient | None = None
        self._api_creds: ApiCreds | None = None

    def _get_base_client(self) -> ClobClient:
        """Temel CLOB client oluştur (API creds olmadan)."""
        return ClobClient(
            host=settings.clob_api_url,
            chain_id=settings.chain_id,
            key=settings.polymarket_private_key,
            signature_type=settings.polymarket_signature_type,
            funder=settings.polymarket_funder_address or None,
        )

    def derive_api_credentials(self) -> ApiCreds:
        """L2 API credential'larını oluştur veya türet."""
        if self._api_creds:
            return self._api_creds

        # Önce .env'den kontrol et
        if settings.has_api_creds:
            self._api_creds = ApiCreds(
                api_key=settings.polymarket_api_key,
                api_secret=settings.polymarket_api_secret,
                api_passphrase=settings.polymarket_passphrase,
            )
            logger.info("✅ API credentials .env dosyasından yüklendi")
            return self._api_creds

        # Yoksa türet
        logger.info("🔑 API credentials türetiliyor...")
        base_client = self._get_base_client()
        self._api_creds = base_client.derive_api_key()
        logger.info("✅ API credentials başarıyla türetildi")
        logger.info(
            f"   API Key: {self._api_creds.api_key[:8]}..."
        )
        logger.info(
            "   💡 Bu değerleri .env dosyanıza kaydedin:\n"
            f"   POLYMARKET_API_KEY={self._api_creds.api_key}\n"
            f"   POLYMARKET_API_SECRET={self._api_creds.api_secret}\n"
            f"   POLYMARKET_PASSPHRASE={self._api_creds.api_passphrase}"
        )
        return self._api_creds

    def get_authenticated_client(self) -> ClobClient:
        """Tam yetkili CLOB client döndür."""
        if self._client:
            return self._client

        creds = self.derive_api_credentials()

        self._client = ClobClient(
            host=settings.clob_api_url,
            chain_id=settings.chain_id,
            key=settings.polymarket_private_key,
            signature_type=settings.polymarket_signature_type,
            funder=settings.polymarket_funder_address or None,
            creds=creds,
        )
        logger.info("✅ Authenticated CLOB client hazır")
        return self._client

    def verify_connection(self) -> bool:
        """API bağlantısını doğrula."""
        try:
            client = self.get_authenticated_client()
            # Basit bir API çağrısı yap
            server_time = client.get_server_time()
            logger.info(f"✅ Polymarket bağlantısı doğrulandı | Sunucu zamanı: {server_time}")
            return True
        except Exception as e:
            logger.error(f"❌ Polymarket bağlantı hatası: {e}")
            return False
