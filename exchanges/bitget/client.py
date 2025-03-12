import aiohttp
import logging
from ..base_client import BaseAPIClient
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

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
        async with aiohttp.ClientSession() as session:
            url = "https://api.bitget.com/api/v2/spot/public/coins"
            
            try:
                async with session.get(url) as response:
                    data = await response.json()
                    if data['code'] == '00000' and data['data']:
                        for coin in data['data']:
                            if coin.get('coin') == symbol.upper():
                                return {
                                    "deposit": coin.get('depositStatus', '0') == '1',
                                    "withdrawal": coin.get('withdrawStatus', '0') == '1'
                                }
                        # Token not found
                        return {"deposit": False, "withdrawal": False}
                    else:
                        return {"deposit": False, "withdrawal": False}
            except Exception as e:
                logger.error(f"Error checking token availability on Bitget: {e}")
                return {"deposit": False, "withdrawal": False}
    
    async def get_currency_chains(self, currency: str) -> List[Tuple[str, str]]:
        """
        Get available networks and contract addresses for a currency on Bitget
        
        Args:
            currency: Currency symbol (e.g., BTC)
            
        Returns:
            List of tuples (network_name, contract_address)
        """
        async with aiohttp.ClientSession() as session:
            url = "https://api.bitget.com/api/v2/spot/public/coins"
            
            try:
                async with session.get(url) as response:
                    data = await response.json()
                    if data['code'] == '00000' and data['data']:
                        result = []
                        for coin in data['data']:
                            if coin.get('coin') == currency.upper():
                                # Extract chain information
                                chains = coin.get('chains', [])
                                for chain in chains:
                                    chain_name = chain.get('chain', '')
                                    contract_address = chain.get('contractAddress', '')
                                    # Only include chains with necessary information
                                    if chain_name:
                                        result.append((chain_name, contract_address))
                                break
                        return result
                    else:
                        return []
            except Exception as e:
                logger.error(f"Error getting currency chains on Bitget: {e}")
                return []
            