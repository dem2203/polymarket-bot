"""
Trade Executor — CLOB API ile limit emir yürütme.
DRY_RUN modunda simülasyon yapar.
"""

import logging
import time
import requests
from dataclasses import dataclass, field
from typing import Optional

from web3 import Web3
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, ApiCreds, BalanceAllowanceParams, AssetType
from py_clob_client.order_builder.constants import BUY, SELL

# Polygon Constants (Local)
RPC_URL = "https://polygon-rpc.com"
USDC_ADDRESS = "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"
ERC20_ABI = [{"constant":True,"inputs":[{"name":"_owner","type":"address"}],"name":"balanceOf","outputs":[{"name":"balance","type":"uint256"}],"type":"function"}]

from src.config import settings
from src.strategy.mispricing import TradeSignal

logger = logging.getLogger("bot.executor")


@dataclass
class ExecutedOrder:
    """Yürütülen emir bilgisi."""
    order_id: str
    market_id: str
    question: str
    side: str          # BUY / SELL
    token_side: str    # YES / NO
    price: float
    size: float        # $ cinsinden
    shares: float
    status: str        # FILLED, PENDING, SIMULATED, FAILED
    timestamp: float
    is_simulated: bool = False


class TradeExecutor:
    """CLOB API ile emir yürütme motoru."""

    def __init__(self):
        self.dry_run = settings.dry_run
        self.client: Optional[ClobClient] = None
        self.executed_orders: list[ExecutedOrder] = []
        self._order_counter = 0

        if not self.dry_run and settings.has_polymarket_key:
            self._init_client()

    def _init_client(self):
        """CLOB client başlat ve kimlik doğrula."""
        try:
            # Key'i temizle (boşluk, tırnak vb.)
            pk = settings.polymarket_private_key
            if pk:
                pk = pk.strip().replace('"', '').replace("'", "")

            self.client = ClobClient(
                host=settings.clob_api_url,
                key=pk,
                chain_id=137,  # Polygon
                funder=settings.polymarket_funder_address,  # Proxy Address for funding
                signature_type=1,  # POLY_PROXY (Try output type 1 for Proxy)
            )

            # API credentials
            if settings.polymarket_api_key:
                self.client.set_api_creds(ApiCreds(
                    api_key=settings.polymarket_api_key,
                    api_secret=settings.polymarket_api_secret,
                    api_passphrase=settings.polymarket_passphrase,
                ))
            else:
                # Otomatik türet
                self.client.set_api_creds(self.client.derive_api_key())


            logger.info("✅ CLOB client başlatıldı (LIVE mode)")
        except Exception as e:
            logger.error(f"CLOB client hatası: {e}")
            self.client = None

    async def execute_signal(self, signal: TradeSignal) -> Optional[ExecutedOrder]:
        """
        Trade sinyalini yürüt.
        DRY_RUN modunda simüle eder.
        """
        if self.dry_run:
            return await self._simulate_order(signal)
        else:
            return await self._place_real_order(signal)

    async def _simulate_order(self, signal: TradeSignal) -> ExecutedOrder:
        """DRY_RUN simülasyonu — gerçek emir gönderilmez."""
        self._order_counter += 1
        order_id = f"SIM-{self._order_counter:04d}"

        order = ExecutedOrder(
            order_id=order_id,
            market_id=signal.market_id,
            question=signal.question,
            side="BUY",
            token_side=signal.token_side,
            price=signal.price,
            size=signal.position_size,
            shares=signal.shares,
            status="SIMULATED",
            timestamp=time.time(),
            is_simulated=True,
        )

        self.executed_orders.append(order)
        logger.info(
            f"🔵 [DRY RUN] Simüle edildi: {order_id} | "
            f"{signal.token_side} {signal.shares:.1f} shares @ ${signal.price:.3f} "
            f"(${signal.position_size:.2f}) | {signal.question[:40]}..."
        )
        return order

    async def _place_real_order(self, signal: TradeSignal) -> Optional[ExecutedOrder]:
        """Gerçek limit emir gönder."""
        if not self.client:
            logger.error("❌ CLOB client hazır değil — emir gönderilemedi")
            return None

        try:
            # Token ID al
            token_id = self._get_token_id(signal)
            if not token_id:
                logger.error(f"Token ID bulunamadı: {signal.market_id}")
                return None

            # Limit order oluştur
            order_args = OrderArgs(
                price=round(signal.price, 2),
                size=round(signal.shares, 2),
                side=BUY,
                token_id=token_id,
            )

            response = self.client.create_and_post_order(order_args)

            self._order_counter += 1
            order_id = response.get("orderID", f"LIVE-{self._order_counter:04d}")

            order = ExecutedOrder(
                order_id=order_id,
                market_id=signal.market_id,
                question=signal.question,
                side="BUY",
                token_side=signal.token_side,
                price=signal.price,
                size=signal.position_size,
                shares=signal.shares,
                status="PENDING",
                timestamp=time.time(),
                is_simulated=False,
            )

            self.executed_orders.append(order)
            logger.info(
                f"🟢 [LIVE] Emir gönderildi: {order_id} | "
                f"{signal.token_side} {signal.shares:.1f} shares @ ${signal.price:.3f} "
                f"(${signal.position_size:.2f})"
            )
            return order

        except Exception as e:
            logger.error(f"❌ Emir gönderme hatası: {e}")
            return None

    def _get_token_id(self, signal: TradeSignal) -> Optional[str]:
        """Sinyal'den doğru token ID'sini al."""
        tokens = signal.tokens
        if not tokens:
            return None

        if signal.token_side == "YES":
            return tokens[0] if isinstance(tokens[0], str) else str(tokens[0])
        else:
            return tokens[1] if len(tokens) > 1 else None

    async def cancel_specific_order(self, order_id: str) -> bool:
        """Belirli bir emri iptal et."""
        if self.dry_run:
            logger.info(f"🔵 [DRY RUN] İptal simüle: {order_id}")
            return True

        if not self.client:
            return False

        try:
            self.client.cancel(order_id)
            logger.info(f"🗑️ Emir iptal edildi: {order_id}")
            return True
        except Exception as e:
            logger.error(f"❌ İptal hatası ({order_id}): {e}")
            return False

    async def cancel_all_open_orders(self):
        """Tüm açık emirleri iptal et."""
        if self.dry_run:
            # logger.info("🔵 [DRY RUN] Tüm açık emirler iptal silindi (simüle)")
            return

        orders = self.get_open_orders()
        if not orders:
            return

        logger.info(f"🧹 {len(orders)} açık emir temizleniyor (sermaye serbest bırakılıyor)...")
        for order in orders:
            order_id = order.get("orderID")
            if order_id:
                await self.cancel_specific_order(order_id)

    async def sell_position(self, token_id: str, shares: float, price: float) -> Optional[ExecutedOrder]:
        """
        Pozisyon sat — SELL emri gönder.
        SL/TP tetiklendiğinde çağrılır.
        """
        if self.dry_run:
            self._order_counter += 1
            order_id = f"SIM-SELL-{self._order_counter:04d}"
            logger.info(f"🔵 [DRY RUN] SELL simüle: {order_id} | {shares:.1f} shares @ ${price:.3f}")
            return ExecutedOrder(
                order_id=order_id, market_id="", question="",
                side="SELL", token_side="", price=price,
                size=shares * price, shares=shares,
                status="SIMULATED", timestamp=time.time(), is_simulated=True,
            )

        if not self.client:
            logger.error("❌ CLOB client hazır değil — SELL gönderilemedi")
            return None

        try:
            order_args = OrderArgs(
                price=round(price, 2),
                size=round(shares, 2),
                side=SELL,
                token_id=token_id,
            )

            response = self.client.create_and_post_order(order_args)
            self._order_counter += 1
            order_id = response.get("orderID", f"SELL-{self._order_counter:04d}")

            order = ExecutedOrder(
                order_id=order_id, market_id="", question="",
                side="SELL", token_side="", price=price,
                size=shares * price, shares=shares,
                status="PENDING", timestamp=time.time(), is_simulated=False,
            )
            self.executed_orders.append(order)
            logger.info(f"🔴 [LIVE] SELL emri gönderildi: {order_id} | {shares:.1f} shares @ ${price:.3f}")
            return order

        except Exception as e:
            logger.error(f"❌ SELL emri hatası: {e}")
            return None

    def get_open_orders(self) -> list:
        """Açık emirleri sorgula."""
        if not self.client:
            return []
        try:
            return self.client.get_orders() or []
        except Exception as e:
            logger.warning(f"Açık emir sorgusu hatası: {e}")
            return []

    def get_balance(self) -> float:
        """Mevcut USDC bakiyesini sorgula."""
        if self.dry_run or not self.client:
            return settings.starting_balance

        # Try API
        bal_api = 0.0
        try:
            params = BalanceAllowanceParams(asset_type=AssetType.COLLATERAL, signature_type=1)
            balance_resp = self.client.get_balance_allowance(params)
            if balance_resp:
                bal_api = float(balance_resp.get("balance", "0")) / 1e6
        except Exception as e:
            logger.warning(f"API Bakiye hatası: {e}")

        if bal_api > 0.5:
            return bal_api
            
        # Try Web3 Fallback (Proxy Balance)
        try:
            proxy = settings.polymarket_funder_address
            if proxy:
                w3 = Web3(Web3.HTTPProvider(RPC_URL))
                checksum_addr = Web3.to_checksum_address(proxy)
                contract = w3.eth.contract(address=USDC_ADDRESS, abi=ERC20_ABI)
                balance_wei = contract.functions.balanceOf(checksum_addr).call()
                bal_web3 = balance_wei / 1e6
                logger.info(f"💰 Web3 Bakiye (Fallback): {bal_web3:.2f} USDC")
                return bal_web3
        except Exception as e:
            logger.warning(f"Web3 Bakiye hatası: {e}")

        return settings.starting_balance

    def get_order_stats(self) -> dict:
        """Emir istatistikleri."""
        total = len(self.executed_orders)
        simulated = sum(1 for o in self.executed_orders if o.is_simulated)
        live = total - simulated
        total_volume = sum(o.size for o in self.executed_orders)

        return {
            "total_orders": total,
            "simulated": simulated,
            "live": live,
            "total_volume": round(total_volume, 2),
        }



    async def get_open_positions(self) -> list[dict]:
        """
        Polymarket API'den açık pozisyonları getir.
        Fallback Zinciri:
        1. client.get_positions() (Varsa)
        2. GET /data/positions (Raw)
        3. GET /data/trades (Raw) -> Reconstruct (Son çare)
        """
        if self.dry_run or not self.client:
            logger.info("⏸️ DRY RUN veya Client yok, pozisyon senkronizasyonu atlandı.")
            return []

        # 1. Try Library Method (If available in future)
        if hasattr(self.client, "get_positions"):
            try:
                positions = self.client.get_positions(limit=100, offset=0)
                return [p for p in positions if float(p.get("size", 0)) > 0]
            except Exception as e:
                logger.warning(f"Library get_positions failed: {e}")

        # 2. Try Raw Request (Official Endpoint)
        try:
            if hasattr(self.client, "creds") and self.client.creds:
                creds = self.client.creds
                headers = {
                    "POLY-API-KEY": creds.api_key,
                    "POLY-API-SECRET": creds.api_secret,
                    "POLY-PASSPHRASE": creds.api_passphrase,
                }
                
                # Try with params
                url = f"{settings.clob_api_url}/data/positions"
                params = {"limit": "100", "offset": "0"}
                resp = requests.get(url, headers=headers, params=params)
                
                if resp.status_code == 200:
                    positions = resp.json()
                    if isinstance(positions, list):
                        logger.info(f"🌍 RAW API: {len(positions)} pozisyon bulundu.")
                        return [p for p in positions if float(p.get("size", 0)) > 0]
                else:
                    logger.warning(f"RAW API (/data/positions) failed: {resp.status_code}")

        except Exception as e:
            logger.error(f"Raw Request error: {e}")

        # 3. Fallback: Reconstruct from Trades (Slow but works)
        logger.info("⚠️ Pozisyon endpointleri başarısız. Trade geçmişinden hesaplanıyor...")
        return self._derive_positions_from_trades()

    def _derive_positions_from_trades(self) -> list[dict]:
        """Trade geçmişini tarayarak açık pozisyonları hesapla."""
        try:
            trades = []
            # RAW REQUEST for trades (safe against library version issues)
            # Endpoint: /data/trades
            
            if hasattr(self.client, "creds") and self.client.creds:
                headers = {
                    "POLY-API-KEY": self.client.creds.api_key,
                    "POLY-API-SECRET": self.client.creds.api_secret,
                    "POLY-PASSPHRASE": self.client.creds.api_passphrase,
                }
                
                # Pagination loop
                next_cursor = ""
                loop_count = 0
                
                while loop_count < 5: # Max 5 loops (500 trades likely enough)
                    url = f"{settings.clob_api_url}/data/trades"
                    params = {"limit": "100"}
                    if next_cursor:
                        params["next_cursor"] = next_cursor
                        
                    resp = requests.get(url, headers=headers, params=params)
                    
                    if resp.status_code == 200:
                        data = resp.json()
                        # data might be list or dict with 'data' and 'next_cursor'
                        if isinstance(data, list):
                            batch = data
                            next_cursor = "" # No cursor in list response?
                        elif isinstance(data, dict):
                            batch = data.get("data", [])
                            next_cursor = data.get("next_cursor", "")
                        else:
                            break
                            
                        if not batch:
                            break
                            
                        trades.extend(batch)
                        
                        if not next_cursor or next_cursor == "MA==": # End of list
                            break
                    else:
                        logger.warning(f"Trade fetch failed: {resp.status_code}")
                        break
                        
                    loop_count += 1
            
            # Aggregate
            holdings = {}
            for t in trades:
                asset_id = t.get("asset_id")
                side = t.get("side") # BUY or SELL
                size = float(t.get("size", 0))
                
                if asset_id not in holdings:
                    holdings[asset_id] = 0.0
                
                if side == "BUY":
                    holdings[asset_id] += size
                elif side == "SELL":
                    holdings[asset_id] -= size
            
            pass# Filter > 0
            positions = []
            for aid, size in holdings.items():
                if size > 0.001:
                    positions.append({
                        "symbol": f"Asset {aid[:6]}..." # Placeholder
                    })
            
            logger.info(f"🔄 Trade geçmişinden {len(positions)} pozisyon kurtarıldı.")
            return positions
            
        except Exception as e:
            logger.error(f"Trade history reconstruction failed: {e}")
            return []
