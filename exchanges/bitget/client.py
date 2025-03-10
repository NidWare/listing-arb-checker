import aiohttp
from ..base_client import BaseAPIClient
from typing import Dict, Any

class BitgetClient(BaseAPIClient):
    BASE_URL = "https://api.bitget.com/api/v2/spot/public"

    def __init__(self, api_key: str, api_secret: str):
        super().__init__(api_key, api_secret)

    def generate_signature(self, params: str) -> str:
        # Bitget public API doesn't require signatures
        pass

    def get_headers(self) -> Dict[str, str]:
        return {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': self.secret_key,
            'Content-Type': 'application/json'
        }

    async def get_spot_price(self, symbol: str) -> float:
        async with aiohttp.ClientSession() as session:
            url = "https://api.bitget.com/api/v2/spot/market/tickers"
            params = {'symbol': f"{symbol}USDT"}
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                if data['code'] == '00000' and data['data']:
                    return float(data['data'][0]['lastPr'])
                raise Exception(f"Failed to get spot price: {data['msg']}")

    async def get_futures_price(self, symbol: str) -> float:
        """
        Get the current futures price for a given symbol.
        
        Args:
            symbol: The trading symbol without USDT suffix (e.g., 'BTC' for BTCUSDT)
            
        Returns:
            float: The current futures price
        """
        async with aiohttp.ClientSession() as session:
            url = "https://api.bitget.com/api/v2/mix/market/ticker"
            params = {
                'productType': 'USDT-FUTURES',
                'symbol': f"{symbol}USDT"
            }
            
            async with session.get(url, params=params) as response:
                data = await response.json()
                if data['code'] == '00000' and data['data']:
                    return float(data['data'][0]['lastPr'])
                raise Exception(f"Failed to get futures price: {data['msg']}")
                
    async def check_token_availability(self, symbol: str) -> Dict[str, bool]:
        """
        Check if a token is available for deposit and withdrawal on Bitget.
        
        Args:
            symbol: The token symbol to check
            
        Returns:
            Dict with keys 'deposit' and 'withdrawal', each with boolean values
            indicating availability status
        """
        # Placeholder implementation - to be completed
        async with aiohttp.ClientSession() as session:
            url = "https://api.bitget.com/api/v2/spot/public/coins"
            
            try:
                async with session.get(url) as response:
                    data = await response.json()
                    if data['code'] == '00000' and data['data']:
                        # In a real implementation, search through data for the specific coin
                        # and check its deposit and withdrawal status
                        # For now, return default values
                        return {
                            "deposit": False,  # Replace with actual logic
                            "withdrawal": False  # Replace with actual logic
                        }
                    else:
                        return {"deposit": False, "withdrawal": False}
            except Exception as e:
                return {"deposit": False, "withdrawal": False} 
            