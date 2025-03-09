import hmac
import hashlib
import time
import urllib.parse
from typing import Dict, Any, Optional, List

import aiohttp
import requests

from exchanges.base_client import BaseAPIClient


class BingxClient(BaseAPIClient):
    """
    Client for BingX exchange API
    Documentation: https://bingx-api-docs.github.io/
    """
    BASE_URL = "https://open-api.bingx.com/openApi/"
    
    def __init__(self, api_key: str, api_secret: str):
        super().__init__(api_key, api_secret)
        self.api_key = api_key
        self.secret_key = api_secret
        self.session = None
    
    async def __aenter__(self):
        await self.ensure_session()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            self.session = None
    
    async def ensure_session(self):
        """Ensure aiohttp session exists"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session
    
    def generate_signature(self, params: str) -> str:
        """
        Generate HMAC SHA256 signature for API request
        
        Args:
            params: query string or request body parameters
            
        Returns:
            Hex digest of HMAC SHA256 signature
        """
        signature = hmac.new(
            self.secret_key.encode('utf-8'),
            params.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature
    
    def get_headers(self) -> Dict[str, str]:
        """Get headers for API request with API key"""
        return {"X-BX-APIKEY": self.api_key}
    
    def prepare_params(self, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        Prepare parameters for API request by adding timestamp 
        and optionally recvWindow
        
        Args:
            params: original parameters
            
        Returns:
            Parameters with timestamp and signature
        """
        params = params or {}
        params.update({
            "timestamp": int(time.time() * 1000),
            "recvWindow": 5000
        })
        return params
    
    def sign_query_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sign query parameters for GET requests
        
        Args:
            params: parameters to sign
            
        Returns:
            Parameters with signature
        """
        # Convert params to query string without sorting
        query_string = urllib.parse.urlencode(params)
        
        # Generate signature
        signature = self.generate_signature(query_string)
        
        # Add signature to params
        params["signature"] = signature
        return params
    
    def sign_request_body(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sign request body parameters for POST requests
        
        Args:
            params: parameters to sign
            
        Returns:
            Parameters with signature
        """
        # Sort parameters alphabetically
        sorted_params = {k: params[k] for k in sorted(params.keys())}
        
        # Convert params to query string
        query_string = urllib.parse.urlencode(sorted_params)
        
        # Generate signature
        signature = self.generate_signature(query_string)
        
        # Add signature to params
        params["signature"] = signature
        return params
    
    def make_request(self, method: str, url: str, params: Optional[Dict] = None, is_signed: bool = False) -> requests.Response:
        """
        Make HTTP request with appropriate headers and parameters
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: request URL
            params: request parameters
            is_signed: whether request requires authentication
            
        Returns:
            HTTP response
        """
        headers = self.get_headers()
        
        if is_signed:
            params = self.prepare_params(params)
            
            if method.upper() == 'GET':
                params = self.sign_query_params(params)
                response = requests.request(method, url, headers=headers, params=params)
            else:
                params = self.sign_request_body(params)
                headers["Content-Type"] = "application/json"
                response = requests.request(method, url, headers=headers, json=params)
        else:
            response = requests.request(method, url, headers=headers, params=params)
            
        return response
    
    async def make_request_async(self, method: str, url: str, params: Optional[Dict] = None, is_signed: bool = False) -> Dict[str, Any]:
        """
        Make asynchronous HTTP request
        
        Args:
            method: HTTP method (GET, POST, etc.)
            url: request URL
            params: request parameters
            is_signed: whether request requires authentication
            
        Returns:
            JSON response
        """
        await self.ensure_session()
        headers = self.get_headers()
        
        if is_signed:
            params = self.prepare_params(params)
            
            if method.upper() == 'GET':
                params = self.sign_query_params(params)
                async with self.session.request(method, url, headers=headers, params=params) as response:
                    return await response.json()
            else:
                params = self.sign_request_body(params)
                headers["Content-Type"] = "application/json"
                async with self.session.request(method, url, headers=headers, json=params) as response:
                    return await response.json()
        else:
            async with self.session.request(method, url, headers=headers, params=params) as response:
                return await response.json()
    
    async def get_exchange_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get exchange information including trading rules and symbol information
        
        Args:
            symbol: Optional trading pair symbol (e.g. 'BTC-USDT')
            
        Returns:
            Dict containing exchange information
        """
        url = f"{self.BASE_URL}/market/exchangeInfo"
        params = {"symbol": symbol} if symbol else None
        return await self.make_request_async('GET', url, params=params)
    
    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get 24hr ticker price change statistics
        
        Args:
            symbol: Trading pair symbol (e.g. 'BTC-USDT')
            
        Returns:
            Dict containing ticker information
        """
        url = f"{self.BASE_URL}/market/ticker"
        params = {"symbol": symbol}
        return await self.make_request_async('GET', url, params=params)
    
    async def get_spot_price(self, symbol: str) -> float:
        """
        Get current spot price for a symbol
        
        Args:
            symbol: Trading pair symbol (e.g. 'BTC-USDT')
            
        Returns:
            Float price value
        """
        url = f"{self.BASE_URL}spot/v1/ticker/price"
        
        # Ensure symbol is in format {symbol}_USDT
        if '-USDT' in symbol:
            # Convert from BTC-USDT format to BTC_USDT format
            formatted_symbol = symbol.replace('-', '_')
        elif '_USDT' not in symbol and not symbol.endswith('USDT'):
            formatted_symbol = f"{symbol}_USDT"
        else:
            formatted_symbol = symbol
            
        params = {"symbol": formatted_symbol}
        response = await self.make_request_async('GET', url, params=params)
        
        if 'price' in response:
            return float(response['price'])
        elif 'data' in response and isinstance(response['data'], list) and len(response['data']) > 0:
            if 'trades' in response['data'][0] and len(response['data'][0]['trades']) > 0:
                price = response['data'][0]['trades'][0]['price']
                return float(price)
        raise Exception(f"Failed to get spot price for {symbol}: {response}")
    
    async def get_futures_price(self, symbol: str) -> float:
        """
        Get current futures price for a symbol
        
        Args:
            symbol: Trading pair symbol (e.g. 'BTC-USDT')
            
        Returns:
            Float price value
        """
        url = f"{self.BASE_URL}swap/v2/quote/premiumIndex"
        
        # Ensure symbol is in format with hyphen (e.g., BTC-USDT)
        if '-' not in symbol:
            # If symbol is like "BTCUSDT" or "BTC_USDT", try to format it
            if 'USDT' in symbol:
                # Extract the base currency
                base = symbol.replace('USDT', '').replace('_', '')
                formatted_symbol = f"{base}-USDT"
            else:
                # Assume it's just the base currency
                formatted_symbol = f"{symbol}-USDT"
        else:
            formatted_symbol = symbol
            
        params = {"symbol": formatted_symbol}
        response = await self.make_request_async('GET', url, params=params)
        
        if 'markPrice' in response:
            return float(response['markPrice'])
        elif 'data' in response and 'markPrice' in response['data']:
            return float(response['data']['markPrice'])
        raise Exception(f"Failed to get futures price for {symbol}: {response}")
    
    async def get_all_coins(self) -> Dict[str, Any]:
        """
        Get information of all coins available
        
        Returns:
            Dict containing coin information
        """
        url = f"{self.BASE_URL}/wallet/getAllCoins"
        return await self.make_request_async('GET', url, is_signed=True)
    
    async def get_account_information(self) -> Dict[str, Any]:
        """
        Get account information
        
        Returns:
            Dict containing account information
        """
        url = f"{self.BASE_URL}/account/detail"
        return await self.make_request_async('GET', url, is_signed=True)
    
    async def get_balances(self) -> List[Dict[str, Any]]:
        """
        Get account balances
        
        Returns:
            List of balance information
        """
        account_info = await self.get_account_information()
        if 'balances' in account_info:
            return account_info['balances']
        raise Exception(f"Failed to get balances: {account_info}") 