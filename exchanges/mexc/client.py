import hmac
import hashlib
import time
import requests
import aiohttp
import logging
from typing import Dict, Any, Optional, List, Tuple
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
        Get futures price for a symbol.
        
        Args:
            symbol: Trading pair symbol (e.g. 'BTCUSDT')
            
        Returns:
            float: Current price of the symbol
        """
        await self.ensure_session()
        
        try:
            # Format symbol for futures API (e.g., BTCUSDT -> BTC_USDT)
            formatted_symbol = f"{symbol.replace('USDT', '')}_USDT"
            
            # Use the contract/ticker endpoint
            ticker_url = "https://contract.mexc.com/api/v1/contract/ticker"
            async with self.session.get(ticker_url) as response:
                if response.status != 200:
                    logger.error(f"MEXC API error: {await response.text()}")
                    return None
                
                ticker_data = await response.json()
                logger.info(f"MEXC futures ticker data structure: {type(ticker_data)}")
                
                if not ticker_data.get('success', False):
                    logger.error(f"Failed to get futures ticker data: {ticker_data}")
                    return None
                
                # The data field contains the ticker information
                if "data" in ticker_data:
                    data = ticker_data["data"]
                    
                    # Check if data is a list or a single object
                    if isinstance(data, list):
                        # Find the matching symbol in the list
                        for ticker in data:
                            if ticker.get("symbol") == formatted_symbol:
                                return float(ticker.get("lastPrice", 0))
                        
                        # If we reach here, we didn't find the symbol
                        logger.error(f"Symbol {formatted_symbol} not found in futures ticker data")
                        return None
                    elif isinstance(data, dict):
                        # If it's a single object (maybe when querying a specific symbol)
                        if data.get("symbol") == formatted_symbol or "symbol" not in data:
                            return float(data.get("lastPrice", 0))
                        else:
                            logger.error(f"Symbol mismatch in futures ticker data. Expected {formatted_symbol}, got {data.get('symbol')}")
                            return None
                
                logger.error(f"Unexpected response structure from MEXC futures ticker: {ticker_data}")
                return None
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

    async def check_token_availability(self, symbol: str) -> Dict[str, bool]:
        """
        Check if a token is available for deposit and withdrawal on MEXC.
        
        Args:
            symbol: The token symbol to check
            
        Returns:
            Dict with keys 'deposit' and 'withdrawal', each with boolean values
            indicating availability status
        """
        # Ensure session exists
        await self.ensure_session()
        
        try:
            # Get authenticated coin information
            timestamp = str(int(time.time() * 1000))
            
            query_string = f"recvWindow=5000&timestamp={timestamp}"
            signature = self.generate_signature(query_string)
            
            params = {
                'recvWindow': '5000',
                'timestamp': timestamp,
                'signature': signature
            }
            
            url = f"{self.BASE_URL}/capital/config/getall"
            
            headers = self.get_headers()
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"MEXC API error: {await response.text()}")
                    return {"deposit": False, "withdrawal": False}
                
                coins_info = await response.json()
                logger.info(f"MEXC coins info retrieved successfully")
                
                # Search for the symbol in the coins_info
                for coin in coins_info:
                    if coin.get('coin') == symbol.upper():
                        # Check if depositAllEnable/withdrawAllEnable exist at coin level
                        if 'depositAllEnable' in coin and 'withdrawAllEnable' in coin:
                            return {
                                "deposit": coin.get('depositAllEnable', False),
                                "withdrawal": coin.get('withdrawAllEnable', False)
                            }
                        
                        # If not found at coin level, check networkList
                        network_list = coin.get('networkList', [])
                        if network_list:
                            # Consider a coin available if at least one network allows deposit/withdrawal
                            deposit_available = False
                            withdrawal_available = False
                            
                            for network in network_list:
                                # Check if this network is for the correct coin
                                if network.get('coin') == symbol.upper():
                                    if network.get('depositEnable', False):
                                        deposit_available = True
                                    if network.get('withdrawEnable', False):
                                        withdrawal_available = True
                            
                            return {
                                "deposit": deposit_available,
                                "withdrawal": withdrawal_available
                            }
                        
                        # No network list found
                        logger.warning(f"No network information found for {symbol}")
                        return {"deposit": False, "withdrawal": False}
                
                # Symbol not found
                logger.warning(f"Token {symbol} not found in MEXC")
                return {"deposit": False, "withdrawal": False}
        except Exception as e:
            logger.error(f"Error checking token availability for {symbol}: {e}")
            return {"deposit": False, "withdrawal": False}

    async def get_currency_chains(self, currency: str) -> List[Tuple[str, str]]:
        """
        Get available networks and contract addresses for a currency on MEXC
        
        Args:
            currency: Currency symbol (e.g., BTC)
            
        Returns:
            List of tuples (network_name, contract_address)
        """
        # Ensure session exists
        await self.ensure_session()
        
        try:
            # Get authenticated coin information
            timestamp = str(int(time.time() * 1000))
            
            query_string = f"recvWindow=5000&timestamp={timestamp}"
            signature = self.generate_signature(query_string)
            
            params = {
                'recvWindow': '5000',
                'timestamp': timestamp,
                'signature': signature
            }
            
            url = f"{self.BASE_URL}/capital/config/getall"
            
            headers = self.get_headers()
            async with self.session.get(url, params=params, headers=headers) as response:
                if response.status != 200:
                    logger.error(f"MEXC API error: {await response.text()}")
                    return []
                
                coins_info = await response.json()
                
                # Search for the currency in the coins_info
                for coin in coins_info:
                    if coin.get('coin') == currency.upper():
                        result = []
                        
                        # Extract network information
                        networks = coin.get('networkList', [])
                        for network in networks:
                            network_name = network.get('network', '')
                            contract_address = network.get('contractAddress', '')
                            
                            # Only include networks with the necessary information
                            if network_name:
                                result.append((network_name, contract_address))
                        
                        return result
                
                # Currency not found
                logger.warning(f"Currency {currency} not found in MEXC")
                return []
        except Exception as e:
            logger.error(f"Error getting currency chains for {currency}: {e}")
            return []

    # Add other async methods as needed 