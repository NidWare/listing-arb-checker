from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from services.exchange_service import ExchangeService
import logging

router = Router()
exchange_service = ExchangeService()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Welcome to Crypto Exchange Info Bot!\n"
        "Send me a coin name to search across all exchanges.\n"
        "Example: 'BTC' or 'ETH'")

@router.message()
async def handle_search(message: Message):
    query = message.text.strip().upper()  # Convert to uppercase for consistency
    
    if not query:
        await message.answer("Please send a valid coin name")
        return

    try:
        exchanges = ["bitget", "gate", "mexc"]
        results = []
        
        for exchange in exchanges:
            try:
                result = await exchange_service.search_coin(
                    exchange=exchange,
                    search_type="name",
                    query=query
                )
                if result:
                    # Get both SPOT and FUTURES prices
                    try:
                        spot_price = await exchange_service.get_average_price(exchange, query, market_type="spot")
                        futures_price = await exchange_service.get_average_price(exchange, query, market_type="futures")
                        
                        price_info = "\n📊 Market Prices:"
                        if spot_price:
                            price_info += f"\n• SPOT: ${spot_price}"
                        if futures_price:
                            price_info += f"\n• FUTURES: ${futures_price}"
                            
                        result += price_info
                    except Exception as e:
                        logger.error(f"Error getting prices for {exchange}: {str(e)}")
                    
                    results.append(result)
            except Exception as e:
                logger.error(f"Error searching {exchange}: {str(e)}")
                continue

        if not results:
            await message.answer(f"No results found for '{query}' on any exchange")
            return

        # Combine all results with better formatting
        combined_results = "\n\n" + "\n\n".join(results)
        await message.answer(
            f"💱 Search results for '{query}':{combined_results}", 
            parse_mode="HTML"
        )

    except Exception as e:
        await message.answer(f"Error occurred while searching: {str(e)}") 