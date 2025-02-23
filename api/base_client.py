from abc import ABC, abstractmethod
import requests
from typing import Dict, Any, Optional

class BaseAPIClient(ABC):
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key

    @abstractmethod
    def get_headers(self) -> Dict[str, str]:
        pass

    def make_request(self, method: str, url: str, headers: Optional[Dict] = None, 
                    params: Optional[Dict] = None) -> requests.Response:
        headers = headers or self.get_headers()
        return requests.request(method, url, headers=headers, params=params) 