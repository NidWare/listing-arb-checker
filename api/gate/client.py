import aiohttp
from typing import Dict, Any, List, Optional

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

    async def get_futures_contracts(self) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self.get_headers()) as session:
            url = f"{self.base_url}/futures/usdt/contracts"
            async with session.get(url) as response:
                return await response.json()

    async def get_futures_price(self, symbol: str) -> Optional[float]:
        """
        Get futures market price for a given symbol
        
        Args:
            symbol: Symbol to search for (without _USDT suffix)
        
        Returns:
            Float market price if found, None otherwise
        """
        contracts = await self.get_futures_contracts()
        contract_name = f"{symbol}_USDT"
        
        for contract in contracts:
            if contract.get('name') == contract_name:
                # Return mark_price as it's typically more stable than last_price
                return float(contract.get('mark_price', 0))
                
        return None

    async def get_spot_price(self, symbol: str) -> Optional[float]:
        """
        Get spot market price for a given symbol
        
        Args:
            symbol: Symbol to search for (without _USDT suffix)
        
        Returns:
            Float market price if found, None otherwise
        """
        async with aiohttp.ClientSession(headers=self.get_headers()) as session:
            currency_pair = f"{symbol}_USDT"
            url = f"{self.base_url}/spot/tickers?currency_pair={currency_pair}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    if data and isinstance(data, list) and len(data) > 0:
                        # Return last price from the first matching ticker
                        return float(data[0].get('last', 0))
                return None

    def format_market_price(self, price: Optional[float], symbol: str) -> str:
        """Format market price into readable string"""
        if price is None:
            return f"No market price found for {symbol}"
        
        return f"Market price for {symbol}: {price} USDT" 
    