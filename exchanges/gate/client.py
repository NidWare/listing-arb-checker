import aiohttp
import logging
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
        
        # Dynamic price formatting based on magnitude
        if price < 0.0001:
            formatted_price = f"{price:.8f}"
        elif price < 0.01:
            formatted_price = f"{price:.6f}"
        elif price < 1:
            formatted_price = f"{price:.5f}"
        else:
            formatted_price = f"{price:.4f}"
            
        return f"Market price for {symbol}: {formatted_price} USDT" 

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "DepositChecker/1.0"
        }

    async def check_token_availability(self, symbol: str) -> Dict[str, bool]:
        """
        Check if a token is available for deposit and withdrawal on Gate.io.
        
        Args:
            symbol: The token symbol to check
            
        Returns:
            Dict with keys 'deposit' and 'withdrawal', each with boolean values
            indicating availability status
        """
        async with aiohttp.ClientSession(headers=self._get_headers()) as session:
            url = f"{self.base_url}/wallet/currency_chains"
            params = {"currency": symbol}
            
            try:
                async with session.get(url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        
                        # Initialize with unavailable status
                        deposit_available = False
                        withdrawal_available = False
                        
                        # Check all chains for the currency
                        for chain in data:
                            # If any chain has deposits enabled (is_deposit_disabled=0), mark deposits as available
                            if chain.get("is_deposit_disabled", 1) == 0:
                                deposit_available = True
                                
                            # If any chain has withdrawals enabled (is_withdraw_disabled=0), mark withdrawals as available
                            if chain.get("is_withdraw_disabled", 1) == 0:
                                withdrawal_available = True
                                
                            # If both are already available, we can stop checking
                            if deposit_available and withdrawal_available:
                                break
                                
                        return {
                            "deposit": deposit_available,
                            "withdrawal": withdrawal_available
                        }
                    else:
                        logging.error(f"Error checking token availability for {symbol}: Status {response.status}")
                        return {"deposit": False, "withdrawal": False}
            except Exception as e:
                logging.error(f"Error checking token availability for {symbol}: {e}")
                return {"deposit": False, "withdrawal": False}

    async def get_currency_chains(self, currency: str) -> List[Tuple[str, str]]:
        """
        Fetch currency information and return list of chain-address pairs.
        Args:
            currency: Currency symbol (e.g., 'GT', 'BTC', 'ETH', etc.)
        Returns:
            List of tuples (chain_name, address) where address is not empty.
        """
        logging.debug(f"Fetching currency chains for {currency}")
        try:
            async with aiohttp.ClientSession(headers=self._get_headers()) as session:
                url = f"{self.base_url}/spot/currencies/{currency}"
                logging.debug(f"Making request to {url}")
                async with session.get(url) as response:
                    if response.status == 200:
                        try:
                            data = await response.json()
                            logging.debug(f"Raw API response for {currency}: {data}")
                            
                            if not isinstance(data, dict):
                                logging.error(f"Unexpected response format for {currency}: {type(data)}, value: {data}")
                                return []
                                
                            chains = data.get('chains', [])
                            logging.debug(f"Extracted chains data for {currency}: {chains}")
                            
                            if not isinstance(chains, list):
                                logging.error(f"Unexpected chains format for {currency}: type: {type(chains)}, value: {chains}")
                                return []
                                
                            logging.debug(f"Found {len(chains)} chains for {currency}")
                            result = []
                            for idx, chain in enumerate(chains):
                                logging.debug(f"Processing chain {idx + 1}/{len(chains)} for {currency}: {chain}")
                                
                                if not isinstance(chain, dict):
                                    logging.warning(f"Invalid chain format at index {idx}: type: {type(chain)}, value: {chain}")
                                    continue
                                    
                                chain_name = chain.get('name')
                                addr = chain.get('addr')
                                logging.debug(f"Chain {idx + 1} data - name: {chain_name} ({type(chain_name)}), addr: {addr} ({type(addr)})")
                                
                                if chain_name and addr and isinstance(chain_name, str) and isinstance(addr, str):
                                    result.append((chain_name, addr))
                                    logging.debug(f"Added chain {chain_name} with address for {currency}")
                                else:
                                    logging.warning(f"Invalid chain data at index {idx} - name: {chain_name} ({type(chain_name)}), addr: {addr} ({type(addr)})")
                                    
                            logging.info(f"Successfully retrieved {len(result)} valid chains for {currency}. Final result: {result}")
                            return result
                        except Exception as e:
                            logging.error(f"Error parsing response for {currency}: {str(e)}", exc_info=True)
                            return []
                    logging.warning(f"Failed to fetch currency chains for {currency}. Status code: {response.status}")
                    try:
                        error_body = await response.text()
                        logging.warning(f"Error response body: {error_body}")
                    except Exception as e:
                        logging.warning(f"Could not read error response: {str(e)}")
                    return []
        except Exception as e:
            logging.error(f"Error in get_currency_chains for {currency}: {str(e)}", exc_info=True)
            return []
