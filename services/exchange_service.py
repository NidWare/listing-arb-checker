from typing import Optional, List, Tuple
from exchanges.mexc.client import MexcClient
from exchanges.gate.client import GateClient
from exchanges.bitget.client import BitgetClient
from exchanges.bybit.client import BybitClient
from exchanges.mexc.coin_service import MexcCoinService
from exchanges.gate.coin_service import GateCoinService
from exchanges.bitget.coin_service import BitgetCoinService
from exchanges.bybit.coin_service import BybitCoinService
from config.config_manager import ConfigManager
import aiohttp
import logging
from exchanges.base_client import BaseAPIClient
logger = logging.getLogger(__name__)

class ExchangeService:
    def __init__(self):
        # Initialize all clients and services
        mexc_credentials = ConfigManager.get_mexc_credentials()
        bitget_credentials = ConfigManager.get_bitget_credentials()
        bybit_credentials = ConfigManager.get_bybit_credentials()
        
        self.clients = {
            'mexc': (MexcClient(**mexc_credentials), MexcCoinService()),
            'gate': (GateClient(), GateCoinService()),
            'bitget': (BitgetClient(**bitget_credentials), BitgetCoinService()),
            'bybit': (BybitClient(**bybit_credentials), BybitCoinService())
        }
        self._session = None

    @property
    async def session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session


    def _get_exchange_client(self, exchange: str) -> BaseAPIClient:
        if exchange.lower() not in self.clients:
            raise ValueError(f"Unsupported exchange: {exchange}")
            
        return self.clients[exchange.lower()][0]  # Return the client from the tuple (client, service)
    
    async def get_currency_chains(self, exchange: str, currency: str) -> List[Tuple[str, str]]:
        exchange_client = self._get_exchange_client(exchange)
        return await exchange_client.get_currency_chains(currency)

    async def get_average_price(self, exchange: str, symbol: str, market_type: str = "spot") -> Optional[float]:
        try:
            exchange_client = self._get_exchange_client(exchange)
            
            if market_type == "futures":
                ticker = await exchange_client.get_futures_price(symbol)
            else:
                ticker = await exchange_client.get_spot_price(symbol)
            return ticker
            
        except Exception as e:
            logger.error(f"Error getting {market_type} price from {exchange}: {str(e)}")
            return None

    async def close(self):
        if self._session is not None:
            await self._session.close()
            self._session = None 
