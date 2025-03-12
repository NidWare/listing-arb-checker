import logging
from typing import Dict, Any, Optional, List
from ..base_coin_service import BaseCoinService

logger = logging.getLogger(__name__)

class BinanceCoinService(BaseCoinService):
    """Service to process Binance coin data"""
    
    def search_by_name(self, data: List[Dict], name: str) -> Optional[Dict]:
        """
        Search for a coin by its name/symbol in Binance data
        
        Args:
            data: List of coin data from Binance
            name: Name/symbol of the coin to search for
            
        Returns:
            Coin data if found, None otherwise
        """
        name = name.upper()
        for coin in data:
            if coin.get('coin') == name:
                return coin
        return None
        
    def search_by_contract(self, data: List[Dict], contract: str) -> Optional[Dict]:
        """
        Search for a coin by its contract address in Binance data
        
        Args:
            data: List of coin data from Binance
            contract: Contract address to search for
            
        Returns:
            Coin data if found, None otherwise
        """
        contract = contract.lower()
        for coin in data:
            # Look through all networks for matching contract
            for network in coin.get('networkList', []):
                if network.get('contractAddress', '').lower() == contract:
                    return coin
        return None
        
    def format_coin_info(self, coin: Optional[Dict]) -> str:
        """
        Format coin information for display
        
        Args:
            coin: Coin data from Binance
            
        Returns:
            Formatted string with coin information
        """
        if not coin:
            return "Coin not found on Binance"
            
        name = coin.get('coin', 'Unknown')
        deposit_enabled = coin.get('depositAllEnable', False)
        withdraw_enabled = coin.get('withdrawAllEnable', False)
        
        networks = []
        for network in coin.get('networkList', []):
            network_name = network.get('network', 'Unknown')
            deposit_network = network.get('depositEnable', False)
            withdraw_network = network.get('withdrawEnable', False)
            
            status = []
            if deposit_network:
                status.append("Deposit ✅")
            else:
                status.append("Deposit ❌")
                
            if withdraw_network:
                status.append("Withdraw ✅")
            else:
                status.append("Withdraw ❌")
                
            networks.append(f"- {network_name}: {' | '.join(status)}")
            
        result = [
            f"🪙 {name} on Binance:",
            f"Overall Deposit: {'✅' if deposit_enabled else '❌'}",
            f"Overall Withdraw: {'✅' if withdraw_enabled else '❌'}",
            "\nNetworks:"
        ]
        
        result.extend(networks)
        return "\n".join(result) 