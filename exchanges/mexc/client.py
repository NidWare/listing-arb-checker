import hmac
import hashlib
import time
import requests
import aiohttp
import logging
from typing import Dict, Any, Optional
from ..base_client import BaseAPIClient

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class MexcClient(BaseAPIClient):
    BASE_URL = "https://api.mexc.com/api/v3"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = "https://api.mexc.com/api/v3"
        self.session = None

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    def generate_signature(self, params: str) -> str:
        return hmac.new(
            bytes(self.api_secret, 'utf-8'),
            bytes(params, 'utf-8'),
            hashlib.sha256
        ).hexdigest()

    def get_headers(self) -> Dict[str, str]:
        return {'x-mexc-apikey': self.api_key}

    async def get_all_coins(self) -> Dict[str, Any]:
        """Get all coins information including network details"""
        timestamp = str(int(time.time() * 1000))
        
        query_string = f"recvWindow=5000&timestamp={timestamp}"
        signature = self.generate_signature(query_string)
        
        params = {
            'recvWindow': '5000',
            'timestamp': timestamp,
            'signature': signature
        }
        
        url = f"{self.BASE_URL}/capital/config/getall"
        
        async with aiohttp.ClientSession() as session:
            headers = self.get_headers()
            async with session.get(url, params=params, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"MEXC API error: {await response.text()}")
                    return []
                return await response.json()

    async def get_all_coins_async(self) -> Dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/exchangeInfo") as response:
                return await response.json()

    def parse_futures_price(self, symbol: str) -> Dict[str, Any]:
        """
        Get the fair price for a futures contract.
        
        Args:
            symbol: Trading pair symbol without '_USDT' (e.g. 'BTC' for BTC_USDT)
            
        Returns:
            Dict containing symbol, fair price, and timestamp
        """
        url = f"https://contract.mexc.com/api/v1/contract/fair_price/{symbol}_USDT"
        response = self.make_request('GET', url)
        data = response.json()
        
        if not data.get('success'):
            raise Exception(f"Failed to get futures price: {data}")
            
        return {
            'symbol': data['data']['symbol'],
            'fair_price': data['data']['fairPrice'],
            'timestamp': data['data']['timestamp']
        }

    def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get exchange information including trading rules and symbol information
        
        Args:
            symbol: Optional trading pair symbol (e.g. 'BTCUSDT')
            
        Returns:
            Dict containing exchange information
        """
        url = f"{self.BASE_URL}/exchangeInfo"
        params = {"symbol": symbol} if symbol else None
        response = self.make_request('GET', url, params=params)
        return response.json()

    async def get_spot_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get spot market ticker"""
        url = f"{self.base_url}/ticker/24hr"  # Removed duplicate api/v3
        params = {"symbol": symbol}
        try:
            async with self.session.get(url, params=params) as response:
                if response.status != 200:
                    logger.error(f"MEXC API error: {await response.text()}")
                    return None
                data = await response.json()
                return {"last": data["lastPrice"]} if "lastPrice" in data else None
        except Exception as e:
            logger.error(f"Error fetching spot ticker: {str(e)}")
            return None

    async def get_futures_price(self, symbol: str) -> float:
        """
        Get futures index price for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g. 'BTCUSDT')
            
        Returns:
            float: Current index price of the symbol
        """
        await self.ensure_session()
        
        try:
            # Get index price
            index_url = f"https://contract.mexc.com/api/v1/contract/index_price/{symbol.replace('USDT', '')}_USDT"
            async with self.session.get(index_url) as response:
                if response.status != 200:
                    logger.error(f"MEXC API error: {await response.text()}")
                    return None
                index_data = await response.json()
                
                if not index_data.get('success'):
                    logger.error(f"Failed to get index price: {index_data}")
                    return None
                    
                return float(index_data["data"]["indexPrice"]) if "data" in index_data else None
        except Exception as e:
            logger.error(f"Error fetching futures price: {str(e)}")
            return None

    async def get_spot_price(self, symbol: str) -> float:
        """
        Get spot market price for a symbol paired with USDT.
        
        Args:
            symbol: Base currency symbol (e.g. 'BTC' for BTCUSDT pair)
            
        Returns:
            float: Current price of the symbol
        """
        symbol = f"{symbol}USDT"    
        url = f"{self.BASE_URL}/ticker/24hr"
        params = {"symbol": symbol}
        
        try:
            await self.ensure_session()
            async with self.session.get(url, params=params, headers=self.get_headers()) as response:
                if response.status != 200:
                    logger.error(f"MEXC API error: {await response.text()}")
                    return None
                data = await response.json()
                logger.info(f"MEXC spot price for {symbol}: {data}")
                return float(data["lastPrice"])
        except Exception as e:
            logger.error(f"Error fetching spot price for {symbol}: {str(e)}")
            return None
    # Add other async methods as needed 