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
    def get_admin_bot_token() -> str:
        token = os.getenv('ADMIN_BOT_TOKEN')
        if not token:
            raise ValueError("ADMIN_BOT_TOKEN not found in environment variables")
        return token

    @staticmethod
    def get_alert_group_id() -> int:
        group_id = os.getenv('ALERT_GROUP_ID')
        if not group_id:
            raise ValueError("ALERT_GROUP_ID not found in environment variables")
        try:
            return int(group_id)
        except ValueError:
            raise ValueError(f"Invalid ALERT_GROUP_ID format: {group_id}")

    @staticmethod
    def get_admin_user_ids() -> list[int]:
        admin_ids = os.getenv('ADMIN_USER_IDS', '')
        if not admin_ids:
            raise ValueError("ADMIN_USER_IDS not found in environment variables")
        return [int(id.strip()) for id in admin_ids.split(',')]

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

    @staticmethod
    def get_bingx_credentials() -> dict:
        api_key = os.getenv('BINGX_API_KEY')
        api_secret = os.getenv('BINGX_API_SECRET')
        if not api_key or not api_secret:
            raise ValueError("BingX credentials not found in environment variables")
        return {
            'api_key': api_key,
            'api_secret': api_secret
        } 