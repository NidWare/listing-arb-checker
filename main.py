import argparse
from config.config_manager import ConfigManager
from api.mexc.client import MexcClient
from api.mexc.coin_service import MexcCoinService
from api.gate.client import GateClient
from api.gate.coin_service import GateCoinService
from api.bitget.client import BitgetClient
from api.bitget.coin_service import BitgetCoinService

def main():
    parser = argparse.ArgumentParser(description='Search for coin information on crypto exchanges')
    parser.add_argument('--exchange', choices=['mexc', 'gate', 'bitget'], required=True, help='Choose exchange')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--name', help='Search by coin name')
    group.add_argument('--contract', help='Search by contract address (MEXC only)')
    args = parser.parse_args()

    if args.contract and args.exchange in ['gate', 'bitget']:
        print(f"{args.exchange.capitalize()} API doesn't support contract search")
        return

    # Initialize clients and services based on exchange
    if args.exchange == 'mexc':
        credentials = ConfigManager.get_mexc_credentials()
        client = MexcClient(**credentials)
        coin_service = MexcCoinService()
        response = client.get_all_coins()
    elif args.exchange == 'gate':
        credentials = ConfigManager.get_gate_credentials()
        client = GateClient(**credentials)
        coin_service = GateCoinService()
        response = client.get_coin_info(args.name)
    else:  # bitget
        credentials = ConfigManager.get_bitget_credentials()
        client = BitgetClient(**credentials)
        coin_service = BitgetCoinService()
        response = client.get_coin_info(args.name)

    print("Status Code:", response.status_code)
    print("Response:", response.text)  # Add this line for debugging

    if response.status_code == 200:
        data = response.json()
        
        if args.name:
            if args.exchange == 'mexc':
                coin = coin_service.search_by_name(data, args.name)
            elif args.exchange == 'bitget':
                # Bitget returns the filtered data directly
                coin = data
            else:
                coin = data  # Gate.io already returns filtered data
        else:
            coin = coin_service.search_by_contract(data, args.contract)
            
        print(coin_service.format_coin_info(coin))
    else:
        print("Response Body:", response.text)

if __name__ == "__main__":
    main()