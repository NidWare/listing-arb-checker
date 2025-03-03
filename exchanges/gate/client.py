import aiohttp
from typing import Dict, Any, List, Optional, Tuple

class GateClient:
    def __init__(self):
        self.base_url = "https://api.gateio.ws/api/v4"

    async def get_futures_contracts(self) -> List[Dict[str, Any]]:
        async with aiohttp.ClientSession(headers=self._get_headers()) as session:
            url = f"{self.base_url}/futures/usdt/contracts"
            async with session.get(url) as response:
                return await response.json()

    async def get_futures_price(self, symbol: str) -> Optional[float]:
        contracts = await self.get_futures_contracts()
        contract_name = f"{symbol}_USDT"
        
        for contract in contracts:
            if contract.get('name') == contract_name:
                return float(contract.get('mark_price', 0))
                
        return None

    async def get_spot_price(self, symbol: str) -> Optional[float]:
        async with aiohttp.ClientSession(headers=self._get_headers()) as session:
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
        if price is None:
            return f"No market price found for {symbol}"
        
        return f"Market price for {symbol}: {price} USDT" 

    def _get_headers(self) -> Dict[str, str]:
        return {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
        }

    async def get_currency_chains(self, currency: str) -> List[Tuple[str, str]]:
        """
        Fetch currency information and return list of chain-address pairs.
        Args:
            currency: Currency symbol (e.g., 'GT', 'BTC', 'ETH', etc.)
        Returns:
            List of tuples (chain_name, address) where address is not empty.
        """
        async with aiohttp.ClientSession(headers=self._get_headers()) as session:
            url = f"{self.base_url}/spot/currencies/{currency}"
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    chains = data.get('chains', [])
                    result = []
                    for chain in chains:
                        chain_name = chain.get('name')
                        addr = chain.get('addr')
                        if chain_name and addr:  # Only include pairs where address exists
                            result.append((chain_name, addr))
                    return result
                return []
