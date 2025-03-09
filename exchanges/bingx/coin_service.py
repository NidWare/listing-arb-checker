from typing import Dict, List, Optional
from exchanges.base_coin_service import BaseCoinService


class BingxCoinService(BaseCoinService):
    """
    Service for handling coin-related operations on BingX exchange
    """
    
    def search_by_name(self, data: List[Dict], name: str) -> List[Dict]:
        """
        Search for coins by name
        
        Args:
            data: List of coin data
            name: Coin name to search for
            
        Returns:
            List of matching coins
        """
        # Convert name to uppercase for case-insensitive comparison
        name = name.upper()
        
        # BingX API might return data in various formats, 
        # this implementation assumes a standard format.
        # Adjust as needed based on actual API response
        return [coin for coin in data 
                if name in coin.get('coin', '').upper() or 
                name in coin.get('name', '').upper()]
    
    def search_by_contract(self, data: List[Dict], contract: str) -> Optional[Dict]:
        """
        Search for a coin by contract address
        
        Args:
            data: List of coin data
            contract: Contract address to search for
            
        Returns:
            Matching coin data or None
        """
        # Contract addresses are case-insensitive in most chains
        contract = contract.lower()
        
        for coin in data:
            # Check the networkList for matching contract address
            if 'networkList' in coin:
                for network in coin.get('networkList', []):
                    if network.get('contractAddress', '').lower() == contract:
                        return coin
        
        return None
    
    def format_coin_info(self, coin_data: List[Dict]) -> str:
        """
        Format coin information for display
        
        Args:
            coin_data: List of coin data
            
        Returns:
            Formatted string of coin information
        """
        if not coin_data:
            return "No coins found"
        
        result = []
        for coin in coin_data:
            name = coin.get('coin', '')
            fullname = coin.get('name', '')
            
            networks = []
            for network in coin.get('networkList', []):
                network_name = network.get('network', '')
                is_deposit_enabled = network.get('depositEnable', False)
                is_withdraw_enabled = network.get('withdrawEnable', False)
                
                status = []
                if is_deposit_enabled:
                    status.append("deposit:enabled")
                else:
                    status.append("deposit:disabled")
                    
                if is_withdraw_enabled:
                    status.append("withdraw:enabled")
                else:
                    status.append("withdraw:disabled")
                
                networks.append(f"{network_name} ({', '.join(status)})")
            
            coin_info = f"{name} ({fullname}): {', '.join(networks)}"
            result.append(coin_info)
        
        return "\n".join(result) 