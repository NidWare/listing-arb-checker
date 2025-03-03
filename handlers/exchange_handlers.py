from aiogram import Router, F
from aiogram.filters import Command, ChatMemberUpdatedFilter
from aiogram.types import Message, ChatMemberUpdated
from aiogram.enums.chat_member_status import ChatMemberStatus
from services.exchange_service import ExchangeService
import logging
from typing import Dict, Optional, Tuple, List, Set
import asyncio
from datetime import datetime
from dex.dex_tools import DexTools
import os

router = Router()
exchange_service = ExchangeService()
logger = logging.getLogger(__name__)

# Store active monitoring tasks per chat
active_monitors: Dict[int, asyncio.Task] = {}

# Store admin IDs
ADMIN_IDS: Set[int] = {741239404, 180247888}

def is_admin(user_id: int) -> bool:
    """Check if user is an admin"""
    return user_id in ADMIN_IDS

@router.my_chat_member()
async def on_bot_status_changed(event: ChatMemberUpdated):
    """Handle when bot's status changes in a chat"""
    chat_id = event.chat.id
    topic_id = int(os.getenv("TOPIC_ID", "1"))  # Get topic ID from env
    
    # Bot was added as admin
    if (event.old_chat_member.status in [ChatMemberStatus.LEFT, ChatMemberStatus.MEMBER] and 
        event.new_chat_member.status == ChatMemberStatus.ADMINISTRATOR):
        # Don't send welcome message in groups anymore
        pass
    
    # Bot was removed as admin
    elif (event.old_chat_member.status == ChatMemberStatus.ADMINISTRATOR and 
          event.new_chat_member.status != ChatMemberStatus.ADMINISTRATOR):
        if chat_id in active_monitors:
            active_monitors[chat_id].cancel()
            del active_monitors[chat_id]

@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    
    # Check if user is admin and message is in private chat
    if not is_admin(user_id) or message.chat.type != "private":
        # Only respond in private chats
        if message.chat.type == "private":
            await message.answer("❌ Only admins can use this bot")
        return
        
    await message.answer(
        "Welcome to Crypto Exchange Info Bot! 🚀\n\n"
        "Send me a coin name to get:\n"
        "• Prices across all exchanges\n"
        "• Arbitrage opportunities\n"
        "• Transfer possibilities\n\n"
        "Example: 'BTC' or 'ETH'"
    )

@router.message(Command("chatinfo"))
async def cmd_chat_info(message: Message):
    """Handler to get detailed chat information"""
    # Get topic ID from config but allow message thread ID to override it
    config_topic_id = int(os.getenv("TOPIC_ID", "1"))
    actual_topic_id = message.message_thread_id if message.message_thread_id else config_topic_id

    chat_info = (
        f"📝 Chat Information:\n\n"
        f"Chat ID: {message.chat.id}\n"
        f"Chat Type: {message.chat.type}\n"
        f"Chat Title: {message.chat.title if message.chat.title else 'N/A'}\n"
        f"Username: {message.chat.username if hasattr(message.chat, 'username') else 'N/A'}\n"
        f"Current Topic ID: {message.message_thread_id if message.message_thread_id else 'N/A'}\n"
        f"Config Topic ID: {config_topic_id}\n"
        f"Using Topic ID: {actual_topic_id}"
    )
    
    logger.info(f"Chat Info Request:\n{chat_info}")
    
    try:
        # Always use the topic ID from config for supergroups
        if message.chat.type == "supergroup":
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=chat_info,
                message_thread_id=config_topic_id
            )
        else:
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=chat_info
            )
    except Exception as e:
        logger.error(f"Error sending chat info: {str(e)}", exc_info=True)
        # If error occurs, try sending without topic ID
        try:
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=f"Error sending with topic. Info:\n\n{chat_info}"
            )
        except Exception as e2:
            logger.error(f"Error sending fallback message: {str(e2)}", exc_info=True)

async def calculate_arbitrage(prices: Dict[str, Dict[str, Optional[float]]]) -> List[Dict]:
    """Calculate all possible arbitrage opportunities between exchanges and DEX"""
    opportunities = []
    exchanges = [ex for ex in prices.keys() if not prices[ex].get('is_dex', False)]
    dex_chains = [ex for ex in prices.keys() if prices[ex].get('is_dex', False)]
    
    logger.info(f"Found DEX chains: {dex_chains}")
    logger.info(f"Found CEX exchanges: {exchanges}")
    
    # Helper function to calculate percentage difference
    def calc_percentage(buy_price: float, sell_price: float) -> float:
        return ((sell_price - buy_price) / buy_price) * 100
    
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
                
                # Check DEX -> CEX opportunity
                dex_to_cex_percentage = calc_percentage(dex_price, cex_spot_price)
                logger.debug(f"DEX->CEX Spot: {dex}->{ex}: {dex_price:.4f}->{cex_spot_price:.4f} = {dex_to_cex_percentage:.2f}%")
                
                # Check CEX -> DEX opportunity
                cex_to_dex_percentage = calc_percentage(cex_spot_price, dex_price)
                logger.debug(f"CEX->DEX Spot: {ex}->{dex}: {cex_spot_price:.4f}->{dex_price:.4f} = {cex_to_dex_percentage:.2f}%")
                
                # Add DEX -> CEX opportunity if profitable
                if dex_to_cex_percentage >= 0.1:
                    logger.info(f"Found DEX->CEX Spot opportunity with {dex_to_cex_percentage:.2f}%")
                    opportunities.append({
                        'type': 'dex_to_cex_spot',
                        'dex': dex,
                        'cex': ex,
                        'dex_price': dex_price,
                        'cex_price': cex_spot_price,
                        'spread': spread,
                        'percentage': dex_to_cex_percentage
                    })
                
                # Add CEX -> DEX opportunity if profitable
                if cex_to_dex_percentage >= 0.1:
                    logger.info(f"Found CEX->DEX Spot opportunity with {cex_to_dex_percentage:.2f}%")
                    opportunities.append({
                        'type': 'cex_to_dex_spot',
                        'dex': dex,
                        'cex': ex,
                        'dex_price': dex_price,
                        'cex_price': cex_spot_price,
                        'spread': spread,
                        'percentage': cex_to_dex_percentage
                    })
            
            # DEX to CEX Futures
            if prices[ex]['futures']:
                cex_futures_price = prices[ex]['futures']
                spread = abs(cex_futures_price - dex_price)
                
                # Check DEX -> CEX Futures opportunity
                dex_to_cex_percentage = calc_percentage(dex_price, cex_futures_price)
                logger.debug(f"DEX->CEX Futures: {dex}->{ex}: {dex_price:.4f}->{cex_futures_price:.4f} = {dex_to_cex_percentage:.2f}%")
                
                # Check CEX -> DEX Futures opportunity
                cex_to_dex_percentage = calc_percentage(cex_futures_price, dex_price)
                logger.debug(f"CEX->DEX Futures: {ex}->{dex}: {cex_futures_price:.4f}->{dex_price:.4f} = {cex_to_dex_percentage:.2f}%")
                
                # Add DEX -> CEX Futures opportunity if profitable
                if dex_to_cex_percentage >= 0.1:
                    logger.info(f"Found DEX->CEX Futures opportunity with {dex_to_cex_percentage:.2f}%")
                    opportunities.append({
                        'type': 'dex_to_cex_futures',
                        'dex': dex,
                        'cex': ex,
                        'dex_price': dex_price,
                        'cex_price': cex_futures_price,
                        'spread': spread,
                        'percentage': dex_to_cex_percentage
                    })
                
                # Add CEX -> DEX Futures opportunity if profitable
                if cex_to_dex_percentage >= 0.1:
                    logger.info(f"Found CEX->DEX Futures opportunity with {cex_to_dex_percentage:.2f}%")
                    opportunities.append({
                        'type': 'cex_to_dex_futures',
                        'dex': dex,
                        'cex': ex,
                        'dex_price': dex_price,
                        'cex_price': cex_futures_price,
                        'spread': spread,
                        'percentage': cex_to_dex_percentage
                    })
    
    # Compare all CEX combinations
    for i in range(len(exchanges)):
        for j in range(len(exchanges)):
            if i != j:
                ex1, ex2 = exchanges[i], exchanges[j]
                
                # SPOT to SPOT between exchanges
                if prices[ex1]['spot'] and prices[ex2]['spot']:
                    price1, price2 = prices[ex1]['spot'], prices[ex2]['spot']
                    spread = abs(price2 - price1)
                    
                    # Check both directions
                    percentage1 = calc_percentage(price1, price2)
                    percentage2 = calc_percentage(price2, price1)
                    
                    logger.debug(f"CEX Spot {ex1}->{ex2}: {price1:.4f}->{price2:.4f} = {percentage1:.2f}%")
                    logger.debug(f"CEX Spot {ex2}->{ex1}: {price2:.4f}->{price1:.4f} = {percentage2:.2f}%")
                    
                    # Add opportunity if profitable in either direction
                    if percentage1 >= 0.1:
                        logger.info(f"Found CEX->CEX Spot opportunity: {ex1}->{ex2} with {percentage1:.2f}%")
                        opportunities.append({
                            'type': 'cross_exchange_spot',
                            'exchange1': ex1,
                            'exchange2': ex2,
                            'price1': price1,
                            'price2': price2,
                            'spread': spread,
                            'percentage': percentage1
                        })
                    if percentage2 >= 0.1:
                        logger.info(f"Found CEX->CEX Spot opportunity: {ex2}->{ex1} with {percentage2:.2f}%")
                        opportunities.append({
                            'type': 'cross_exchange_spot',
                            'exchange1': ex2,
                            'exchange2': ex1,
                            'price1': price2,
                            'price2': price1,
                            'spread': spread,
                            'percentage': percentage2
                        })
                
                # FUTURES to FUTURES between exchanges
                if prices[ex1]['futures'] and prices[ex2]['futures']:
                    price1, price2 = prices[ex1]['futures'], prices[ex2]['futures']
                    spread = abs(price2 - price1)
                    
                    # Check both directions
                    percentage1 = calc_percentage(price1, price2)
                    percentage2 = calc_percentage(price2, price1)
                    
                    logger.debug(f"CEX Futures {ex1}->{ex2}: {price1:.4f}->{price2:.4f} = {percentage1:.2f}%")
                    logger.debug(f"CEX Futures {ex2}->{ex1}: {price2:.4f}->{price1:.4f} = {percentage2:.2f}%")
                    
                    # Add opportunity if profitable in either direction
                    if percentage1 >= 0.1:
                        logger.info(f"Found CEX->CEX Futures opportunity: {ex1}->{ex2} with {percentage1:.2f}%")
                        opportunities.append({
                            'type': 'cross_exchange_futures',
                            'exchange1': ex1,
                            'exchange2': ex2,
                            'price1': price1,
                            'price2': price2,
                            'spread': spread,
                            'percentage': percentage1
                        })
                    if percentage2 >= 0.1:
                        logger.info(f"Found CEX->CEX Futures opportunity: {ex2}->{ex1} with {percentage2:.2f}%")
                        opportunities.append({
                            'type': 'cross_exchange_futures',
                            'exchange1': ex2,
                            'exchange2': ex1,
                            'price1': price2,
                            'price2': price1,
                            'spread': spread,
                            'percentage': percentage2
                        })
                
                # SPOT to FUTURES between exchanges
                if prices[ex1]['spot'] and prices[ex2]['futures']:
                    spot_price = prices[ex1]['spot']
                    futures_price = prices[ex2]['futures']
                    spread = abs(futures_price - spot_price)
                    
                    # Calculate percentage
                    percentage = calc_percentage(spot_price, futures_price)
                    logger.debug(f"CEX Spot->Futures {ex1}->{ex2}: {spot_price:.4f}->{futures_price:.4f} = {percentage:.2f}%")
                    
                    if percentage >= 0.1:
                        logger.info(f"Found CEX Spot->Futures opportunity: {ex1}->{ex2} with {percentage:.2f}%")
                        opportunities.append({
                            'type': 'cross_exchange_spot_futures',
                            'spot_exchange': ex1,
                            'futures_exchange': ex2,
                            'spot_price': spot_price,
                            'futures_price': futures_price,
                            'spread': spread,
                            'percentage': percentage
                        })
                
                # FUTURES to SPOT between exchanges
                if prices[ex1]['futures'] and prices[ex2]['spot']:
                    futures_price = prices[ex1]['futures']
                    spot_price = prices[ex2]['spot']
                    spread = abs(spot_price - futures_price)
                    
                    # Calculate percentage
                    percentage = calc_percentage(futures_price, spot_price)
                    logger.debug(f"CEX Futures->Spot {ex1}->{ex2}: {futures_price:.4f}->{spot_price:.4f} = {percentage:.2f}%")
                    
                    if percentage >= 0.1:
                        logger.info(f"Found CEX Futures->Spot opportunity: {ex1}->{ex2} with {percentage:.2f}%")
                        opportunities.append({
                            'type': 'cross_exchange_futures_spot',
                            'futures_exchange': ex1,
                            'spot_exchange': ex2,
                            'futures_price': futures_price,
                            'spot_price': spot_price,
                            'spread': spread,
                            'percentage': percentage
                        })
                
                # SPOT to FUTURES within same exchange
                if prices[ex1]['spot'] and prices[ex1]['futures']:
                    spot_price = prices[ex1]['spot']
                    futures_price = prices[ex1]['futures']
                    spread = abs(futures_price - spot_price)
                    
                    # Calculate percentage
                    percentage = calc_percentage(spot_price, futures_price)
                    logger.debug(f"Same CEX Spot->Futures {ex1}: {spot_price:.4f}->{futures_price:.4f} = {percentage:.2f}%")
                    
                    if percentage >= 0.1:
                        logger.info(f"Found same-exchange Spot->Futures opportunity on {ex1} with {percentage:.2f}%")
                        opportunities.append({
                            'type': 'same_exchange_spot_futures',
                            'exchange': ex1,
                            'spot_price': spot_price,
                            'futures_price': futures_price,
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

async def monitor_prices(chat_id: int, query: str, bot):
    """Background task to monitor prices and detect arbitrage opportunities"""
    try:
        last_opportunities = set()
        alert_group_id = int(os.getenv("ALERT_GROUP_ID"))
        topic_id = int(os.getenv("TOPIC_ID", "1"))
        
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
            await bot.send_message(alert_group_id, price_message, message_thread_id=topic_id)

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
                        if opp['type'] in ['dex_to_cex_spot', 'dex_to_cex_futures', 'cex_to_dex_spot', 'cex_to_dex_futures']:
                            if opp['type'].startswith('dex_to_cex'):
                                opp_id += f"_{opp['dex']}_{opp['cex']}"
                            else:  # cex_to_dex types
                                opp_id += f"_{opp['cex']}_{opp['dex']}"
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
                        try:
                            opp_id = f"{opp['type']}_{opp['percentage']:.2f}"
                            
                            # Generate consistent opportunity IDs
                            if opp['type'] in ['dex_to_cex_spot', 'dex_to_cex_futures', 'cex_to_dex_spot', 'cex_to_dex_futures']:
                                if opp['type'].startswith('dex_to_cex'):
                                    opp_id += f"_{opp['dex']}_{opp['cex']}"
                                else:  # cex_to_dex types
                                    opp_id += f"_{opp['cex']}_{opp['dex']}"
                            elif opp['type'] == 'cross_exchange_spot' or opp['type'] == 'cross_exchange_futures':
                                opp_id += f"_{opp['exchange1']}_{opp['exchange2']}"
                            elif opp['type'] == 'cross_exchange_spot_futures':
                                opp_id += f"_{opp['spot_exchange']}_{opp['futures_exchange']}"
                            elif opp['type'] == 'same_exchange_spot_futures':
                                opp_id += f"_{opp['exchange']}"
                            else:
                                continue
                            
                            if opp_id in new_opps:
                                try:
                                    alert_msg = f"🚨 New Arbitrage Opportunity at {timestamp}!\n\n"
                                    valid_alert = True  # Flag to track if the alert is valid
                                    
                                    if opp['type'] == 'dex_to_cex_spot' and all(k in opp for k in ['dex', 'cex', 'dex_price', 'cex_price', 'percentage']):
                                        alert_msg += (
                                            f"Type: DEX to CEX Spot\n"
                                            f"Buy on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                            f"Sell on: {opp['cex'].upper()} at ${opp['cex_price']:.4f}\n"
                                            f"Price difference: {opp['percentage']:.2f}%\n"
                                            f"Profit potential: ${opp['spread']:.4f}\n"
                                        )
                                    elif opp['type'] == 'cex_to_dex_spot' and all(k in opp for k in ['dex', 'cex', 'dex_price', 'cex_price', 'percentage']):
                                        alert_msg += (
                                            f"Type: CEX to DEX Spot\n"
                                            f"Buy on: {opp['cex'].upper()} at ${opp['cex_price']:.4f}\n"
                                            f"Sell on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                            f"Price difference: {opp['percentage']:.2f}%\n"
                                            f"Profit potential: ${opp['spread']:.4f}\n"
                                        )
                                    elif opp['type'] == 'dex_to_cex_futures' and all(k in opp for k in ['dex', 'cex', 'dex_price', 'cex_price', 'percentage']):
                                        alert_msg += (
                                            f"Type: DEX to CEX Futures\n"
                                            f"Buy on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                            f"Sell on: {opp['cex'].upper()} Futures at ${opp['cex_price']:.4f}\n"
                                            f"Price difference: {opp['percentage']:.2f}%\n"
                                            f"Profit potential: ${opp['spread']:.4f}\n"
                                        )
                                    elif opp['type'] == 'cex_to_dex_futures' and all(k in opp for k in ['dex', 'cex', 'dex_price', 'cex_price', 'percentage']):
                                        alert_msg += (
                                            f"Type: CEX to DEX Futures\n"
                                            f"Buy on: {opp['cex'].upper()} Futures at ${opp['cex_price']:.4f}\n"
                                            f"Sell on: {opp['dex'].upper()} DEX at ${opp['dex_price']:.4f}\n"
                                            f"Price difference: {opp['percentage']:.2f}%\n"
                                            f"Profit potential: ${opp['spread']:.4f}\n"
                                        )
                                    elif opp['type'] == 'cross_exchange_spot' and all(k in opp for k in ['exchange1', 'exchange2', 'price1', 'price2', 'percentage']):
                                        alert_msg += (
                                            f"Type: Spot-to-Spot\n"
                                            f"Buy on: {opp['exchange1'].upper()} at ${opp['price1']:.4f}\n"
                                            f"Sell on: {opp['exchange2'].upper()} at ${opp['price2']:.4f}\n"
                                            f"Price difference: {opp['percentage']:.2f}%\n"
                                        )
                                    elif opp['type'] == 'cross_exchange_futures' and all(k in opp for k in ['exchange1', 'exchange2', 'price1', 'price2', 'percentage']):
                                        alert_msg += (
                                            f"Type: Futures-to-Futures\n"
                                            f"Buy on: {opp['exchange1'].upper()} at ${opp['price1']:.4f}\n"
                                            f"Sell on: {opp['exchange2'].upper()} at ${opp['price2']:.4f}\n"
                                            f"Price difference: {opp['percentage']:.2f}%\n"
                                        )
                                    elif opp['type'] == 'cross_exchange_spot_futures' and all(k in opp for k in ['spot_exchange', 'futures_exchange', 'spot_price', 'futures_price', 'percentage']):
                                        alert_msg += (
                                            f"Type: Spot-to-Futures\n"
                                            f"Buy on: {opp['spot_exchange'].upper()} (Spot) at ${opp['spot_price']:.4f}\n"
                                            f"Sell on: {opp['futures_exchange'].upper()} (Futures) at ${opp['futures_price']:.4f}\n"
                                            f"Price difference: {opp['percentage']:.2f}%\n"
                                        )
                                    elif opp['type'] == 'same_exchange_spot_futures' and all(k in opp for k in ['exchange', 'spot_price', 'futures_price', 'percentage']):
                                        alert_msg += (
                                            f"Type: Same-Exchange Spot-Futures\n"
                                            f"Exchange: {opp['exchange'].upper()}\n"
                                            f"Spot price: ${opp['spot_price']:.4f}\n"
                                            f"Futures price: ${opp['futures_price']:.4f}\n"
                                            f"Price difference: {opp['percentage']:.2f}%\n"
                                        )
                                    else:
                                        valid_alert = False
                                        logger.warning(f"Invalid or incomplete opportunity data: {opp}")
                                        
                                    # Only send the alert if it's valid and has content
                                    if valid_alert and len(alert_msg.strip()) > 40:  # More than just the timestamp line
                                        await bot.send_message(alert_group_id, alert_msg, message_thread_id=topic_id)
                                    
                                except Exception as e:
                                    logger.error(f"Error formatting alert message: {str(e)}", exc_info=True)
                                    logger.debug(f"Opportunity data: {opp}")
                                    continue
                        except Exception as e:
                            logger.error(f"Error processing opportunity alert: {str(e)}", exc_info=True)
                            logger.debug(f"Opportunity data: {opp}")
                            continue
            
            # Update last opportunities
            last_opportunities = current_opps
            
            # Wait for 5 seconds before next check
            await asyncio.sleep(3)
            
    except asyncio.CancelledError:
        logger.info(f"Monitoring stopped for {query}")
    except Exception as e:
        logger.error(f"Error in price monitoring: {str(e)}")
        await bot.send_message(alert_group_id, f"❌ Error in price monitoring: {str(e)}", message_thread_id=topic_id)

@router.message(Command("stop"))
async def cmd_stop(message: Message):
    """Stop monitoring for the chat"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    alert_group_id = int(os.getenv("ALERT_GROUP_ID"))
    topic_id = int(os.getenv("TOPIC_ID", "0"))  # Get topic ID from env
    bot = message.bot
    
    # Check if user is admin and message is in private chat
    if not is_admin(user_id) or message.chat.type != "private":
        # Only respond in private chats
        if message.chat.type == "private":
            await message.answer("❌ Only admins can stop monitoring")
        return
        
    if chat_id in active_monitors:
        active_monitors[chat_id].cancel()
        del active_monitors[chat_id]
        # Send confirmation to both alert group and admin
        await bot.send_message(alert_group_id, "✅ Monitoring stopped", message_thread_id=topic_id)
        await message.answer("✅ Monitoring stopped in the alert group")
    else:
        await message.answer("❌ No active monitoring found")

@router.message()
async def handle_search(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    alert_group_id = int(os.getenv("ALERT_GROUP_ID"))
    topic_id = int(os.getenv("TOPIC_ID", "1"))
    bot = message.bot
    
    # Check if user is admin and message is in private chat
    if not is_admin(user_id) or message.chat.type != "private":
        # Only respond in private chats
        if message.chat.type == "private":
            await message.answer("❌ Only admins can specify coins to monitor")
        return
    
    query = message.text.strip().upper()
    
    if not query:
        await message.answer("Please send a valid coin name")
        return

    try:
        # Cancel existing monitoring task if any
        if chat_id in active_monitors:
            active_monitors[chat_id].cancel()
            del active_monitors[chat_id]
        
        # Send initial message to alert group
        await bot.send_message(
            chat_id=alert_group_id,
            text=f"🔍 Starting price monitoring for {query}...",
            message_thread_id=topic_id
        )
        
        # Start new monitoring task with the target chat ID and bot instance
        task = asyncio.create_task(monitor_prices(chat_id, query, bot))
        active_monitors[chat_id] = task
        
        # Send confirmation to both alert group and admin
        await bot.send_message(
            chat_id=alert_group_id,
            text="✅ Monitoring started!\n\n"
                 "I will notify you when there are arbitrage opportunities with >2% difference.\n"
                 "Use /stop command to stop monitoring.",
            message_thread_id=topic_id
        )
        
        await message.answer("✅ Monitoring started in the alert group!")

    except Exception as e:
        logger.error(f"Error in handle_search: {str(e)}", exc_info=True)
        try:
            # Send error to admin in private chat
            await message.answer(f"❌ Error occurred while searching: {str(e)}")
        except Exception as e2:
            logger.error(f"Error sending error message: {str(e2)}", exc_info=True) 