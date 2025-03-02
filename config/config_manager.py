import os
from dotenv import load_dotenv
from typing import Dict

class ConfigManager:
    load_dotenv()

    @staticmethod
    def get_bot_token() -> str:
        token = os.getenv('BOT_TOKEN')
        if not token:
            raise ValueError("BOT_TOKEN not found in environment variables")
        return token

    @staticmethod
    def get_mexc_credentials() -> dict:
        api_key = os.getenv('MEXC_API_KEY')
        api_secret = os.getenv('MEXC_API_SECRET')
        if not api_key or not api_secret:
            raise ValueError("MEXC credentials not found in environment variables")
        return {
            'api_key': api_key,
            'api_secret': api_secret
        }

    @staticmethod
    def get_bitget_credentials() -> dict:
        api_key = os.getenv('BITGET_API_KEY')
        api_secret = os.getenv('BITGET_SECRET_KEY')
        if not api_key or not api_secret:
            raise ValueError("Bitget credentials not found in environment variables")
        return {
            'api_key': api_key,
            'api_secret': api_secret
        }

    @staticmethod
    def get_bybit_credentials() -> dict:
        api_key = os.getenv('BYBIT_API_KEY')
        api_secret = os.getenv('BYBIT_API_SECRET')
        if not api_key or not api_secret:
            raise ValueError("Bybit credentials not found in environment variables")
        return {
            'api_key': api_key,
            'api_secret': api_secret
        } 