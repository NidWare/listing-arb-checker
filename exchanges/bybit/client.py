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
        
        timestamp = self.get_timestamp()
        params = "coin=" + symbol
        signature = self.generate_signature(timestamp, params)
        headers = self.get_headers(timestamp, signature)
        
        url = f"{self.base_url}/asset/coin/query-info"
        
        try:
            async with self.session.get(f"{url}?{params}", headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Bybit API error: {await response.text()}")
                    return {"deposit": False, "withdrawal": False}
                
                data = await response.json()
                
                if data.get('retCode') != 0 or not data.get('result', {}).get('rows'):
                    logger.error(f"Failed to get coin info from Bybit: {data}")
                    return {"deposit": False, "withdrawal": False}
                
                # Search for the token in the response
                for coin in data['result']['rows']:
                    if coin.get('coin') == symbol.upper():
                        # Get deposit and withdrawal status
                        chains = coin.get('chains', [])
                        
                        deposit_enabled = False
                        withdrawal_enabled = False
                        
                        # If any chain has deposits/withdrawals enabled, mark as available
                        for chain in chains:
                            if chain.get('chainDeposit') == 'on':
                                deposit_enabled = True
                            if chain.get('chainWithdraw') == 'on':
                                withdrawal_enabled = True
                        
                        return {
                            "deposit": deposit_enabled,
                            "withdrawal": withdrawal_enabled
                        }
                
                # Token not found
                logger.warning(f"Token {symbol} not found in Bybit")
                return {"deposit": False, "withdrawal": False}
        
        except Exception as e:
            logger.error(f"Error checking token availability for {symbol}: {e}")
            return {"deposit": False, "withdrawal": False}
            
    async def get_currency_chains(self, currency: str) -> List[Tuple[str, str]]:
        """
        Get available networks and contract addresses for a currency on Bybit
        
        Args:
            currency: Currency symbol (e.g., BTC)
            
        Returns:
            List of tuples (network_name, contract_address)
        """
        # Ensure session exists
        await self.ensure_session()
        
        timestamp = self.get_timestamp()
        params = "coin=" + currency
        signature = self.generate_signature(timestamp, params)
        headers = self.get_headers(timestamp, signature)
        
        url = f"{self.base_url}/asset/coin/query-info"
        
        try:
            async with self.session.get(f"{url}?{params}", headers=headers) as response:
                if response.status != 200:
                    logger.error(f"Bybit API error: {await response.text()}")
                    return []
                
                data = await response.json()
                
                if data.get('retCode') != 0 or not data.get('result', {}).get('rows'):
                    logger.error(f"Failed to get coin info from Bybit: {data}")
                    return []
                
                # Search for the currency in the response
                for coin in data['result']['rows']:
                    if coin.get('coin') == currency.upper():
                        result = []
                        
                        # Extract network information
                        chains = coin.get('chains', [])
                        for chain in chains:
                            network_name = chain.get('chain', '')
                            # Bybit might not expose contract addresses directly, so we'll use 
                            # empty string as a placeholder for contract address
                            contract_address = chain.get('contractAddress', '') 
                            
                            # Only include networks with names
                            if network_name:
                                result.append((network_name, contract_address))
                        
                        return result
                
                # Currency not found
                logger.warning(f"Currency {currency} not found in Bybit")
                return []
        
        except Exception as e:
            logger.error(f"Error getting currency chains for {currency}: {e}")
            return []
        