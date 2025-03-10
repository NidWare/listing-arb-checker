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

class BybitClient(BaseAPIClient):
    BASE_URL = "https://api.bybit.com/v5"

    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.BASE_URL
        self.session = None
        self.recv_window = "5000"  # Default recv_window as per Bybit docs

    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def ensure_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()

    def get_timestamp(self) -> str:
        """Get current timestamp in milliseconds"""
        return str(int(time.time() * 1000))

    def generate_signature(self, timestamp: str, params: str) -> str:
        """
        Generate HMAC SHA256 signature for Bybit API
        Format: timestamp + api_key + recv_window + params
        """
        sign_str = f"{timestamp}{self.api_key}{self.recv_window}{params}"
        return hmac.new(
            bytes(self.api_secret, 'utf-8'),
            bytes(sign_str, 'utf-8'),
            hashlib.sha256
        ).hexdigest()

    def get_headers(self, timestamp: str, signature: str) -> Dict[str, str]:
        """Get headers required for authenticated requests"""
        return {
            'X-BAPI-API-KEY': self.api_key,
            'X-BAPI-TIMESTAMP': timestamp,
            'X-BAPI-SIGN': signature,
            'X-BAPI-RECV-WINDOW': self.recv_window,
            'Content-Type': 'application/json'
        }

    async def get_server_time(self) -> int:
        """Get Bybit server time"""
        url = f"{self.base_url}/market/time"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return int(data['time'])
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
        timestamp = self.get_timestamp()
        params = f"category=spot&symbol={symbol}"
        
        signature = self.generate_signature(timestamp, params)
        headers = self.get_headers(timestamp, signature)
        
        url = f"{self.base_url}/market/tickers"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}?{params}", headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Bybit API error: {await response.text()}")
                        return None
                    data = await response.json()
                    if data.get('retCode') == 0 and data.get('result', {}).get('list'):
                        # Get the first (and should be only) item in the list
                        ticker = data['result']['list'][0]
                        return float(ticker['lastPrice']) if ticker.get('lastPrice') else None
                    logger.error(f"Unexpected response structure: {data}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching spot price for {symbol}: {str(e)}")
            return None

    async def get_all_coins(self) -> Dict[str, Any]:
        """Get all coins information"""
        timestamp = self.get_timestamp()
        params = f"recvWindow={self.recv_window}"
        signature = self.generate_signature(timestamp, params)
        
        url = f"{self.base_url}/asset/coin/query-info"
        headers = self.get_headers(timestamp, signature)
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{url}?{params}", headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Bybit API error: {await response.text()}")
                    return []
                return await response.json()

    async def get_futures_price(self, symbol: str) -> float:
        """
        Get spot market price for a symbol paired with USDT.
        
        Args:
            symbol: Base currency symbol (e.g. 'BTC' for BTCUSDT pair)
            
        Returns:
            float: Current price of the symbol
        """
        symbol = f"{symbol}USDT"
        timestamp = self.get_timestamp()
        params = f"category=linear&symbol={symbol}"
        
        signature = self.generate_signature(timestamp, params)
        headers = self.get_headers(timestamp, signature)
        
        url = f"{self.base_url}/market/tickers"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{url}?{params}", headers=headers) as response:
                    if response.status != 200:
                        logger.error(f"Bybit API error: {await response.text()}")
                        return None
                    data = await response.json()
                    if data.get('retCode') == 0 and data.get('result', {}).get('list'):
                        # Get the first (and should be only) item in the list
                        ticker = data['result']['list'][0]
                        return float(ticker['lastPrice']) if ticker.get('lastPrice') else None
                    logger.error(f"Unexpected response structure: {data}")
                    return None
        except Exception as e:
            logger.error(f"Error fetching spot price for {symbol}: {str(e)}")
            return None

    async def check_token_availability(self, symbol: str) -> Dict[str, bool]:
        """
        Check if a token is available for deposit and withdrawal on Bybit.
        
        Args:
            symbol: The token symbol to check
            
        Returns:
            Dict with keys 'deposit' and 'withdrawal', each with boolean values
            indicating availability status
        """
        # Ensure session exists
        await self.ensure_session()
        
        # Placeholder implementation - to be completed
        url = f"{self.base_url}/asset/coin/query-info"
        timestamp = self.get_timestamp()
        params = f"timestamp={timestamp}&recvWindow={self.recv_window}"
        signature = self.generate_signature(timestamp, params)
        headers = self.get_headers(timestamp, signature)
        
        try:
            # This will need to be implemented to query coin info and check availability
            response = {"deposit": False, "withdrawal": False}
            return response
        except Exception as e:
            logger.error(f"Error checking token availability for {symbol}: {e}")
            return {"deposit": False, "withdrawal": False}
        