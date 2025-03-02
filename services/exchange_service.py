from typing import Optional, Dict, Any
from api.mexc.client import MexcClient
from api.gate.client import GateClient
from api.bitget.client import BitgetClient
from api.bybit.client import BybitClient
from api.mexc.coin_service import MexcCoinService
from api.gate.coin_service import GateCoinService
from api.bitget.coin_service import BitgetCoinService
from api.bybit.coin_service import BybitCoinService
from config.config_manager import ConfigManager
import aiohttp
import logging

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

    async def search_all_exchanges(self, search_type: str, query: str) -> str:
        results = []
        
        for exchange_name, (client, service) in self.clients.items():
            try:
                if exchange_name == 'mexc':
                    data = await client.get_all_coins()
                    if search_type == 'name':
                        coin = service.search_by_name(data, query)
                    else:  # contract
                        coin = service.search_by_contract(data, query)
                else:
                    data = await client.get_coin_info(query)
                    coin = data

                if coin:
                    formatted_info = service.format_coin_info(coin)
                    results.append(f"💱 {exchange_name.upper()}\n{formatted_info}")
            
            except Exception as e:
                results.append(f"❌ {exchange_name.upper()}: Error - {str(e)}")
                continue

        return "\n\n".join(results) if results else "No results found on any exchange."


    def _get_exchange_client(self, exchange: str):
        """
        Get the client instance for the specified exchange
        
        Args:
            exchange: Exchange name (mexc, gate, or bitget)
            
        Returns:
            The client instance for the specified exchange
        """
        if exchange.lower() not in self.clients:
            raise ValueError(f"Unsupported exchange: {exchange}")
            
        return self.clients[exchange.lower()][0]  # Return the client from the tuple (client, service)

    async def get_average_price(self, exchange: str, symbol: str, market_type: str = "spot") -> Optional[float]:
        """
        Get average price for a symbol from specific exchange and market type
        
        Args:
            exchange: Exchange name
            symbol: Trading symbol
            market_type: Either "spot" or "futures"
        """
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