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

    async def get_coin_info(self, symbol: str) -> Dict[str, Any]:
        async with aiohttp.ClientSession(headers=self.get_headers()) as session:
            url = f"{self.BASE_URL}/coins"
            params = {'symbol': symbol}
            async with session.get(url, params=params) as response:
                return await response.json() 