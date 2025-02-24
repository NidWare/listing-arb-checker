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

def format_price_comparison(prices: Dict[str, Dict[str, Optional[float]]], symbol: str) -> str:
    """Format price comparison in monospace table format"""
    result = [f"💰 Price Comparison for {symbol}:\n"]
    
    # Header with monospace formatting
    result.append(f"<pre>")
    result.append(f"Exchange  Market   Price    Spread")
    result.append(f"──────────────────────────────────")
    
    # Format each exchange's prices
    for exchange in prices:
        spot_price = prices[exchange]['spot']
        futures_price = prices[exchange]['futures']
        
        # Calculate spread percentage between spot and futures
        if spot_price and futures_price:
            spread = abs(spot_price - futures_price)
            spread_pct = (spread / min(spot_price, futures_price)) * 100
            spread_str = f"{spread_pct:.1f}%"
        else:
            spread_str = "N/A"
        
        # Format SPOT line
        if spot_price:
            result.append(
                f"{exchange.upper():<8} SPOT    ${spot_price:<7.4f} {spread_str:<6}"
            )
        
        # Format FUTURES line
        if futures_price:
            result.append(
                f"{exchange.upper():<8} FUTURES ${futures_price:<7.4f} {spread_str:<6}"
            )
    
    result.append("</pre>")
    return "\n".join(result)

async def calculate_arbitrage(prices: Dict[str, Dict[str, Optional[float]]]) -> List[Dict]:
    """Calculate all possible arbitrage opportunities between exchanges"""
    opportunities = []
    exchanges = list(prices.keys())
    
    # Helper function to calculate percentage difference
    def calc_percentage(price1: float, price2: float) -> float:
        return abs(price1 - price2) / min(price1, price2) * 100
    
    # Compare all possible combinations
    for i in range(len(exchanges)):
        for j in range(len(exchanges)):
            if i != j:  # Compare different exchanges
                ex1, ex2 = exchanges[i], exchanges[j]
                
                # SPOT to SPOT between exchanges
                if prices[ex1]['spot'] and prices[ex2]['spot']:
                    price1, price2 = prices[ex1]['spot'], prices[ex2]['spot']
                    spread = abs(price1 - price2)
                    percentage = calc_percentage(price1, price2)
                    
                    if percentage >= 0.1:  # Lower threshold to show more opportunities
                        opportunities.append({
                            'type': 'cross_exchange_spot',
                            'exchange1': ex1,
                            'exchange2': ex2,
                            'price1': price1,
                            'price2': price2,
                            'spread': spread,
                            'percentage': percentage
                        })
                
                # FUTURES to FUTURES between exchanges
                if prices[ex1]['futures'] and prices[ex2]['futures']:
                    price1, price2 = prices[ex1]['futures'], prices[ex2]['futures']
                    spread = abs(price1 - price2)
                    percentage = calc_percentage(price1, price2)
                    
                    if percentage >= 0.1:
                        opportunities.append({
                            'type': 'cross_exchange_futures',
                            'exchange1': ex1,
                            'exchange2': ex2,
                            'price1': price1,
                            'price2': price2,
                            'spread': spread,
                            'percentage': percentage
                        })
                
                # SPOT to FUTURES between different exchanges
                if prices[ex1]['spot'] and prices[ex2]['futures']:
                    price1, price2 = prices[ex1]['spot'], prices[ex2]['futures']
                    spread = abs(price1 - price2)
                    percentage = calc_percentage(price1, price2)
                    
                    if percentage >= 0.1:
                        opportunities.append({
                            'type': 'cross_exchange_spot_futures',
                            'spot_exchange': ex1,
                            'futures_exchange': ex2,
                            'spot_price': price1,
                            'futures_price': price2,
                            'spread': spread,
                            'percentage': percentage
                        })
    
    # Within same exchange SPOT vs FUTURES
    for ex in exchanges:
        if prices[ex]['spot'] and prices[ex]['futures']:
            spot, futures = prices[ex]['spot'], prices[ex]['futures']
            spread = abs(spot - futures)
            percentage = calc_percentage(spot, futures)
            
            if percentage >= 0.1:
                opportunities.append({
                    'type': 'same_exchange_spot_futures',
                    'exchange': ex,
                    'spot_price': spot,
                    'futures_price': futures,
                    'spread': spread,
                    'percentage': percentage
                })
    
    return sorted(opportunities, key=lambda x: x['percentage'], reverse=True)

def format_arbitrage_opportunities(opportunities: List[Dict]) -> str:
    """Format arbitrage opportunities in monospace table format"""
    if not opportunities:
        return "\n🤔 No significant arbitrage opportunities found"
    
    result = ["\n📈 Arbitrage Opportunities:\n"]
    result.append("<pre>")
    result.append("Type     Exchange Route      Spread  Profit")
    result.append("──────────────────────────────────────────")
    
    for opp in opportunities:
        if opp['type'] == 'cross_exchange_spot':
            profit = opp['spread'] * 100  # Example calculation, adjust as needed
            ex1 = f"{opp['exchange1'].upper():6}"
            ex2 = f"{opp['exchange2'].upper():6}"
            route = f"{ex1}→ {ex2}"
            result.append(
                f"SPOT     {route:<15} {opp['percentage']:>5.1f}% ${profit:>6.2f}"
            )
        
        elif opp['type'] == 'cross_exchange_futures':
            profit = opp['spread'] * 100  # Example calculation, adjust as needed
            ex1 = f"{opp['exchange1'].upper():6}"
            ex2 = f"{opp['exchange2'].upper():6}"
            route = f"{ex1}→ {ex2}"
            result.append(
                f"FUTURES  {route:<15} {opp['percentage']:>5.1f}% ${profit:>6.2f}"
            )
        
        elif opp['type'] == 'cross_exchange_spot_futures':
            profit = opp['spread'] * 100  # Example calculation, adjust as needed
            ex1 = f"{opp['spot_exchange'].upper():6}"
            ex2 = f"{opp['futures_exchange'].upper():6}"
            route = f"{ex1}→ {ex2}"
            result.append(
                f"CROSS    {route:<15} {opp['percentage']:>5.1f}% ${profit:>6.2f}"
            )
        
        else:  # same_exchange_spot_futures
            profit = opp['spread'] * 100  # Example calculation, adjust as needed
            route = f"{opp['exchange'].upper():15}"
            result.append(
                f"SPOTFUT  {route:<15} {opp['percentage']:>5.1f}% ${profit:>6.2f}"
            )
    
    result.append("</pre>")
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
            "• Check transfer fees and limits",
            "• Verify market liquidity",
            "• Monitor price changes",
            "• Consider trading fees"
        ]
        
        # Update status message with results
        await status_message.edit_text(
            "\n".join(response),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error(f"Error in handle_search: {str(e)}", exc_info=True)
        await message.answer(f"❌ Error occurred while searching: {str(e)}") 