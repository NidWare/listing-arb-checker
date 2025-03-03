from typing import Dict, Any, Optional, List
from ..base_coin_service import BaseCoinService

class BybitCoinService(BaseCoinService):
    def search_by_name(self, data: List[Dict], name: str) -> Optional[Dict]:
        """Search for a coin by its name in the Bybit response data"""
        if not data.get('result', {}).get('list'):
            return None
            
        for coin in data['result']['list']:
            if coin.get('name') == name or coin.get('coin') == name:
                return coin
        return None

    def search_by_contract(self, data: List[Dict], contract: str) -> Optional[Dict]:
        """Search for a coin by its contract address in the Bybit response data"""
        if not data.get('result', {}).get('list'):
            return None
            
        for coin in data['result']['list']:
            for chain in coin.get('chains', []):
                if chain.get('chainType') == contract or chain.get('contract') == contract:
                    return coin
        return None

    def format_coin_info(self, coin: Optional[Dict]) -> str:
        """Format coin information for display"""
        if not coin:
            return "Coin not found in the response"

        output = [
            f"\nCoin Details:",
            f"Name: {coin.get('name')}",
            f"Coin: {coin.get('coin')}",
            f"Status: {coin.get('status')}",
        ]
        
        if coin.get('chains'):
            output.append("\nSupported Networks:")
            for chain in coin.get('chains', []):
                output.extend([
                    f"  Network: {chain.get('chainType')}",
                    f"  Deposit Status: {chain.get('depositStatus')}",
                    f"  Withdrawal Status: {chain.get('withdrawStatus')}",
                    f"  Withdrawal Fee: {chain.get('withdrawFee')}",
                    ""
                ])
            
        return "\n".join(output) 