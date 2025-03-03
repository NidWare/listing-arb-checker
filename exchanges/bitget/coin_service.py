from ..base_coin_service import BaseCoinService
from typing import Dict, Optional, List

class BitgetCoinService(BaseCoinService):
    def search_by_name(self, data: Dict, name: str) -> Optional[Dict]:
        if not data or "code" != "00000" or "data" not in data or not data["data"]:
            return None
        
        coins = data["data"]
        for coin in coins:
            if coin["coin"].lower() == name.lower():
                return coin
        return None

    def search_by_contract(self, data: List[Dict], contract: str) -> Optional[Dict]:
        # Bitget doesn't support contract search
        raise NotImplementedError("Bitget API doesn't support contract search")

    def format_coin_info(self, coin: Optional[Dict]) -> str:
        if not coin or not isinstance(coin, dict):
            return "No coin found"

        try:
            # For Bitget response format
            if "data" in coin and isinstance(coin["data"], list) and len(coin["data"]) > 0:
                coin_data = coin["data"][0]
            else:
                coin_data = coin

            result = [f"Coin: {coin_data.get('coin', 'N/A')}"]
            if "chains" in coin_data and coin_data["chains"]:
                chain = coin_data["chains"][0]  # Get first chain info
                result.extend([
                    f"Chain: {chain.get('chain', 'N/A')}",
                    f"Withdrawal Fee: {chain.get('withdrawFee', 'N/A')}",
                    f"Min Deposit: {chain.get('minDepositAmount', 'N/A')}",
                    f"Min Withdrawal: {chain.get('minWithdrawAmount', 'N/A')}",
                    f"Contract Address: {chain.get('contractAddress', 'N/A')}"
                ])
            return "\n".join(result)
        except Exception as e:
            return f"Error formatting coin info: {str(e)}" 