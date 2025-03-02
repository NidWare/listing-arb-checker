from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from services.exchange_service import ExchangeService
import logging
from typing import Dict, Optional, Tuple, List
import asyncio
from datetime import datetime

router = Router()
exchange_service = ExchangeService()
logger = logging.getLogger(__name__)

# Store active monitoring tasks
active_monitors = {}

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
        return (price2 - price1) / price1 * 100
    
    # Compare all possible combinations
    for i in range(len(exchanges)):
        for j in range(len(exchanges)):
            if i != j:  # Compare different exchanges
                ex1, ex2 = exchanges[i], exchanges[j]
                
                # SPOT to SPOT between exchanges
                if prices[ex1]['spot'] and prices[ex2]['spot']:
                    buy_price, sell_price = prices[ex1]['spot'], prices[ex2]['spot']
                    if buy_price < sell_price:  # Only if we can buy low and sell high
                        spread = sell_price - buy_price
                        percentage = calc_percentage(buy_price, sell_price)
                        
                        if percentage >= 0.1:  # Lower threshold to show more opportunities
                            opportunities.append({
                                'type': 'cross_exchange_spot',
                                'exchange1': ex1,
                                'exchange2': ex2,
                                'price1': buy_price,
                                'price2': sell_price,
                                'spread': spread,
                                'percentage': percentage
                            })
                
                # FUTURES to FUTURES between exchanges
                if prices[ex1]['futures'] and prices[ex2]['futures']:
                    buy_price, sell_price = prices[ex1]['futures'], prices[ex2]['futures']
                    if buy_price < sell_price:  # Only if we can buy low and sell high
                        spread = sell_price - buy_price
                        percentage = calc_percentage(buy_price, sell_price)
                        
                        if percentage >= 0.1:
                            opportunities.append({
                                'type': 'cross_exchange_futures',
                                'exchange1': ex1,
                                'exchange2': ex2,
                                'price1': buy_price,
                                'price2': sell_price,
                                'spread': spread,
                                'percentage': percentage
                            })
                
                # SPOT to FUTURES between different exchanges
                if prices[ex1]['spot'] and prices[ex2]['futures']:
                    buy_price, sell_price = prices[ex1]['spot'], prices[ex2]['futures']
                    if buy_price < sell_price:  # Only if we can buy low and sell high
                        spread = sell_price - buy_price
                        percentage = calc_percentage(buy_price, sell_price)
                        
                        if percentage >= 0.1:
                            opportunities.append({
                                'type': 'cross_exchange_spot_futures',
                                'spot_exchange': ex1,
                                'futures_exchange': ex2,
                                'spot_price': buy_price,
                                'futures_price': sell_price,
                                'spread': spread,
                                'percentage': percentage
                            })
    
    # Within same exchange SPOT vs FUTURES
    for ex in exchanges:
        if prices[ex]['spot'] and prices[ex]['futures']:
            spot, futures = prices[ex]['spot'], prices[ex]['futures']
            if spot < futures:  # Only if spot price is lower than futures
                spread = futures - spot
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
    result.append("Type      Exchange Route      Spread   Profit")
    result.append("───────────────────────────────────────────")
    
    for opp in opportunities:
        if opp['type'] == 'cross_exchange_spot':
            profit = opp['spread'] * 100  # Example calculation, adjust as needed
            ex1 = f"{opp['exchange1'].upper():6}"
            ex2 = f"{opp['exchange2'].upper():6}"
            route = f"{ex1}→ {ex2}"
            result.append(
                f"S         {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
        
        elif opp['type'] == 'cross_exchange_futures':
            profit = opp['spread'] * 100  # Example calculation, adjust as needed
            ex1 = f"{opp['exchange1'].upper():6}"
            ex2 = f"{opp['exchange2'].upper():6}"
            route = f"{ex1}→ {ex2}"
            result.append(
                f"F         {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
        
        elif opp['type'] == 'cross_exchange_spot_futures':
            profit = opp['spread'] * 100  # Example calculation, adjust as needed
            ex1 = f"{opp['spot_exchange'].upper():6}"
            ex2 = f"{opp['futures_exchange'].upper():6}"
            route = f"{ex1}→ {ex2}"
            # Determine if it's spot→futures or futures→spot based on prices
            if opp['spot_price'] < opp['futures_price']:
                cross_type = "S→F"  # spot to futures
            else:
                cross_type = "F→S"  # futures to spot
            result.append(
                f"CROSS {cross_type} {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
        
        else:  # same_exchange_spot_futures
            profit = opp['spread'] * 100  # Example calculation, adjust as needed
            route = f"{opp['exchange'].upper():15}"
            result.append(
                f"S/F       {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
    
    result.append("</pre>")
    return "\n".join(result)

async def monitor_prices(message: Message, query: str):
    """Background task to monitor prices and detect arbitrage opportunities"""
    try:
        last_opportunities = set()  # Store hash of last reported opportunities
        
        while True:
            prices = {}
            has_any_price = False  # Flag to track if we got any price
            price_message = f"📊 Current prices for {query}:\n\n"
            
            # Collect prices from all exchanges
            for exchange in ["bitget", "gate", "mexc", "bybit"]: # TODO: CHANGE THIS TO THE EXCHANGES YOU WANT TO MONITOR
                prices[exchange] = {'spot': None, 'futures': None}
                try:
                    spot_price = await exchange_service.get_average_price(exchange, query, market_type="spot")
                    if spot_price:
                        prices[exchange]['spot'] = spot_price
                        has_any_price = True
                        price_message += f"{exchange.upper()} Spot: ${spot_price:.4f}\n"
                except Exception as e:
                    logger.error(f"Error getting spot price for {exchange}: {str(e)}")
                    price_message += f"{exchange.upper()} Spot: Not available\n"

                try:
                    futures_price = await exchange_service.get_average_price(exchange, query, market_type="futures")
                    if futures_price:
                        prices[exchange]['futures'] = futures_price
                        has_any_price = True
                        price_message += f"{exchange.upper()} Futures: ${futures_price:.4f}\n"
                except Exception as e:
                    logger.error(f"Error getting futures price for {exchange}: {str(e)}")
                    price_message += f"{exchange.upper()} Futures: Not available\n"
                
                price_message += "\n"  # Add spacing between exchanges

            # Send current prices regardless of arbitrage opportunities
            await message.answer(price_message)

            if has_any_price:
                # Calculate arbitrage opportunities only if we have some prices
                opportunities = await calculate_arbitrage(prices)
                
                # Filter opportunities > 1%
                significant_opportunities = [opp for opp in opportunities if opp['percentage'] >= 0.3]
                
                # Create unique identifiers for current opportunities
                current_opps = set()
                for opp in significant_opportunities:
                    opp_id = f"{opp['type']}_{opp['percentage']:.2f}"
                    if 'exchange1' in opp:
                        opp_id += f"_{opp['exchange1']}_{opp['exchange2']}"
                    elif 'spot_exchange' in opp:
                        opp_id += f"_{opp['spot_exchange']}_{opp['futures_exchange']}"
                    else:
                        opp_id += f"_{opp['exchange']}"
                    current_opps.add(opp_id)
                
                # Report new opportunities
                new_opps = current_opps - last_opportunities
                if new_opps:
                    # Format and send new opportunities
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    for opp in significant_opportunities:
                        opp_id = f"{opp['type']}_{opp['percentage']:.2f}"
                        if 'exchange1' in opp:
                            opp_id += f"_{opp['exchange1']}_{opp['exchange2']}"
                        elif 'spot_exchange' in opp:
                            opp_id += f"_{opp['spot_exchange']}_{opp['futures_exchange']}"
                        else:
                            opp_id += f"_{opp['exchange']}"
                        
                        if opp_id in new_opps:
                            alert_msg = f"🚨 New Arbitrage Opportunity at {timestamp}!\n\n"
                            if opp['type'] == 'cross_exchange_spot':
                                alert_msg += (
                                    f"Type: Spot-to-Spot\n"
                                    f"Buy on: {opp['exchange1'].upper()} at ${opp['price1']:.4f}\n"
                                    f"Sell on: {opp['exchange2'].upper()} at ${opp['price2']:.4f}\n"
                                    f"Price difference: {opp['percentage']:.2f}%\n"
                                )
                            elif opp['type'] == 'cross_exchange_futures':
                                alert_msg += (
                                    f"Type: Futures-to-Futures\n"
                                    f"Buy on: {opp['exchange1'].upper()} at ${opp['price1']:.4f}\n"
                                    f"Sell on: {opp['exchange2'].upper()} at ${opp['price2']:.4f}\n"
                                    f"Price difference: {opp['percentage']:.2f}%\n"
                                )
                            elif opp['type'] == 'cross_exchange_spot_futures':
                                alert_msg += (
                                    f"Spot exchange: {opp['spot_exchange'].upper()} at ${opp['spot_price']:.4f}\n"
                                    f"Futures exchange: {opp['futures_exchange'].upper()} at ${opp['futures_price']:.4f}\n"
                                    f"Price difference: {opp['percentage']:.2f}%\n"
                                )
                            
                            await message.answer(alert_msg)
            
            # Update last opportunities
            last_opportunities = current_opps
            
            # Wait for 5 seconds before next check
            await asyncio.sleep(3)
            
    except asyncio.CancelledError:
        logger.info(f"Monitoring stopped for {query}")
    except Exception as e:
        logger.error(f"Error in price monitoring: {str(e)}")
        await message.answer(f"❌ Error in price monitoring: {str(e)}")

@router.message(Command("stop"))
async def cmd_stop(message: Message):
    """Stop monitoring for the user"""
    user_id = message.from_user.id
    if user_id in active_monitors:
        active_monitors[user_id].cancel()
        del active_monitors[user_id]
        await message.answer("✅ Monitoring stopped")
    else:
        await message.answer("❌ No active monitoring found")

@router.message()
async def handle_search(message: Message):
    query = message.text.strip().upper()
    
    if not query:
        await message.answer("Please send a valid coin name")
        return

    try:
        user_id = message.from_user.id
        
        # Cancel existing monitoring task if any
        if user_id in active_monitors:
            active_monitors[user_id].cancel()
            del active_monitors[user_id]
        
        # Send initial message
        await message.answer(f"🔍 Starting price monitoring for {query}...")
        
        # Start new monitoring task
        task = asyncio.create_task(monitor_prices(message, query))
        active_monitors[user_id] = task
        
        await message.answer(
            "✅ Monitoring started!\n\n"
            "I will notify you when there are arbitrage opportunities with >2% difference.\n"
            "Use /stop command to stop monitoring."
        )

    except Exception as e:
        logger.error(f"Error in handle_search: {str(e)}", exc_info=True)
        await message.answer(f"❌ Error occurred while searching: {str(e)}") 