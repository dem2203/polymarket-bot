"""
CLOB Client Wrapper - Order book, fiyat, spread sorgulama.
py-clob-client SDK üzerinde ince katman.
"""

from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderBookSummary
from src.wallet.auth import PolymarketAuth
from src.utils import logger


class ClobManager:
    """Polymarket CLOB API - Order book ve fiyat verileri."""

    def __init__(self, auth: PolymarketAuth):
        self.auth = auth
        self._client: ClobClient | None = None

    @property
    def client(self) -> ClobClient:
        if not self._client:
            self._client = self.auth.get_authenticated_client()
        return self._client

    def get_order_book(self, token_id: str) -> dict:
        """Bir token'ın order book'unu getir."""
        try:
            book: OrderBookSummary = self.client.get_order_book(token_id)
            return {
                "token_id": token_id,
                "bids": book.bids if hasattr(book, "bids") else [],
                "asks": book.asks if hasattr(book, "asks") else [],
                "spread": self._calc_spread(book),
            }
        except Exception as e:
            logger.error(f"❌ Order book hatası [{token_id[:8]}...]: {e}")
            return {"token_id": token_id, "bids": [], "asks": [], "spread": 0}

    def get_price(self, token_id: str) -> float:
        """Token'ın güncel fiyatını al."""
        try:
            price = self.client.get_price(token_id)
            return float(price)
        except Exception as e:
            logger.error(f"❌ Fiyat sorgulama hatası [{token_id[:8]}...]: {e}")
            return 0.0

    def get_midpoint(self, token_id: str) -> float:
        """Token'ın midpoint fiyatını al."""
        try:
            midpoint = self.client.get_midpoint(token_id)
            return float(midpoint)
        except Exception as e:
            logger.error(f"❌ Midpoint hatası [{token_id[:8]}...]: {e}")
            return 0.0

    def get_spread(self, token_id: str) -> float:
        """Token'ın bid-ask spread'ini hesapla."""
        try:
            spread = self.client.get_spread(token_id)
            return float(spread)
        except Exception as e:
            logger.error(f"❌ Spread hatası [{token_id[:8]}...]: {e}")
            return 0.0

    def get_market_snapshot(self, token_id: str) -> dict:
        """Market'in anlık tam görüntüsünü al."""
        price = self.get_price(token_id)
        midpoint = self.get_midpoint(token_id)
        spread = self.get_spread(token_id)
        book = self.get_order_book(token_id)

        snapshot = {
            "token_id": token_id,
            "price": price,
            "midpoint": midpoint,
            "spread": spread,
            "bid_depth": len(book.get("bids", [])),
            "ask_depth": len(book.get("asks", [])),
            "top_bid": float(book["bids"][0]["price"]) if book.get("bids") else 0,
            "top_ask": float(book["asks"][0]["price"]) if book.get("asks") else 0,
        }

        logger.debug(
            f"📸 Snapshot [{token_id[:8]}...]: "
            f"Price={price:.4f} Mid={midpoint:.4f} Spread={spread:.4f}"
        )
        return snapshot

    @staticmethod
    def _calc_spread(book: OrderBookSummary) -> float:
        """Order book'tan spread hesapla."""
        try:
            bids = book.bids if hasattr(book, "bids") else []
            asks = book.asks if hasattr(book, "asks") else []
            if bids and asks:
                best_bid = float(bids[0]["price"])
                best_ask = float(asks[0]["price"])
                return best_ask - best_bid
        except (IndexError, KeyError, TypeError):
            pass
        return 0.0
