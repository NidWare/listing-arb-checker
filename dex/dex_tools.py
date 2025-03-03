import requests
import logging
class DexTools:

    basic_url = "https://public-api.dextools.io/trial/v2/"

    def __init__(self, api_key):
        self.api_key = api_key

    def get_price(self, contract):
        url = f"{self.basic_url}price/{contract}"
        return self._send_get(url)

    def get_token_price(self, chain, address):
        """
        Get token price for a specific token on a chain
        :param chain: Chain name (e.g., 'ether', 'bsc')
        :param address: Token contract address
        :return: Token price as float or None if not available
        """
        url = f"{self.basic_url}token/{chain}/{address}/price"
        response = self._send_get(url)
        logging.info(f"Token price response: {response}")
        if response and 'data' in response and 'price' in response['data']:
            return response['data']['price']
        return None

    def get_token_info(self, chain, address):
        url = f"{self.basic_url}token/{chain}/{address}"
        return self._send_get(url)

    def _get_headers(self):
        return {'x-api-key': self.api_key, 'accept':'application/json'}

    def _send_request(self, method, url, params=None, data=None):
        headers = self._get_headers()
        response = requests.request(
            method=method,
            url=url,
            headers=headers,
            params=params if method == 'GET' else None,
            json=data if method in ['POST', 'PUT'] else None
        )
        return response.json()

    def _send_get(self, url, params=None):
        return self._send_request('GET', url, params=params)

    def _send_post(self, url, data=None):
        return self._send_request('POST', url, data=data)


