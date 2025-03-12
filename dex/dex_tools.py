import requests
import logging
class DexTools:

    basic_url = "https://public-api.dextools.io/advanced/v2/" # TODO: to check if this is the correct url

    def __init__(self, api_key):
        self.api_key = api_key
        logging.info(f"DexTools initialized with API key: {api_key[:5]}...")  # Log only first 5 chars for security

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
        logging.info(f"chain: {chain} address: {address} Token price response: {response}")
        if response and 'data' in response and 'price' in response['data']:
            return response['data']['price']
        return None

    def get_pool_price(self, chain, pool_address):
        """
        Get pool price for a specific pool on a chain
        :param chain: Chain name (e.g., 'ether', 'bsc')
        :param pool_address: Pool address
        :return: Pool price as float or None if not available
        """
        url = f"{self.basic_url}pool/{chain}/{pool_address}/price"
        response = self._send_get(url)
        logging.info(f"chain: {chain} pool_address: {pool_address} Pool price response: {response}")
        if response and 'data' in response and 'price' in response['data']:
            return response['data']['price']
        return None

    def get_token_info(self, chain, address):
        url = f"{self.basic_url}token/{chain}/{address}"
        return self._send_get(url)

    def _get_headers(self):
        headers = {'x-api-key': self.api_key, 'accept': 'application/json'}
        logging.info(f"Generated headers: {headers}")  # Log headers (API key will be visible)
        return headers

    def _send_request(self, method, url, params=None, data=None):
        headers = self._get_headers()
        logging.info(f"Making request to URL: {url}")
        logging.info(f"Request method: {method}")
        logging.info(f"Request params: {params}")
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                params=params if method == 'GET' else None,
                json=data if method in ['POST', 'PUT'] else None
            )
            logging.info(f"Response status code: {response.status_code}")
            logging.info(f"Response headers: {response.headers}")
            return response.json()
        except Exception as e:
            logging.error(f"Request failed: {str(e)}")
            return {'message': str(e)}

    def _send_get(self, url, params=None):
        return self._send_request('GET', url, params=params)

    def _send_post(self, url, data=None):
        return self._send_request('POST', url, data=data)


