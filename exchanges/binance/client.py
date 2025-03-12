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

class BinanceClient(BaseAPIClient):
    # Use the main endpoint as default, but we can switch if needed
    BASE_URL = "https://api.binance.com"
    ALTERNATIVE_URLS = [
        "https://api-gcp.binance.com",
        "https://api1.binance.com",
        "https://api2.binance.com", 
        "https://api3.binance.com",
        "https://api4.binance.com"
    ]
    
    def __init__(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = self.BASE_URL
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
            
    def generate_signature(self, query_string: str) -> str:
        """Generate HMAC SHA256 signature for Binance API"""
        return hmac.new(
            bytes(self.api_secret, 'utf-8'),
            bytes(query_string, 'utf-8'),
            hashlib.sha256
        ).hexdigest()
        
    def get_headers(self) -> Dict[str, str]:
        """Get the required headers for Binance API calls"""
        return {
            'X-MBX-APIKEY': self.api_key
        }
        
    async def get_spot_ticker(self, symbol: str) -> Dict[str, Any]:
        """Get 24hr ticker price change statistics for a symbol"""
        await self.ensure_session()
        
        # Format the symbol as {coin}USDT if it doesn't already have USDT
        formatted_symbol = symbol
        if not symbol.endswith('USDT'):
            formatted_symbol = f"{symbol}USDT"
            logger.info(f"Formatted symbol for Binance: {symbol} -> {formatted_symbol}")
        
        url = f"{self.base_url}/api/v3/ticker/24hr"
        params = {'symbol': formatted_symbol}
        
        try:
            logger.info(f"Requesting Binance spot ticker for {formatted_symbol}")
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Successfully retrieved Binance spot ticker for {formatted_symbol}")
                    return data
                else:
                    error_text = await response.text()
                    logger.error(f"Error getting spot ticker for {formatted_symbol}: {error_text}")
                    return {}
        except Exception as e:
            logger.error(f"Exception getting spot ticker for {formatted_symbol}: {str(e)}")
            return {}
    
    async def get_spot_price(self, symbol: str) -> float:
        """Get the current spot price for a symbol"""
        ticker_data = await self.get_spot_ticker(symbol)
        
        if not ticker_data or 'lastPrice' not in ticker_data:
            logger.error(f"Failed to get spot price for {symbol}")
            return 0.0
            
        try:
            # Parse lastPrice from the response
            return float(ticker_data['lastPrice'])
        except (KeyError, ValueError) as e:
            logger.error(f"Error parsing spot price for {symbol}: {str(e)}")
            return 0.0
    
    async def get_futures_price(self, symbol: str) -> float:
        """Get the current futures price for a symbol"""
        try:
            # For futures, we need to use the futures API endpoints
            futures_url = "https://fapi.binance.com/fapi/v1/ticker/price"
            
            # Format the symbol as {coin}USDT if it doesn't already have USDT
            formatted_symbol = symbol
            if not symbol.endswith('USDT'):
                formatted_symbol = f"{symbol}USDT"
                logger.info(f"Formatted symbol for Binance futures: {symbol} -> {formatted_symbol}")
            
            await self.ensure_session()
            logger.info(f"Requesting Binance futures price for {formatted_symbol}")
            async with self.session.get(futures_url, params={'symbol': formatted_symbol}) as response:
                if response.status == 200:
                    data = await response.json()
                    logger.info(f"Successfully retrieved Binance futures price for {formatted_symbol}: {data['price']}")
                    return float(data['price'])
                else:
                    error_text = await response.text()
                    logger.error(f"Error getting futures price for {formatted_symbol}: {error_text}")
                    return 0.0
        except Exception as e:
            logger.error(f"Exception getting futures price for {formatted_symbol}: {str(e)}")
            return 0.0
    
    async def check_token_availability(self, symbol: str) -> Dict[str, bool]:
        """Check if a token is available for deposit and withdrawal"""
        try:
            # Generate timestamp and signature for authenticated endpoint
            timestamp = str(int(time.time() * 1000))
            query_string = f"timestamp={timestamp}"
            signature = self.generate_signature(query_string)
            
            # Capital/config/getall endpoint provides coin information
            url = f"{self.base_url}/sapi/v1/capital/config/getall"
            params = {
                'timestamp': timestamp,
                'signature': signature
            }
            
            await self.ensure_session()
            headers = self.get_headers()
            
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Find the specified coin
                    for coin in data:
                        if coin.get('coin') == symbol:
                            return {
                                'deposit': coin.get('depositAllEnable', False),
                                'withdrawal': coin.get('withdrawAllEnable', False)
                            }
                    
                    # Coin not found
                    logger.warning(f"Token {symbol} not found in Binance")
                    return {'deposit': False, 'withdrawal': False}
                else:
                    error_text = await response.text()
                    logger.error(f"Error checking token availability for {symbol}: {error_text}")
                    return {'deposit': False, 'withdrawal': False}
        except Exception as e:
            logger.error(f"Exception checking token availability for {symbol}: {str(e)}")
            return {'deposit': False, 'withdrawal': False}
            
    def get_spot_trading_url(self, symbol: str) -> str:
        """
        Generate a URL for trading the specified symbol on Binance spot market
        
        Args:
            symbol: The trading symbol (e.g., BTC)
            
        Returns:
            URL to the Binance spot trading page
        """
        # Format the symbol appropriately for the URL
        # Spot format is NAME_USDT
        base_symbol = symbol.replace('USDT', '').replace('_USDT', '')
        return f"https://www.binance.com/en/trade/{base_symbol}_USDT?type=spot"
    
    def get_futures_trading_url(self, symbol: str) -> str:
        """
        Generate a URL for trading the specified symbol on Binance futures market
        
        Args:
            symbol: The trading symbol (e.g., BTC)
            
        Returns:
            URL to the Binance futures trading page
        """
        # Format the symbol appropriately for the URL
        # Futures format is NAMEUSDT
        base_symbol = symbol.replace('USDT', '').replace('_USDT', '')
        return f"https://www.binance.com/en/futures/{base_symbol}USDT"
    
    async def get_currency_chains(self, currency: str) -> List[Tuple[str, str]]:
        """
        Get available networks and contract addresses for a currency
        
        Args:
            currency: Currency symbol (e.g., BTC)
            
        Returns:
            List of tuples (network_name, contract_address)
        """
        try:
            # Generate timestamp and signature for authenticated endpoint
            timestamp = str(int(time.time() * 1000))
            query_string = f"timestamp={timestamp}"
            signature = self.generate_signature(query_string)
            
            # Capital/config/getall endpoint provides coin information
            url = f"{self.base_url}/sapi/v1/capital/config/getall"
            params = {
                'timestamp': timestamp,
                'signature': signature
            }
            
            await self.ensure_session()
            headers = self.get_headers()
            
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    # Find the specified coin
                    result = []
                    for coin in data:
                        if coin.get('coin') == currency:
                            # Extract network information
                            for network in coin.get('networkList', []):
                                network_name = network.get('network', '')
                                contract_address = network.get('contractAddress', '')
                                # Only include networks with contract addresses
                                if contract_address:
                                    result.append((network_name, contract_address))
                            break
                    
                    return result
                else:
                    error_text = await response.text()
                    logger.error(f"Error getting currency chains for {currency}: {error_text}")
                    return []
        except Exception as e:
            logger.error(f"Exception getting currency chains for {currency}: {str(e)}")
            return [] 