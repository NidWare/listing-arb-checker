import aiohttp
from typing import Dict, Any

class GateClient:
    def __init__(self):
        self.base_url = "https://api.gateio.ws/api/v4"

    def get_headers(self) -> Dict[str, str]:
        return {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

    async def get_coin_info(self, symbol: str) -> Dict[str, Any]:
        async with aiohttp.ClientSession(headers=self.get_headers()) as session:
            url = f"{self.base_url}/spot/currencies/{symbol}"
            async with session.get(url) as response:
                return await response.json() 