from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from services.exchange_service import ExchangeService
import logging
from typing import Dict, Optional, Tuple, List

router = Router()
exchange_service = ExchangeService()
logger = logging.getLogger(__name__)

@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer(
        "Welcome to Crypto Exchange Info Bot! 🚀\n\n"
        "Send me a coin name to get:\n"
        "• Prices across all exchanges\n"
        "• Arbitrage opportunities\n"
        "• Transfer possibilities\n\n"
        "Example: 'BTC' or 'ETH'"
    )

async def calculate_arbitrage(prices: Dict[str, Dict[str, Optional[float]]]) -> List[Dict]:
    """Calculate arbitrage opportunities between exchanges"""
    opportunities = []
    exchanges = list(prices.keys())
    
    for i in range(len(exchanges)):
        for j in range(i + 1, len(exchanges)):
            ex1, ex2 = exchanges[i], exchanges[j]
            
            # Compare SPOT prices
            if prices[ex1]['spot'] and prices[ex2]['spot']:
                price1, price2 = prices[ex1]['spot'], prices[ex2]['spot']
                spread = abs(price1 - price2)
                percentage = (spread / min(price1, price2)) * 100
                
                if percentage >= 0.5:  # Only show opportunities with >0.5% difference
                    opportunities.append({
                        'type': 'spot',
                        'exchange1': ex1,
                        'exchange2': ex2,
                        'price1': price1,
                        'price2': price2,
                        'spread': spread,
                        'percentage': percentage
                    })
            
            # Compare FUTURES prices
            if prices[ex1]['futures'] and prices[ex2]['futures']:
                price1, price2 = prices[ex1]['futures'], prices[ex2]['futures']
                spread = abs(price1 - price2)
                percentage = (spread / min(price1, price2)) * 100
                
                if percentage >= 0.5:
                    opportunities.append({
                        'type': 'futures',
                        'exchange1': ex1,
                        'exchange2': ex2,
                        'price1': price1,
                        'price2': price2,
                        'spread': spread,
                        'percentage': percentage
                    })
            
            # Compare SPOT vs FUTURES within same exchange
            for ex in [ex1, ex2]:
                if prices[ex]['spot'] and prices[ex]['futures']:
                    spot, futures = prices[ex]['spot'], prices[ex]['futures']
                    spread = abs(spot - futures)
                    percentage = (spread / min(spot, futures)) * 100
                    
                    if percentage >= 0.5:
                        opportunities.append({
                            'type': 'spot_futures',
                            'exchange': ex,
                            'spot_price': spot,
                            'futures_price': futures,
                            'spread': spread,
                            'percentage': percentage
                        })
    
    return sorted(opportunities, key=lambda x: x['percentage'], reverse=True)

def format_price_comparison(prices: Dict[str, Dict[str, Optional[float]]], symbol: str) -> str:
    """Format price comparison table"""
    result = [f"💰 Price Comparison for {symbol}:"]
    
    # Header
    result.append("\n┌─────────┬────────────┬────────────┐")
    result.append("│ Exchange│    SPOT    │  FUTURES   │")
    result.append("├─────────┼────────────┼────────────┤")
    
    for exchange in prices:
        spot_price = f"${prices[exchange]['spot']:.2f}" if prices[exchange]['spot'] else "N/A"
        futures_price = f"${prices[exchange]['futures']:.2f}" if prices[exchange]['futures'] else "N/A"
        
        # Pad exchange name and prices for alignment
        exchange_pad = exchange.ljust(7)
        spot_pad = spot_price.ljust(10)
        futures_pad = futures_price.ljust(10)
        
        result.append(f"│ {exchange_pad}│ {spot_pad}│ {futures_pad}│")
    
    result.append("└─────────┴────────────┴────────────┘")
    return "\n".join(result)

def format_arbitrage_opportunities(opportunities: List[Dict]) -> str:
    """Format arbitrage opportunities"""
    if not opportunities:
        return "\n🤔 No significant arbitrage opportunities found"
    
    result = ["\n📈 Arbitrage Opportunities:"]
    
    for opp in opportunities:
        if opp['type'] in ['spot', 'futures']:
            result.append(
                f"\n{opp['type'].upper()} Market:"
                f"\n• Buy on {opp['exchange1']} at ${opp['price1']:.2f}"
                f"\n• Sell on {opp['exchange2']} at ${opp['price2']:.2f}"
                f"\n• Spread: ${opp['spread']:.2f} ({opp['percentage']:.2f}%)"
                f"\n• Transfer: {opp['exchange1']} ➡️ {opp['exchange2']}"
            )
        else:  # spot_futures
            result.append(
                f"\nSpot-Futures on {opp['exchange']}:"
                f"\n• Spot Price: ${opp['spot_price']:.2f}"
                f"\n• Futures Price: ${opp['futures_price']:.2f}"
                f"\n• Spread: ${opp['spread']:.2f} ({opp['percentage']:.2f}%)"
            )
        result.append("")  # Add empty line between opportunities
    
    return "\n".join(result)

@router.message()
async def handle_search(message: Message):
    query = message.text.strip().upper()
    
    if not query:
        await message.answer("Please send a valid coin name")
        return

    try:
        # Send initial message
        status_message = await message.answer("🔍 Searching across exchanges...")
        
        exchanges = ["bitget", "gate", "mexc"]
        prices = {}
        
        # Collect prices from all exchanges
        for exchange in exchanges:
            prices[exchange] = {'spot': None, 'futures': None}
            try:
                # Get both SPOT and FUTURES prices
                spot_price = await exchange_service.get_average_price(exchange, query, market_type="spot")
                futures_price = await exchange_service.get_average_price(exchange, query, market_type="futures")
                
                prices[exchange]['spot'] = spot_price
                prices[exchange]['futures'] = futures_price
                
            except Exception as e:
                logger.error(f"Error getting prices for {exchange}: {str(e)}")
                continue
        
        # If no prices found at all
        if not any(any(v.values()) for v in prices.values()):
            await status_message.edit_text(f"❌ No prices found for '{query}' on any exchange")
            return
        
        # Calculate arbitrage opportunities
        opportunities = await calculate_arbitrage(prices)
        
        # Format response
        response = [
            f"🎯 Analysis for {query}:",
            format_price_comparison(prices, query),
            format_arbitrage_opportunities(opportunities),
            "\n💡 Tips:",
            "• Always check transfer fees before executing trades",
            "• Market prices may change quickly",
            "• Consider exchange trading fees",
            "• Verify withdrawal/deposit status on each exchange"
        ]
        
        # Update status message with results
        await status_message.edit_text(
            "\n".join(response),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Error in handle_search: {str(e)}", exc_info=True)
        await message.answer(f"❌ Error occurred while searching: {str(e)}") 