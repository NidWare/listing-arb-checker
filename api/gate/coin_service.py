from typing import Dict, Any, Optional, List
from ..base_coin_service import BaseCoinService

class GateCoinService(BaseCoinService):
    def search_by_name(self, data: List[Dict], name: str) -> List[Dict]:
        # Gate.io API directly returns the coin info for the requested currency
        return data

    def search_by_contract(self, data: List[Dict], contract: str) -> Optional[Dict]:
        # Not implemented for Gate.io
        raise NotImplementedError("Gate.io API doesn't support contract search")

    def format_coin_info(self, coin_data: List[Dict]) -> str:
        if not coin_data:
            return "Coin not found in the response"

        output = ["\nCoin Network Details:"]
        
        for network in coin_data:
            output.append("\nNetwork Information:")
            output.extend([
                f"Chain: {network.get('chain')}",
                f"Name (EN): {network.get('name_en')}",
                f"Name (CN): {network.get('name_cn')}",
                f"Contract Address: {network.get('contract_address')}",
                f"Deposit Disabled: {network.get('is_deposit_disabled')}",
                f"Withdraw Disabled: {network.get('is_withdraw_disabled')}"
            ])
            
        return "\n".join(output) 