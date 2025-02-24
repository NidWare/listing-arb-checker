from typing import Dict, Any, Optional, List
from ..base_coin_service import BaseCoinService

class MexcCoinService(BaseCoinService):
    def search_by_name(self, data: List[Dict], name: str) -> Optional[Dict]:
        for coin in data:
            if coin.get('coin') == name or coin.get('Name') == name:
                return coin
        return None

    def search_by_contract(self, data: List[Dict], contract: str) -> Optional[Dict]:
        for coin in data:
            for network in coin.get('networkList', []):
                if network.get('contract') == contract:
                    return coin
        return None

    def format_coin_info(self, coin: Optional[Dict]) -> str:
        if not coin:
            return "Coin not found in the response"

        output = [f"\nCoin Details:", f"Coin: {coin.get('Name', coin.get('coin'))}"]
            
        return "\n".join(output) 