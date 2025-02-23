from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

class BaseCoinService(ABC):
    @abstractmethod
    def search_by_name(self, data: List[Dict], name: str) -> Optional[Dict]:
        pass

    @abstractmethod
    def search_by_contract(self, data: List[Dict], contract: str) -> Optional[Dict]:
        pass

    @abstractmethod
    def format_coin_info(self, coin: Optional[Dict]) -> str:
        pass 