from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message
from services.exchange_service import ExchangeService
import logging
from typing import Dict, Optional, Tuple, List
import asyncio
from datetime import datetime
from dex.dex_tools import DexTools
import os

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

async def calculate_arbitrage(prices: Dict[str, Dict[str, Optional[float]]]) -> List[Dict]:
    """Calculate all possible arbitrage opportunities between exchanges and DEX"""
    opportunities = []
    exchanges = [ex for ex in prices.keys() if not prices[ex].get('is_dex', False)]
    dex_chains = [ex for ex in prices.keys() if prices[ex].get('is_dex', False)]
    
    logger.info(f"Found DEX chains: {dex_chains}")
    logger.info(f"Found CEX exchanges: {exchanges}")
    
    # Helper function to calculate percentage difference
    def calc_percentage(price1: float, price2: float) -> float:
        return ((price2 - price1) / price1) * 100
    
    # Compare DEX to CEX opportunities
    for dex in dex_chains:
        dex_price = prices[dex]['spot']  # DEX only has spot price
        if not dex_price:
            logger.warning(f"No price found for DEX {dex}")
            continue
            
        logger.info(f"Processing DEX {dex} with price ${dex_price:.4f}")
        
        for ex in exchanges:
            logger.debug(f"Comparing with CEX {ex}")
            # DEX to CEX Spot
            if prices[ex]['spot']:
                cex_spot_price = prices[ex]['spot']
                spread = abs(cex_spot_price - dex_price)
                
                # Calculate percentage based on buy price
                if dex_price < cex_spot_price:
                    percentage = ((cex_spot_price - dex_price) / dex_price) * 100
                    logger.debug(f"DEX->CEX Spot: {dex}->{ex}: {dex_price:.4f}->{cex_spot_price:.4f} = {percentage:.2f}%")
                else:
                    percentage = ((dex_price - cex_spot_price) / cex_spot_price) * 100
                    logger.debug(f"CEX->DEX Spot: {ex}->{dex}: {cex_spot_price:.4f}->{dex_price:.4f} = {percentage:.2f}%")
                
                if percentage >= 0.1:
                    logger.info(f"Found arbitrage opportunity: {'DEX->CEX' if dex_price < cex_spot_price else 'CEX->DEX'} Spot with {percentage:.2f}%")
                    if dex_price < cex_spot_price:
                        opportunities.append({
                            'type': 'dex_to_cex_spot',
                            'dex': dex,
                            'cex': ex,
                            'dex_price': dex_price,
                            'cex_price': cex_spot_price,
                            'spread': spread,
                            'percentage': percentage
                        })
                    else:
                        opportunities.append({
                            'type': 'cex_to_dex_spot',
                            'dex': dex,
                            'cex': ex,
                            'dex_price': dex_price,
                            'cex_price': cex_spot_price,
                            'spread': spread,
                            'percentage': percentage
                        })
            
            # DEX to CEX Futures
            if prices[ex]['futures']:
                cex_futures_price = prices[ex]['futures']
                spread = abs(cex_futures_price - dex_price)
                
                # Calculate percentage based on buy price
                if dex_price < cex_futures_price:
                    percentage = ((cex_futures_price - dex_price) / dex_price) * 100
                    logger.debug(f"DEX->CEX Futures: {dex}->{ex}: {dex_price:.4f}->{cex_futures_price:.4f} = {percentage:.2f}%")
                else:
                    percentage = ((dex_price - cex_futures_price) / cex_futures_price) * 100
                    logger.debug(f"CEX->DEX Futures: {ex}->{dex}: {cex_futures_price:.4f}->{dex_price:.4f} = {percentage:.2f}%")
                
                if percentage >= 0.1:
                    logger.info(f"Found arbitrage opportunity: {'DEX->CEX' if dex_price < cex_futures_price else 'CEX->DEX'} Futures with {percentage:.2f}%")
                    if dex_price < cex_futures_price:
                        opportunities.append({
                            'type': 'dex_to_cex_futures',
                            'dex': dex,
                            'cex': ex,
                            'dex_price': dex_price,
                            'cex_price': cex_futures_price,
                            'spread': spread,
                            'percentage': percentage
                        })
                    else:
                        opportunities.append({
                            'type': 'cex_to_dex_futures',
                            'dex': dex,
                            'cex': ex,
                            'dex_price': dex_price,
                            'cex_price': cex_futures_price,
                            'spread': spread,
                            'percentage': percentage
                        })
    
    # Compare all CEX combinations
    for i in range(len(exchanges)):
        for j in range(len(exchanges)):
            if i != j:
                ex1, ex2 = exchanges[i], exchanges[j]
                
                # SPOT to SPOT between exchanges
                if prices[ex1]['spot'] and prices[ex2]['spot']:
                    buy_price, sell_price = prices[ex1]['spot'], prices[ex2]['spot']
                    if buy_price < sell_price:
                        spread = sell_price - buy_price
                        percentage = calc_percentage(buy_price, sell_price)
                        
                        if percentage >= 0.1:
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
                    if buy_price < sell_price:
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
                    if buy_price < sell_price:
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
            if spot < futures:
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
        profit = opp['spread'] * 100  # Example calculation, adjust as needed
        
        if opp['type'] == 'dex_to_cex_spot':
            dex = f"{opp['dex'].upper():6}"
            cex = f"{opp['cex'].upper():6}"
            route = f"{dex}→ {cex}"
            result.append(
                f"DEX→S    {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
        
        elif opp['type'] == 'dex_to_cex_futures':
            dex = f"{opp['dex'].upper():6}"
            cex = f"{opp['cex'].upper():6}"
            route = f"{dex}→ {cex}"
            result.append(
                f"DEX→F    {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
        
        elif opp['type'] == 'cross_exchange_spot':
            ex1 = f"{opp['exchange1'].upper():6}"
            ex2 = f"{opp['exchange2'].upper():6}"
            route = f"{ex1}→ {ex2}"
            result.append(
                f"S         {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
        
        elif opp['type'] == 'cross_exchange_futures':
            ex1 = f"{opp['exchange1'].upper():6}"
            ex2 = f"{opp['exchange2'].upper():6}"
            route = f"{ex1}→ {ex2}"
            result.append(
                f"F         {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
        
        elif opp['type'] == 'cross_exchange_spot_futures':
            ex1 = f"{opp['spot_exchange'].upper():6}"
            ex2 = f"{opp['futures_exchange'].upper():6}"
            route = f"{ex1}→ {ex2}"
            if opp['spot_price'] < opp['futures_price']:
                cross_type = "S→F"
            else:
                cross_type = "F→S"
            result.append(
                f"CROSS {cross_type} {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
        
        else:  # same_exchange_spot_futures
            route = f"{opp['exchange'].upper():15}"
            result.append(
                f"S/F       {route:<15} {opp['percentage']:>5.1f}%  ${profit:>5.2f}"
            )
    
    result.append("</pre>")
    return "\n".join(result)

async def monitor_prices(message: Message, query: str):
    """Background task to monitor prices and detect arbitrage opportunities"""
    try:
        last_opportunities = set()
        
        while True:
            prices = {}
            has_any_price = False
            price_message = f"📊 Current prices for {query}:\n\n"

            # Get DEX prices
            try:
                logger.info(f"Starting DEX price check for {query}")
                chains = await exchange_service.get_currency_chains("gate", query)
                logger.info(f"Retrieved chains for {query}: {chains}")
                
                if not chains:
                    logger.info(f"No chains found for {query}")
                else:
                    logger.info(f"Initializing DexTools with API key")
                    dex_tools = DexTools(api_key=os.getenv("DEXTOOLS_API_KEY"))
                    # Map chain names to DexTools format
                    chain_mapping = {
                        'BASEEVM': 'base',
                        'ETH': 'ether',
                        'BSC': 'bsc',
                        'MATIC': 'polygon',
                        'ARBITRUM': 'arbitrum',
                        'OPTIMISM': 'optimism',
                        'AVAX': 'avalanche'
                    }
                    logger.debug(f"Chain mapping configuration: {chain_mapping}")
                    
                    # Handle chains as a list of tuples
                    for chain_name, contract_address in chains:
                        if not chain_name or not contract_address:
                            logger.warning(f"Invalid chain data: {chain_name}, {contract_address}")
                            continue
                            
                        try:
                            # Convert chain name to DexTools format
                            dextools_chain = chain_mapping.get(chain_name.upper())
                            if dextools_chain:
                                logger.info(f"Processing chain {chain_name} ({dextools_chain}) for token {query}")
                                logger.debug(f"Contract address for {chain_name}: {contract_address}")
                                
                                logger.info(f"Requesting DexTools price for {query} on {dextools_chain}")
                                price = dex_tools.get_token_price(dextools_chain, contract_address)
                                
                                if price:
                                    logger.info(f"Successfully got price for {query} on {dextools_chain}: ${price:.4f}")
                                    prices[chain_name] = {
                                        'spot': price,
                                        'futures': None,
                                        'is_dex': True  # Mark as DEX
                                    }
                                    has_any_price = True
                                    price_message += f"DEX ({chain_name.upper()}): ${price:.4f}\n"
                                else:
                                    logger.warning(f"No price returned from DexTools for {query} on {dextools_chain}")
                            else:
                                logger.warning(f"Unsupported chain {chain_name} for DexTools")
                        except Exception as e:
                            logger.error(f"Error getting DEX price for chain {chain_name}: {str(e)}", exc_info=True)
            except Exception as e:
                logger.error(f"Error in DEX price retrieval process: {str(e)}", exc_info=True)
            
            for exchange in ["bitget", "gate", "mexc", "bybit"]:
                prices[exchange] = {
                    'spot': None,
                    'futures': None,
                    'is_dex': False  # Mark as CEX
                }
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
                opportunities = await calculate_arbitrage(prices)
                
                # Filter opportunities > 1%
                significant_opportunities = [opp for opp in opportunities if opp['percentage'] >= 0.2]
                
                # Create unique identifiers for current opportunities
                current_opps = set()
                for opp in significant_opportunities:
                    try:
                        logger.debug(f"Processing opportunity: {opp}")
                        opp_id = f"{opp['type']}_{opp['percentage']:.2f}"
                        
                        # Handle different opportunity types
                        if opp['type'] == 'dex_to_cex_spot' or opp['type'] == 'dex_to_cex_futures':
                            opp_id += f"_{opp['dex']}_{opp['cex']}"
                        elif opp['type'] == 'cross_exchange_spot' or opp['type'] == 'cross_exchange_futures':
                            opp_id += f"_{opp['exchange1']}_{opp['exchange2']}"
                        elif opp['type'] == 'cross_exchange_spot_futures':
                            opp_id += f"_{opp['spot_exchange']}_{opp['futures_exchange']}"
                        elif opp['type'] == 'same_exchange_spot_futures':
                            opp_id += f"_{opp['exchange']}"
                        else:
                            logger.warning(f"Unknown opportunity type: {opp['type']}")
                            continue
                            
                        current_opps.add(opp_id)
                        logger.debug(f"Added opportunity ID: {opp_id}")
                    except KeyError as ke:
                        logger.error(f"Missing key in opportunity dict: {ke}", exc_info=True)
                        logger.debug(f"Opportunity data: {opp}")
                        continue
                    except Exception as e:
                        logger.error(f"Error processing opportunity: {str(e)}", exc_info=True)
                        logger.debug(f"Opportunity data: {opp}")
                        continue
                
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
                            if opp['type'] == 'dex_to_cex_spot':
                                if opp['dex_price'] < opp['cex_price']:
                                    alert_msg += (
                                        f"Type: DEX to CEX Spot\n"
                                        f"Buy on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                        f"Sell on: {opp['cex'].upper()} at ${opp['cex_price']:.4f}\n"
                                        f"Price difference: {opp['percentage']:.2f}%\n"
                                    )
                                else:
                                    alert_msg += (
                                        f"Type: CEX to DEX Spot\n"
                                        f"Buy on: {opp['cex'].upper()} at ${opp['cex_price']:.4f}\n"
                                        f"Sell on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                        f"Price difference: {opp['percentage']:.2f}%\n"
                                    )
                            elif opp['type'] == 'cex_to_dex_spot':
                                alert_msg += (
                                    f"Type: CEX to DEX Spot\n"
                                    f"Buy on: {opp['cex'].upper()} at ${opp['cex_price']:.4f}\n"
                                    f"Sell on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                    f"Price difference: {opp['percentage']:.2f}%\n"
                                )
                            elif opp['type'] == 'dex_to_cex_futures':
                                if opp['dex_price'] < opp['cex_price']:
                                    alert_msg += (
                                        f"Type: DEX to CEX Futures\n"
                                        f"Buy on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                        f"Sell on: {opp['cex'].upper()} at ${opp['cex_price']:.4f}\n"
                                        f"Price difference: {opp['percentage']:.2f}%\n"
                                    )
                                else:
                                    alert_msg += (
                                        f"Type: CEX to DEX Futures\n"
                                        f"Buy on: {opp['cex'].upper()} at ${opp['cex_price']:.4f}\n"
                                        f"Sell on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                        f"Price difference: {opp['percentage']:.2f}%\n"
                                    )
                            elif opp['type'] == 'cex_to_dex_futures':
                                alert_msg += (
                                    f"Type: CEX to DEX Futures\n"
                                    f"Buy on: {opp['cex'].upper()} at ${opp['cex_price']:.4f}\n"
                                    f"Sell on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                    f"Price difference: {opp['percentage']:.2f}%\n"
                                )
                            elif opp['type'] == 'cross_exchange_spot':
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
                                    f"Type: Spot-to-Futures\n"
                                    f"Spot exchange: {opp['spot_exchange'].upper()} at ${opp['spot_price']:.4f}\n"
                                    f"Futures exchange: {opp['futures_exchange'].upper()} at ${opp['futures_price']:.4f}\n"
                                    f"Price difference: {opp['percentage']:.2f}%\n"
                                )
                            
                            # Only send alert if it's not a same-exchange opportunity
                            if opp['type'] != 'same_exchange_spot_futures':
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