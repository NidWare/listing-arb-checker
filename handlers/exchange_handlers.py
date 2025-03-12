from aiogram import Router, F
from aiogram.filters import Command, ChatMemberUpdatedFilter
from aiogram.types import Message, ChatMemberUpdated, CallbackQuery, InlineKeyboardMarkup
from aiogram.enums.chat_member_status import ChatMemberStatus
from aiogram.utils.keyboard import InlineKeyboardBuilder
from services.exchange_service import ExchangeService
import logging
from typing import Dict, Optional, Any, List, Set
import asyncio
from datetime import datetime, timezone
from dex.dex_tools import DexTools
import os
import re
import json
import aiohttp
import time
import uuid  # Add import for UUID generation

# Global constants
PRICE_CHECK_INTERVAL = 60  # seconds
MIN_ARBITRAGE_PERCENTAGE = 0.1  # 0.1%

# Define a helper function for price formatting
def format_price(price: float) -> str:
    """
    Format price with appropriate precision based on its magnitude:
    - For very small values (< 0.0001): show up to 8 decimal places
    - For small values (< 0.01): show up to 6 decimal places
    - For medium values (< 1): show up to 5 decimal places
    - For larger values: show 4 decimal places
    """
    if price is None:
        return "N/A"
        
    if price < 0.0001:
        return f"{price:.8f}"
    elif price < 0.01:
        return f"{price:.6f}"
    elif price < 1:
        return f"{price:.5f}"
    else:
        return f"{price:.4f}"

# Track active monitoring tasks
active_monitors = {}  # Format: {chat_id: {query_id: task}}

# Store temporary user queries while waiting for min percentage input
user_queries = {}  # Format: {chat_id: {query_id: {query: str, min_percentage: float, filter_mode: str}}}

# Store user filter preferences
user_filter_preferences = {}  # Format: {chat_id: "cex_only" or "all"}

# Function to generate a unique ID for each query
def generate_query_id() -> str:
    """Generate a unique ID for a monitoring query"""
    return str(uuid.uuid4())

# Create a router instance
router = Router()
exchange_service = ExchangeService()
logger = logging.getLogger(__name__)

# Store admin IDs
ADMIN_IDS_ENV = os.getenv("ADMIN_USER_IDS", "741239404,180247888")
ADMIN_IDS: Set[int] = {int(id.strip()) for id in ADMIN_IDS_ENV.split(",")}

def is_admin(user_id: int) -> bool:
    """Check if user is an admin"""
    logger.info(f"Checking if user {user_id} is admin. Admin IDs: {ADMIN_IDS}")
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
            for query_id, task in active_monitors[chat_id].items():
                task.cancel()
            del active_monitors[chat_id]

@router.message(Command("start"))
async def cmd_start(message: Message):
    # Only respond in private chats
    if message.chat.type != "private":
        return
        
    user_id = message.from_user.id
    is_user_admin = is_admin(user_id)
    
    base_message = (
        "Welcome to Crypto Exchange Info Bot! 🚀\n\n"
        "Send me a coin name to get:\n"
        "• Prices across all exchanges\n"
        "• Arbitrage opportunities\n"
        "• Transfer possibilities\n\n"
        "Example: 'BTC' or 'ETH'"
    )
    
    if is_user_admin:
        admin_commands = (
            "\n\n📊 Admin Commands:\n"
            "• /addcoin <symbol> - Start monitoring a new coin\n"
            "• /listcoins - List all monitored coins\n"
            "• /stop [id] - Stop all monitoring or a specific one\n"
            "• /setmin <id> <percentage> - Set min arbitrage %\n"
            "\nYou can monitor multiple coins simultaneously!"
        )
        await message.answer(base_message + admin_commands)
    else:
        await message.answer(base_message)

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
                message_thread_id=config_topic_id,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        else:
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=chat_info,
                parse_mode="HTML",
                disable_web_page_preview=True
            )
    except Exception as e:
        logger.error(f"Error sending chat info: {str(e)}", exc_info=True)
        # If error occurs, try sending without topic ID
        try:
            await message.bot.send_message(
                chat_id=message.chat.id,
                text=f"Error sending with topic. Info:\n\n{chat_info}",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
        except Exception as e2:
            logger.error(f"Error sending fallback message: {str(e2)}", exc_info=True)

async def calculate_arbitrage(prices: Dict[str, Dict[str, Optional[float]]], min_arbitrage_percentage: float = MIN_ARBITRAGE_PERCENTAGE, filter_mode: str = "all") -> List[Dict]:
    """Calculate all possible arbitrage opportunities between exchanges and DEX"""
    opportunities = []
    exchanges = [ex for ex in prices.keys() if not prices[ex].get('is_dex', False)]
    dex_chains = [ex for ex in prices.keys() if prices[ex].get('is_dex', False)]
    
    logger.info(f"Found DEX chains: {dex_chains}")
    logger.info(f"Found CEX exchanges: {exchanges}")
    logger.info(f"Filter mode: {filter_mode}")
    
    # Helper function to calculate percentage difference
    def calc_percentage(buy_price: float, sell_price: float) -> float:
        return ((sell_price - buy_price) / buy_price) * 100
    
    # Compare DEX to CEX opportunities (only if not in CEX-only mode)
    if filter_mode == "all" or filter_mode == "cex_dex_only" or filter_mode == "future":
        for dex in dex_chains:
            dex_price = prices[dex]['spot']  # DEX only has spot price
            if not dex_price:
                logger.warning(f"No price found for DEX {dex}")
                continue
                
            logger.info(f"Processing DEX {dex} with price ${format_price(dex_price)}")
            
            for ex in exchanges:
                logger.debug(f"Comparing with CEX {ex}")
                # DEX to CEX Spot
                if prices[ex]['spot'] and filter_mode != "future":
                    cex_spot_price = prices[ex]['spot']
                    spread = abs(cex_spot_price - dex_price)
                    
                    # Check DEX -> CEX opportunity
                    dex_to_cex_percentage = calc_percentage(dex_price, cex_spot_price)
                    logger.debug(f"DEX->CEX Spot: {dex}->{ex}: {format_price(dex_price)}->{format_price(cex_spot_price)} = {dex_to_cex_percentage:.2f}%")
                    
                    # Check CEX -> DEX opportunity
                    cex_to_dex_percentage = calc_percentage(cex_spot_price, dex_price)
                    logger.debug(f"CEX->DEX Spot: {ex}->{dex}: {format_price(cex_spot_price)}->{format_price(dex_price)} = {cex_to_dex_percentage:.2f}%")
                    
                    # Add DEX -> CEX opportunity if profitable
                    if dex_to_cex_percentage >= min_arbitrage_percentage:
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
                    if cex_to_dex_percentage >= min_arbitrage_percentage:
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
                if prices[ex]['futures'] and (filter_mode == "all" or filter_mode == "future"):
                    cex_futures_price = prices[ex]['futures']
                    spread = abs(cex_futures_price - dex_price)
                    
                    # Check DEX -> CEX Futures opportunity
                    dex_to_cex_percentage = calc_percentage(dex_price, cex_futures_price)
                    logger.debug(f"DEX->CEX Futures: {dex}->{ex}: {format_price(dex_price)}->{format_price(cex_futures_price)} = {dex_to_cex_percentage:.2f}%")
                    
                    # Check CEX -> DEX Futures opportunity
                    cex_to_dex_percentage = calc_percentage(cex_futures_price, dex_price)
                    logger.debug(f"CEX->DEX Futures: {ex}->{dex}: {format_price(cex_futures_price)}->{format_price(dex_price)} = {cex_to_dex_percentage:.2f}%")
                    
                    # Add DEX -> CEX Futures opportunity if profitable
                    if dex_to_cex_percentage >= min_arbitrage_percentage:
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
                    if cex_to_dex_percentage >= min_arbitrage_percentage:
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
    
    # Compare all CEX combinations (always shown regardless of filter)
    for i in range(len(exchanges)):
        # Skip CEX-CEX comparisons when in CEX-DEX only mode or future mode
        if filter_mode == "cex_dex_only" or filter_mode == "future":
            break
            
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
                    
                    logger.debug(f"CEX Spot {ex1}->{ex2}: {format_price(price1)}->{format_price(price2)} = {percentage1:.2f}%")
                    logger.debug(f"CEX Spot {ex2}->{ex1}: {format_price(price2)}->{format_price(price1)} = {percentage2:.2f}%")
                    
                    # Add opportunity if profitable in either direction
                    if percentage1 >= min_arbitrage_percentage:
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
                    if percentage2 >= min_arbitrage_percentage:
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
                    
                    logger.debug(f"CEX Futures {ex1}->{ex2}: {format_price(price1)}->{format_price(price2)} = {percentage1:.2f}%")
                    logger.debug(f"CEX Futures {ex2}->{ex1}: {format_price(price2)}->{format_price(price1)} = {percentage2:.2f}%")
                    
                    # Add opportunity if profitable in either direction
                    if percentage1 >= min_arbitrage_percentage:
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
                    if percentage2 >= min_arbitrage_percentage:
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
                    logger.debug(f"CEX Spot->Futures {ex1}->{ex2}: {format_price(spot_price)}->{format_price(futures_price)} = {percentage:.2f}%")
                    
                    if percentage >= min_arbitrage_percentage:
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
                    logger.debug(f"CEX Futures->Spot {ex1}->{ex2}: {format_price(futures_price)}->{format_price(spot_price)} = {percentage:.2f}%")
                    
                    if percentage >= min_arbitrage_percentage:
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
                    logger.debug(f"Same CEX Spot->Futures {ex1}: {format_price(spot_price)}->{format_price(futures_price)} = {percentage:.2f}%")
                    
                    if percentage >= min_arbitrage_percentage:
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
                f"DEX→S    {route:<15} {opp['percentage']:>5.1f}%  ${format_price(opp['spread']):>5.2f}"
            )
        
        elif opp['type'] == 'dex_to_cex_futures':
            dex = f"{opp['dex'].upper():6}"
            cex = f"{opp['cex'].upper():6}"
            route = f"{dex}→ {cex}"
            result.append(
                f"DEX→F    {route:<15} {opp['percentage']:>5.1f}%  ${format_price(opp['spread']):>5.2f}"
            )
        
        elif opp['type'] == 'cross_exchange_spot':
            ex1 = f"{opp['exchange1'].upper():6}"
            ex2 = f"{opp['exchange2'].upper():6}"
            route = f"{ex1}→ {ex2}"
            result.append(
                f"S         {route:<15} {opp['percentage']:>5.1f}%  ${format_price(opp['spread']):>5.2f}"
            )
        
        elif opp['type'] == 'cross_exchange_futures':
            ex1 = f"{opp['exchange1'].upper():6}"
            ex2 = f"{opp['exchange2'].upper():6}"
            route = f"{ex1}→ {ex2}"
            result.append(
                f"F         {route:<15} {opp['percentage']:>5.1f}%  ${format_price(opp['spread']):>5.2f}"
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
                f"CROSS {cross_type} {route:<15} {opp['percentage']:>5.1f}%  ${format_price(opp['spread']):>5.2f}"
            )
        
        else:  # same_exchange_spot_futures
            route = f"{opp['exchange'].upper():15}"
            result.append(
                f"S/F       {route:<15} {opp['percentage']:>5.1f}%  ${format_price(opp['spread']):>5.2f}"
            )
    
    result.append("</pre>")
    return "\n".join(result)

async def monitor_prices(chat_id: int, query: str, bot, min_arbitrage_percentage: float = 0.1, network: str = None, pool_address: str = None, query_id: str = None):
    """Background task to monitor prices and detect arbitrage opportunities"""
    try:
        # Get the filter preference for this chat_id
        filter_mode = user_filter_preferences.get(chat_id, "all")  # Default to showing all
        logger.info(f"Starting monitoring for {query} (ID: {query_id}) with filter mode: {filter_mode} (raw value from dict)")
        
        # Validate the filter mode
        if filter_mode not in ["cex_only", "cex_dex_only", "future", "all"]:
            logger.warning(f"Invalid filter mode: {filter_mode}. Defaulting to 'all'")
            filter_mode = "all"
            
        logger.info(f"Using filter mode: {filter_mode} for {query} (ID: {query_id})")
        
        price_monitor = ArbitragePriceMonitor(query, bot, min_arbitrage_percentage, filter_mode, network, pool_address, query_id)
        await price_monitor.start_monitoring()
    except asyncio.CancelledError:
        logger.info(f"Monitoring stopped for {query} (ID: {query_id})")
    except Exception as e:
        logger.error(f"Error in price monitoring: {str(e)}")
        alert_group_id = int(os.getenv("ALERT_GROUP_ID"))
        topic_id = int(os.getenv("TOPIC_ID", "1"))
        await bot.send_message(alert_group_id, f"❌ Error in price monitoring for {query} (ID: {query_id}): {str(e)}", message_thread_id=topic_id, parse_mode="HTML", disable_web_page_preview=True)

class ArbitragePriceMonitor:
    """Class for monitoring prices and detecting arbitrage opportunities"""
    
    def __init__(self, query: str, bot, min_arbitrage_percentage: float = 0.1, filter_mode: str = "all", 
                 network: str = None, pool_address: str = None, query_id: str = None):
        self.query = query
        self.bot = bot
        self.min_arbitrage_percentage = min_arbitrage_percentage
        self.query_id = query_id or generate_query_id()  # Use provided ID or generate a new one
        # Make sure filter_mode is either "cex_only", "cex_dex_only", "future" or "all"
        if filter_mode not in ["cex_only", "cex_dex_only", "future", "all"]:
            logger.warning(f"Invalid filter_mode provided: {filter_mode}, defaulting to 'all'")
            filter_mode = "all"
        self.filter_mode = filter_mode  # "all", "cex_only", "cex_dex_only", or "future"
        self.network = network  # Network for DEX operations (e.g., 'Ethereum', 'BSC')
        self.pool_address = pool_address  # Pool address for DEX operations
        logger.info(f"ArbitragePriceMonitor initialized with filter_mode: {self.filter_mode}")
        if self.network and self.pool_address:
            logger.info(f"DEX parameters provided - Network: {self.network}, Pool Address: {self.pool_address}")
        self.last_opportunities = set()
        self.alert_group_id = int(os.getenv("ALERT_GROUP_ID"))
        self.topic_id = int(os.getenv("TOPIC_ID", "1"))
        self.cex_exchanges = ["bitget", "gate", "mexc", "bybit", "bingx", "binance"]
        self.chain_mapping = {
            'BASEEVM': 'BASEEVM',
            'ETH': 'ether',
            'BSC': 'bsc',
            'MATIC': 'polygon',
            'ARBEVM': 'arbitrum',
            'OPTIMISM': 'optimism',
            'AVAX': 'avalanche'
        }
    
    async def start_monitoring(self):
        """Start the monitoring loop"""
        while True:
            prices = {}
            has_any_price = False
            
            # Collect prices from DEX and CEX
            dex_prices = await self._fetch_dex_prices()
            prices.update(dex_prices)
            
            cex_prices = await self._fetch_cex_prices()
            prices.update(cex_prices)
            
            # Determine if we have any prices
            has_any_price = any(
                prices[exchange].get('spot') is not None or prices[exchange].get('futures') is not None
                for exchange in prices
            )
            
            # Format and send price message
            # price_message = await self._format_price_message(prices)
            # await self._send_message(price_message)
            
            # Process arbitrage opportunities if we have prices
            if has_any_price:
                await self._process_arbitrage_opportunities(prices)
            
            # Wait before next check
            await asyncio.sleep(10)
    
    async def _fetch_dex_prices(self) -> Dict[str, Dict[str, Any]]:
        """Fetch prices from DEX platforms"""
        dex_prices = {}
        try:
            logger.info(f"Starting DEX price check for {self.query}")
            
            # If pool address and network are explicitly provided, use them directly
            if self.network and self.pool_address:
                logger.info(f"Using provided network and pool address: {self.network}, {self.pool_address}")
                
                # Initialize DexTools API
                dex_tools = DexTools(api_key=os.getenv("DEXTOOLS_API_KEY"))
                logger.info(f"Initialized DexTools with API key")
                
                dex_price = await self._get_pool_price(dex_tools, self.network, self.pool_address)
                if dex_price:
                    dex_prices[self.network] = {
                        'spot': dex_price,
                        'futures': None,
                        'is_dex': True
                    }
                return dex_prices
            
            # Otherwise, use the traditional chain lookup method (fallback for compatibility)
            chains = await exchange_service.get_currency_chains("gate", self.query)
            logger.info(f"Retrieved chains for {self.query}: {chains}")
            
            if not chains:
                logger.info(f"No chains found for {self.query}")
                return dex_prices
                
            # Initialize DexTools API
            dex_tools = DexTools(api_key=os.getenv("DEXTOOLS_API_KEY"))
            logger.info(f"Initialized DexTools with API key")
            
            # Process each chain
            for chain_name, contract_address in chains:
                if not chain_name or not contract_address:
                    logger.warning(f"Invalid chain data: {chain_name}, {contract_address}")
                    continue
                
                dex_price = await self._get_token_price(dex_tools, chain_name, contract_address)
                if dex_price:
                    dex_prices[chain_name] = {
                        'spot': dex_price,
                        'futures': None,
                        'is_dex': True
                    }
        except Exception as e:
            logger.error(f"Error in DEX price retrieval process: {str(e)}", exc_info=True)
        
        return dex_prices
    
    async def _get_token_price(self, dex_tools, chain_name: str, contract_address: str) -> Optional[float]:
        """Get token price for a specific DEX chain (legacy method)"""
        try:
            # Convert chain name to DexTools format
            dextools_chain = self.chain_mapping.get(chain_name.upper())
            if not dextools_chain:
                logger.warning(f"Unsupported chain {chain_name} for DexTools")
                return None
                
            logger.info(f"Processing chain {chain_name} ({dextools_chain}) for token {self.query}")
            logger.debug(f"Contract address for {chain_name}: {contract_address}")
            
            logger.info(f"Requesting DexTools token price for {self.query} on {dextools_chain}")
            price = dex_tools.get_token_price(dextools_chain, contract_address)
            
            if price is not None:
                logger.info(f"Successfully got token price for {self.query} on {dextools_chain}: ${format_price(price)}")
                return price
            else:
                logger.warning(f"No token price returned from DexTools for {self.query} on {dextools_chain}")
                return None
        except Exception as e:
            logger.error(f"Error getting token price for chain {chain_name}: {str(e)}", exc_info=True)
            return None
            
    async def _get_pool_price(self, dex_tools, chain_name: str, pool_address: str) -> Optional[float]:
        """Get pool price for a specific DEX chain"""
        try:
            # Convert chain name to DexTools format
            dextools_chain = self.chain_mapping.get(chain_name.upper())
            if not dextools_chain:
                # Try to use the chain name directly if it's not in our mapping
                dextools_chain = chain_name.lower()
                logger.info(f"Using chain name directly for DexTools: {dextools_chain}")
                
            logger.info(f"Processing chain {chain_name} ({dextools_chain}) for pool for {self.query}")
            logger.debug(f"Pool address for {chain_name}: {pool_address}")
            
            logger.info(f"Requesting DexTools pool price for {self.query} on {dextools_chain}")
            price = dex_tools.get_pool_price(dextools_chain, pool_address)
            
            if price is not None:
                logger.info(f"Successfully got pool price for {self.query} on {dextools_chain}: ${format_price(price)}")
                return price
            else:
                logger.warning(f"No pool price returned from DexTools for {self.query} on {dextools_chain}")
                return None
        except Exception as e:
            logger.error(f"Error getting pool price for chain {chain_name}: {str(e)}", exc_info=True)
            return None
    
    async def _fetch_cex_prices(self) -> Dict[str, Dict[str, Any]]:
        """Fetch prices from centralized exchanges"""
        cex_prices = {}
        
        for exchange in self.cex_exchanges:
            cex_prices[exchange] = {
                'spot': None,
                'futures': None,
                'is_dex': False
            }
            
            # Get spot price
            try:
                spot_price = await exchange_service.get_average_price(
                    exchange, self.query, market_type="spot"
                )
                if spot_price:
                    cex_prices[exchange]['spot'] = spot_price
            except Exception as e:
                logger.error(f"Error getting spot price for {exchange}: {str(e)}")
            
            # Get futures price
            try:
                futures_price = await exchange_service.get_average_price(
                    exchange, self.query, market_type="futures"
                )
                if futures_price:
                    cex_prices[exchange]['futures'] = futures_price
            except Exception as e:
                logger.error(f"Error getting futures price for {exchange}: {str(e)}")
        
        return cex_prices
    
    async def _format_price_message(self, prices: Dict[str, Dict[str, Any]]) -> str:
        """Format the price message to display to users"""
        token_symbol = self.query.upper()
        price_message = f"📊 Current prices for {token_symbol}:\n\n"
        
        # Add DEX prices
        for exchange, price_data in prices.items():
            if price_data.get('is_dex', False) and price_data.get('spot'):
                dex_url = self._get_dextools_url(exchange, self.pool_address)
                
                if dex_url:
                    price_message += f"DEX (<a href='{dex_url}'>{exchange.upper()}</a>): ${format_price(price_data['spot'])}\n\n"
                else:
                    price_message += f"DEX ({exchange.upper()}): ${format_price(price_data['spot'])}\n\n"
        
        # Add CEX prices
        for exchange in self.cex_exchanges:
            if exchange in prices:
                spot_url = self._get_exchange_url(exchange, 'spot', token_symbol)
                futures_url = self._get_exchange_url(exchange, 'futures', token_symbol)
                
                # Start with the exchange name
                price_message += f"<b>{exchange.upper()}</b>\n"
                
                # Get token availability status for Gate.io
                if exchange == "gate":
                    try:
                        # Get token availability from Gate.io
                        gate_client = exchange_service._get_exchange_client("gate")
                        availability = await gate_client.check_token_availability(self.query)
                        
                        # Create status indicators for deposit and withdrawal
                        deposit_status = "✅" if availability.get("deposit", False) else "❌"
                        withdrawal_status = "✅" if availability.get("withdrawal", False) else "❌"
                        
                        price_message += f"<b>Status:</b> Deposit: {deposit_status} | Withdrawal: {withdrawal_status}\n"
                    except Exception as e:
                        logger.error(f"Error getting token availability for {self.query} on Gate.io: {str(e)}")
                
                # Get token availability status for Binance
                elif exchange == "binance":
                    try:
                        # Get token availability from Binance
                        binance_client = exchange_service._get_exchange_client("binance")
                        availability = await binance_client.check_token_availability(self.query)
                        
                        # Create status indicators for deposit and withdrawal
                        deposit_status = "✅" if availability.get("deposit", False) else "❌"
                        withdrawal_status = "✅" if availability.get("withdrawal", False) else "❌"
                        
                        price_message += f"<b>Status:</b> Deposit: {deposit_status} | Withdrawal: {withdrawal_status}\n"
                        
                        # Try to get network information if available
                        try:
                            networks = await binance_client.get_currency_chains(self.query)
                            if networks:
                                price_message += "<b>Networks:</b> "
                                network_names = [network_name for network_name, _ in networks]
                                price_message += ", ".join(network_names) + "\n"
                        except Exception as e:
                            logger.error(f"Error getting network information for {self.query} on Binance: {str(e)}")
                            
                    except Exception as e:
                        logger.error(f"Error getting token availability for {self.query} on Binance: {str(e)}")
                
                # Get token availability status for Bitget
                elif exchange == "bitget":
                    try:
                        # Get token availability from Bitget
                        bitget_client = exchange_service._get_exchange_client("bitget")
                        availability = await bitget_client.check_token_availability(self.query)
                        
                        # Create status indicators for deposit and withdrawal
                        deposit_status = "✅" if availability.get("deposit", False) else "❌"
                        withdrawal_status = "✅" if availability.get("withdrawal", False) else "❌"
                        
                        price_message += f"<b>Status:</b> Deposit: {deposit_status} | Withdrawal: {withdrawal_status}\n"
                        
                        # Try to get network information if available
                        try:
                            networks = await bitget_client.get_currency_chains(self.query)
                            if networks:
                                price_message += "<b>Networks:</b> "
                                network_names = [network_name for network_name, _ in networks]
                                price_message += ", ".join(network_names) + "\n"
                        except Exception as e:
                            logger.error(f"Error getting network information for {self.query} on Bitget: {str(e)}")
                            
                    except Exception as e:
                        logger.error(f"Error getting token availability for {self.query} on Bitget: {str(e)}")
                
                # Get token availability status for MEXC
                elif exchange == "mexc":
                    try:
                        # Get token availability from MEXC
                        mexc_client = exchange_service._get_exchange_client("mexc")
                        availability = await mexc_client.check_token_availability(self.query)
                        
                        # Create status indicators for deposit and withdrawal
                        deposit_status = "✅" if availability.get("deposit", False) else "❌"
                        withdrawal_status = "✅" if availability.get("withdrawal", False) else "❌"
                        
                        price_message += f"<b>Status:</b> Deposit: {deposit_status} | Withdrawal: {withdrawal_status}\n"
                        
                        # Try to get network information if available
                        try:
                            networks = await mexc_client.get_currency_chains(self.query)
                            if networks:
                                price_message += "<b>Networks:</b> "
                                network_names = [network_name for network_name, _ in networks]
                                price_message += ", ".join(network_names) + "\n"
                        except Exception as e:
                            logger.error(f"Error getting network information for {self.query} on MEXC: {str(e)}")
                            
                    except Exception as e:
                        logger.error(f"Error getting token availability for {self.query} on MEXC: {str(e)}")
                
                # Get token availability status for ByBit
                elif exchange == "bybit":
                    try:
                        # Get token availability from ByBit
                        bybit_client = exchange_service._get_exchange_client("bybit")
                        availability = await bybit_client.check_token_availability(self.query)
                        
                        # Create status indicators for deposit and withdrawal
                        deposit_status = "✅" if availability.get("deposit", False) else "❌"
                        withdrawal_status = "✅" if availability.get("withdrawal", False) else "❌"
                        
                        price_message += f"<b>Status:</b> Deposit: {deposit_status} | Withdrawal: {withdrawal_status}\n"
                        
                        # Try to get network information if available
                        try:
                            networks = await bybit_client.get_currency_chains(self.query)
                            if networks:
                                price_message += "<b>Networks:</b> "
                                network_names = [network_name for network_name, _ in networks]
                                price_message += ", ".join(network_names) + "\n"
                        except Exception as e:
                            logger.error(f"Error getting network information for {self.query} on ByBit: {str(e)}")
                            
                    except Exception as e:
                        logger.error(f"Error getting token availability for {self.query} on ByBit: {str(e)}")
                
                # Get token availability status for BingX
                elif exchange == "bingx":
                    try:
                        # Get token availability from BingX
                        bingx_client = exchange_service._get_exchange_client("bingx")
                        availability = await bingx_client.check_token_availability(self.query)
                        
                        # Create status indicators for deposit and withdrawal
                        deposit_status = "✅" if availability.get("deposit", False) else "❌"
                        withdrawal_status = "✅" if availability.get("withdrawal", False) else "❌"
                        
                        price_message += f"<b>Status:</b> Deposit: {deposit_status} | Withdrawal: {withdrawal_status}\n"
                        
                        # Try to get network information if available
                        try:
                            networks = await bingx_client.get_currency_chains(self.query)
                            if networks:
                                price_message += "<b>Networks:</b> "
                                network_names = [network_name for network_name, _ in networks]
                                price_message += ", ".join(network_names) + "\n"
                        except Exception as e:
                            logger.error(f"Error getting network information for {self.query} on BingX: {str(e)}")
                            
                    except Exception as e:
                        logger.error(f"Error getting token availability for {self.query} on BingX: {str(e)}")
                
                # Add spot price
                if prices[exchange].get('spot'):
                    price_message += f"<a href='{spot_url}'>Spot</a>: ${format_price(prices[exchange]['spot'])}\n"
                else:
                    price_message += f"Spot: Not available\n"
                
                # Add futures price
                if prices[exchange].get('futures'):
                    price_message += f"<a href='{futures_url}'>Futures</a>: ${format_price(prices[exchange]['futures'])}\n"
                else:
                    price_message += f"Futures: Not available\n"
                
                price_message += "\n"  # Add spacing between exchanges
        
        return price_message
    
    async def _process_arbitrage_opportunities(self, prices: Dict[str, Dict[str, Any]]):
        """Process and alert about arbitrage opportunities"""
        # Calculate arbitrage opportunities with the filter mode
        opportunities = await calculate_arbitrage(prices, self.min_arbitrage_percentage, self.filter_mode)
        
        # Filter significant opportunities (>= MIN_ARBITRAGE_PERCENTAGE) and exclude same-exchange opportunities
        significant_opportunities = [
            opp for opp in opportunities
            if opp['percentage'] >= self.min_arbitrage_percentage and opp['type'] != 'same_exchange_spot_futures'
        ]
        
        # Generate unique IDs for each opportunity
        current_opps = self._generate_opportunity_ids(significant_opportunities)
        
        # Report new opportunities
        new_opps = current_opps - self.last_opportunities
        if new_opps:
            await self._send_new_opportunity_alerts(significant_opportunities, new_opps)
        
        # Update last opportunities
        self.last_opportunities = current_opps
    
    def _generate_opportunity_ids(self, opportunities: List[Dict]) -> Set[str]:
        """Generate unique IDs for arbitrage opportunities"""
        current_opps = set()
        
        for opp in opportunities:
            try:
                # Skip same-exchange opportunities
                if opp['type'] == 'same_exchange_spot_futures':
                    continue
                    
                opp_id = f"{opp['type']}_{opp['percentage']:.2f}"
                
                # Add exchange-specific information to the ID based on opportunity type
                if opp['type'] in ['dex_to_cex_spot', 'dex_to_cex_futures']:
                    opp_id += f"_{opp['dex']}_{opp['cex']}"
                elif opp['type'] in ['cex_to_dex_spot', 'cex_to_dex_futures']:
                    opp_id += f"_{opp['cex']}_{opp['dex']}"
                elif opp['type'] in ['cross_exchange_spot', 'cross_exchange_futures']:
                    opp_id += f"_{opp['exchange1']}_{opp['exchange2']}"
                elif opp['type'] == 'cross_exchange_spot_futures':
                    opp_id += f"_{opp['spot_exchange']}_{opp['futures_exchange']}"
                else:
                    logger.warning(f"Unknown opportunity type: {opp['type']}")
                    continue
                    
                current_opps.add(opp_id)
                logger.debug(f"Added opportunity ID: {opp_id}")
                
            except KeyError as ke:
                logger.error(f"Missing key in opportunity dict: {ke}", exc_info=True)
                logger.debug(f"Opportunity data: {opp}")
            except Exception as e:
                logger.error(f"Error processing opportunity: {str(e)}", exc_info=True)
                logger.debug(f"Opportunity data: {opp}")
                
        return current_opps
    
    async def _send_new_opportunity_alerts(self, opportunities: List[Dict], new_opps: Set[str]):
        """Send alerts for new arbitrage opportunities"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        for opp in opportunities:
            try:
                # Generate the opportunity ID in the same way as in _generate_opportunity_ids
                opp_id = self._get_opportunity_id(opp)
                
                # Check if this opportunity is new
                if opp_id in new_opps:
                    alert_msg = self._format_opportunity_alert(opp, timestamp)
                    if alert_msg:
                        await self._send_message(alert_msg)
                        
            except Exception as e:
                logger.error(f"Error processing opportunity alert: {str(e)}", exc_info=True)
                logger.debug(f"Opportunity data: {opp}")
    
    def _get_opportunity_id(self, opp: Dict) -> str:
        """Get a unique ID for an opportunity - must match the logic in _generate_opportunity_ids"""
        # Skip same-exchange opportunities
        if opp['type'] == 'same_exchange_spot_futures':
            return ""
            
        opp_id = f"{opp['type']}_{opp['percentage']:.2f}"
        
        if opp['type'] in ['dex_to_cex_spot', 'dex_to_cex_futures']:
            opp_id += f"_{opp['dex']}_{opp['cex']}"
        elif opp['type'] in ['cex_to_dex_spot', 'cex_to_dex_futures']:
            opp_id += f"_{opp['cex']}_{opp['dex']}"
        elif opp['type'] in ['cross_exchange_spot', 'cross_exchange_futures']:
            opp_id += f"_{opp['exchange1']}_{opp['exchange2']}"
        elif opp['type'] == 'cross_exchange_spot_futures':
            opp_id += f"_{opp['spot_exchange']}_{opp['futures_exchange']}"
            
        return opp_id
    
    def _get_exchange_url(self, exchange: str, market_type: str, token_symbol: str) -> str:
        """
        Generate a URL for the given exchange, market type, and token symbol
        
        Args:
            exchange: Exchange name (gate, bitget, bybit, mexc, bingx, binance)
            market_type: 'spot' or 'futures'
            token_symbol: Token symbol (e.g. BTC)
            
        Returns:
            URL for the exchange
        """
        exchange = exchange.lower()
        
        if market_type == 'spot':
            if exchange == 'gate':
                return f"https://www.gate.io/ru/trade/{token_symbol}_USDT"
            elif exchange == 'bitget':
                return f"https://www.bitget.com/ru/spot/{token_symbol}USDC"
            elif exchange == 'bybit':
                return f"https://www.bybit.com/ru-RU/trade/spot/{token_symbol}/USDT"
            elif exchange == 'mexc':
                return f"https://www.mexc.com/ru-RU/exchange/{token_symbol}_USDT?_from=search_spot_trade"
            elif exchange == 'bingx':
                return f"https://bingx.com/en/spot/{token_symbol}USDT/"
            elif exchange == 'binance':
                # Use Binance specific URL format for spot markets
                return f"https://www.binance.com/en/trade/{token_symbol}_USDT?type=spot"
        
        elif market_type == 'futures':
            if exchange == 'gate':
                return f"https://www.gate.io/ru/futures/USDT/{token_symbol}_USDT"
            elif exchange == 'bitget':
                return f"https://www.bitget.com/ru/futures/usdt/{token_symbol}USDT"
            elif exchange == 'bybit':
                return f"https://www.bybit.com/trade/usdt/{token_symbol}USDT"
            elif exchange == 'mexc':
                return f"https://futures.mexc.com/ru-RU/exchange/{token_symbol}_USDT?type=linear_swap"
            elif exchange == 'bingx':
                return f"https://bingx.com/en/perpetual/{token_symbol}-USDT/"
            elif exchange == 'binance':
                # Use Binance specific URL format for futures markets
                return f"https://www.binance.com/en/futures/{token_symbol}USDT"
        
        # Default fallback - return empty string if no match
        return ""
    
    def _get_dextools_url(self, dex_name: str, pool_address: str = None) -> str:
        """
        Generate a DexTools URL for the given DEX and pool address
        
        Args:
            dex_name: DEX name
            pool_address: Pool address (if available)
            
        Returns:
            DexTools URL
        """
        if not pool_address:
            return ""
            
        # Default to BASE chain for now, but this could be enhanced to support multiple chains
        return f"https://www.dextools.io/app/en/{dex_name}/pair-explorer/{pool_address}"
    
    def _format_opportunity_alert(self, opp: Dict, timestamp: str) -> Optional[str]:
        """Format an alert message for a new arbitrage opportunity"""
        try:
            # Skip same-exchange opportunities
            if opp['type'] == 'same_exchange_spot_futures':
                logger.info(f"Skipping same-exchange opportunity for {opp['exchange']}")
                return None
                
            alert_msg = f"🚨 New Arbitrage Opportunity at {timestamp}!\n\n"
            
            # Extract token symbol from the query
            token_symbol = self.query.upper()
            
            # DEX to CEX Spot
            if opp['type'] == 'dex_to_cex_spot' and all(k in opp for k in ['dex', 'cex', 'dex_price', 'cex_price', 'percentage']):
                cex_url = self._get_exchange_url(opp['cex'], 'spot', token_symbol)
                dex_url = self._get_dextools_url(opp['dex'], self.pool_address)
                
                dex_name = f"{opp['dex'].upper()} DEX"
                if dex_url:
                    dex_name = f"<a href='{dex_url}'>{dex_name}</a>"
                
                alert_msg += (
                    f"💰 <b>Arbitrage Opportunity</b>\n"
                    f"Type: DEX -> CEX Spot\n"
                    f"Buy on: {dex_name} at ${format_price(opp['dex_price'])}\n"
                    f"Sell on: <a href='{cex_url}'>{opp['cex'].upper()}</a> at ${format_price(opp['cex_price'])}\n"
                    f"Difference: {opp['percentage']:.2f}%\n"
                    f"Profit potential: ${format_price(opp['spread'])}\n\n"
                )
            
            # CEX to DEX Spot
            elif opp['type'] == 'cex_to_dex_spot' and all(k in opp for k in ['dex', 'cex', 'dex_price', 'cex_price', 'percentage']):
                cex_url = self._get_exchange_url(opp['cex'], 'spot', token_symbol)
                dex_url = self._get_dextools_url(opp['dex'], self.pool_address)
                
                dex_name = f"{opp['dex'].upper()} DEX"
                if dex_url:
                    dex_name = f"<a href='{dex_url}'>{dex_name}</a>"
                
                alert_msg += (
                    f"💰 <b>Arbitrage Opportunity</b>\n"
                    f"Type: CEX Spot -> DEX\n"
                    f"Buy on: <a href='{cex_url}'>{opp['cex'].upper()}</a> at ${format_price(opp['cex_price'])}\n"
                    f"Sell on: {dex_name} at ${format_price(opp['dex_price'])}\n"
                    f"Difference: {opp['percentage']:.2f}%\n"
                    f"Profit potential: ${format_price(opp['spread'])}\n\n"
                )
            
            # DEX to CEX Futures
            elif opp['type'] == 'dex_to_cex_futures' and all(k in opp for k in ['dex', 'cex', 'dex_price', 'cex_price', 'percentage']):
                cex_url = self._get_exchange_url(opp['cex'], 'futures', token_symbol)
                dex_url = self._get_dextools_url(opp['dex'], self.pool_address)
                
                dex_name = f"{opp['dex'].upper()} DEX"
                if dex_url:
                    dex_name = f"<a href='{dex_url}'>{dex_name}</a>"
                
                alert_msg += (
                    f"💰 <b>Arbitrage Opportunity</b>\n"
                    f"Type: DEX -> CEX Futures\n"
                    f"Buy on: {dex_name} at ${format_price(opp['dex_price'])}\n"
                    f"Sell on: <a href='{cex_url}'>{opp['cex'].upper()}</a> Futures at ${format_price(opp['cex_price'])}\n"
                    f"Difference: {opp['percentage']:.2f}%\n"
                    f"Profit potential: ${format_price(opp['spread'])}\n\n"
                )
            
            # CEX to DEX Futures
            elif opp['type'] == 'cex_to_dex_futures' and all(k in opp for k in ['dex', 'cex', 'dex_price', 'cex_price', 'percentage']):
                cex_url = self._get_exchange_url(opp['cex'], 'futures', token_symbol)
                dex_url = self._get_dextools_url(opp['dex'], self.pool_address)
                
                dex_name = f"{opp['dex'].upper()} DEX"
                if dex_url:
                    dex_name = f"<a href='{dex_url}'>{dex_name}</a>"
                
                alert_msg += (
                    f"💰 <b>Arbitrage Opportunity</b>\n"
                    f"Type: CEX Futures -> DEX\n"
                    f"Buy on: <a href='{cex_url}'>{opp['cex'].upper()}</a> Futures at ${format_price(opp['cex_price'])}\n"
                    f"Sell on: {dex_name} at ${format_price(opp['dex_price'])}\n"
                    f"Difference: {opp['percentage']:.2f}%\n"
                    f"Profit potential: ${format_price(opp['spread'])}\n\n"
                )
            
            # CEX to CEX Spot
            elif opp['type'] == 'cross_exchange_spot' and all(k in opp for k in ['exchange1', 'exchange2', 'price1', 'price2', 'percentage']):
                exchange1_url = self._get_exchange_url(opp['exchange1'], 'spot', token_symbol)
                exchange2_url = self._get_exchange_url(opp['exchange2'], 'spot', token_symbol)
                alert_msg += (
                    f"💰 <b>Arbitrage Opportunity</b>\n"
                    f"Type: CEX Spot -> CEX Spot\n"
                    f"Buy on: <a href='{exchange1_url}'>{opp['exchange1'].upper()}</a> at ${format_price(opp['price1'])}\n"
                    f"Sell on: <a href='{exchange2_url}'>{opp['exchange2'].upper()}</a> at ${format_price(opp['price2'])}\n"
                    f"Difference: {opp['percentage']:.2f}%\n"
                    f"Profit potential: ${format_price(opp['spread'])}\n\n"
                )
            
            # CEX to CEX Futures
            elif opp['type'] == 'cross_exchange_futures' and all(k in opp for k in ['exchange1', 'exchange2', 'price1', 'price2', 'percentage']):
                exchange1_url = self._get_exchange_url(opp['exchange1'], 'futures', token_symbol)
                exchange2_url = self._get_exchange_url(opp['exchange2'], 'futures', token_symbol)
                alert_msg += (
                    f"💰 <b>Arbitrage Opportunity</b>\n"
                    f"Type: CEX Futures -> CEX Futures\n"
                    f"Buy on: <a href='{exchange1_url}'>{opp['exchange1'].upper()}</a> at ${format_price(opp['price1'])}\n"
                    f"Sell on: <a href='{exchange2_url}'>{opp['exchange2'].upper()}</a> at ${format_price(opp['price2'])}\n"
                    f"Difference: {opp['percentage']:.2f}%\n"
                    f"Profit potential: ${format_price(opp['spread'])}\n\n"
                )
            
            # CEX Spot to CEX Futures (Cross-exchange)
            elif opp['type'] == 'cross_exchange_spot_futures' and all(k in opp for k in ['spot_exchange', 'futures_exchange', 'spot_price', 'futures_price', 'percentage']):
                spot_url = self._get_exchange_url(opp['spot_exchange'], 'spot', token_symbol)
                futures_url = self._get_exchange_url(opp['futures_exchange'], 'futures', token_symbol)
                alert_msg += (
                    f"💰 <b>Arbitrage Opportunity</b>\n"
                    f"Type: CEX Spot -> CEX Futures\n"
                    f"Buy on: <a href='{spot_url}'>{opp['spot_exchange'].upper()}</a> (Spot) at ${format_price(opp['spot_price'])}\n"
                    f"Sell on: <a href='{futures_url}'>{opp['futures_exchange'].upper()}</a> (Futures) at ${format_price(opp['futures_price'])}\n"
                    f"Difference: {opp['percentage']:.2f}%\n"
                    f"Profit potential: ${format_price(opp['spread'])}\n\n"
                )
            else:
                logger.warning(f"Invalid or incomplete opportunity data: {opp}")
                return None
                
            return alert_msg
                
        except Exception as e:
            logger.error(f"Error formatting alert message: {str(e)}", exc_info=True)
            logger.debug(f"Opportunity data: {opp}")
            return None
    
    async def _send_message(self, message: str):
        """Send a message to the alert group"""
        if message and len(message.strip()) > 0:
            # Add query ID as a small reference at the end of the message
            prefixed_message = f"{message}\n<i>Monitor ID: {self.query_id[:8]}</i>"
            
            await self.bot.send_message(
                self.alert_group_id, 
                prefixed_message, 
                message_thread_id=self.topic_id,
                parse_mode="HTML",
                disable_web_page_preview=True
            )

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
    
    # Parse arguments: /stop [monitor_id]
    args = message.text.split()
    monitor_id = args[1] if len(args) > 1 else None
    
    if chat_id not in active_monitors or not active_monitors[chat_id]:
        await message.answer("❌ No active monitors to stop")
        return
        
    if monitor_id:
        # Stop specific monitor
        found = False
        for query_id, task in list(active_monitors[chat_id].items()):
            if query_id.startswith(monitor_id):
                task.cancel()
                del active_monitors[chat_id][query_id]
                found = True
                # Send confirmation to both alert group and admin
                await bot.send_message(
                    alert_group_id, 
                    f"✅ Monitoring stopped for ID: {query_id[:8]}", 
                    message_thread_id=topic_id, 
                    parse_mode="HTML", 
                    disable_web_page_preview=True
                )
                await message.answer(f"✅ Stopped monitoring for ID: {query_id[:8]}")
                break
        
        if not found:
            await message.answer(f"❌ No monitor found with ID: {monitor_id}")
            
        # If no more monitors, clean up the dict
        if not active_monitors[chat_id]:
            del active_monitors[chat_id]
    else:
        # Stop all monitors
        for query_id, task in list(active_monitors[chat_id].items()):
            task.cancel()
        
        num_stopped = len(active_monitors[chat_id])
        del active_monitors[chat_id]
        
        # Send confirmation to both alert group and admin
        await bot.send_message(
            alert_group_id, 
            f"✅ All monitoring stopped ({num_stopped} monitors)", 
            message_thread_id=topic_id, 
            parse_mode="HTML", 
            disable_web_page_preview=True
        )
        await message.answer(f"✅ All monitoring stopped ({num_stopped} monitors)")

@router.message()
async def handle_search(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    alert_group_id = int(os.getenv("ALERT_GROUP_ID"))
    topic_id = int(os.getenv("TOPIC_ID", "1"))
    bot = message.bot
    
    logger.info(f"Received message from user ID: {user_id}, chat type: {message.chat.type}")
    
    # Check if user is admin and message is in private chat
    if not is_admin(user_id) or message.chat.type != "private":
        # Only respond in private chats
        if message.chat.type == "private":
            logger.info(f"User {user_id} is not an admin, rejecting command")
            await message.answer("❌ Only admins can specify coins to monitor")
        return
    
    query = message.text.strip().upper()
    
    if not query:
        await message.answer("Please send a valid coin name")
        return

    # Generate a unique ID for this monitoring request
    query_id = generate_query_id()
    
    # Initialize user_queries for this chat if not exists
    if chat_id not in user_queries:
        user_queries[chat_id] = {}
    
    # Store the query information
    user_queries[chat_id][query_id] = {
        'query': query, 
        'min_percentage': MIN_ARBITRAGE_PERCENTAGE, 
        'filter_mode': "all",
        'query_id': query_id
    }
    
    # Ask for filter mode
    logger.info(f"Showing filter keyboard to user {user_id} for coin {query}")
    await message.answer(
        f"Please select which opportunities to monitor for {query}:",
        reply_markup=get_filter_mode_keyboard()
    )
    return

@router.message(lambda message: message.chat.id in user_queries)
async def handle_min_percentage(message: Message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    alert_group_id = int(os.getenv("ALERT_GROUP_ID"))
    topic_id = int(os.getenv("TOPIC_ID", "1"))
    bot = message.bot
    
    # Get the stored query
    query_id = next(iter(user_queries[chat_id]))
    query_info = user_queries[chat_id].pop(query_id)
    
    # Get the user's filter preference (default to "all" if not set)
    filter_mode = query_info.get('filter_mode', "all")
    
    # Parse the minimum percentage
    try:
        min_percentage = float(message.text.strip())
        if min_percentage <= 0:
            await message.answer("Minimum percentage must be greater than 0. Please try again.")
            return
    except ValueError:
        await message.answer("Please enter a valid number (e.g., 0.5 for 0.5%)")
        return
    
    try:
        # Cancel existing monitoring task if any
        if chat_id in active_monitors:
            for query_id, task in active_monitors[chat_id].items():
                task.cancel()
            del active_monitors[chat_id]
        
        # Get filter mode text for display
        if filter_mode == "cex_only":
            mode_text = "CEX-CEX Only"
        elif filter_mode == "cex_dex_only":
            mode_text = "CEX-DEX Only"
        elif filter_mode == "future":
            mode_text = "Future Only"
        else:
            mode_text = "All Types"
        
        # Send initial message to alert group
        await bot.send_message(
            chat_id=alert_group_id,
            text=f"🔍 Starting price monitoring for {query_info['query']} with minimum arbitrage of {min_percentage}%...\nFilter mode: {mode_text}",
            message_thread_id=topic_id,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        # Start new monitoring task with the target chat ID, bot instance, minimum percentage, and filter mode
        task = asyncio.create_task(monitor_prices(chat_id, query_info['query'], bot, min_percentage, query_info.get('network'), query_info.get('pool_address'), query_id))
        active_monitors[chat_id] = {query_id: task}
        
        # Send confirmation to both alert group and admin
        await bot.send_message(
            chat_id=alert_group_id,
            text=f"✅ Monitoring started for {query_info['query']}!\n\n"
                 f"Filter mode: {mode_text}\n"
                 f"I will notify you when there are arbitrage opportunities with >{min_percentage}% difference.\n"
                 "Use /stop command to stop monitoring.",
            message_thread_id=topic_id,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        await message.answer(f"✅ Started monitoring {query_info['query']} with minimum arbitrage set to {min_percentage}%\nFilter mode: {mode_text}")
    except Exception as e:
        await message.answer(f"❌ Error starting monitoring: {str(e)}")

def get_filter_mode_keyboard() -> InlineKeyboardMarkup:
    """Create a keyboard for selecting filter mode"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="CEX-CEX Only",
        callback_data="filter_cex_only"
    )
    
    builder.button(
        text="ONLY CEX-DEX",
        callback_data="filter_cex_dex_only"
    )
    
    builder.button(
        text="DEX + CEX (ONLY FUTURE)",
        callback_data="filter_future"
    )
    
    builder.button(
        text="CEX-CEX + DEX",
        callback_data="filter_all"
    )
    
    builder.adjust(1)
    return builder.as_markup()

@router.callback_query(F.data.startswith("filter_"))
async def handle_filter_mode_callback(callback: CallbackQuery):
    """Handle filter mode selection"""
    filter_mode = callback.data.split("_")[1]
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    alert_group_id = int(os.getenv("ALERT_GROUP_ID"))
    topic_id = int(os.getenv("TOPIC_ID", "0"))  # Get topic ID from env
    bot = callback.bot
    
    # Check if user is admin
    if not is_admin(user_id):
        await callback.answer("❌ Only admins can start monitoring")
        return
    
    # Find the most recent query in user_queries for this chat
    if chat_id not in user_queries or not user_queries[chat_id]:
        await callback.answer("❌ No pending coin to monitor. Use /addcoin to add a coin.")
        return
    
    # Get the most recent query_id added (assuming it's the one the user is configuring)
    query_id = list(user_queries[chat_id].keys())[-1]
    query_info = user_queries[chat_id][query_id]
    
    # Update filter mode in user_queries
    query_info['filter_mode'] = filter_mode
    
    try:
        # Translate filter mode for display
        if filter_mode == "dex_only":
            mode_text = "DEX Only"
        elif filter_mode == "cex_only":
            mode_text = "CEX-CEX Only"
        elif filter_mode == "cex_dex_only":
            mode_text = "CEX-DEX Only"
        elif filter_mode == "future":
            mode_text = "Future Only"
        else:
            mode_text = "All Types"
        
        # Send initial message to alert group
        await bot.send_message(
            chat_id=alert_group_id,
            text=f"🔍 Starting price monitoring for {query_info['query']} (ID: {query_id[:8]}) with minimum arbitrage of {query_info['min_percentage']}%...\nFilter mode: {mode_text}",
            message_thread_id=topic_id,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        # Start new monitoring task
        task = asyncio.create_task(
            monitor_prices(
                chat_id, 
                query_info['query'], 
                bot, 
                query_info['min_percentage'], 
                query_info.get('network'), 
                query_info.get('pool_address'), 
                query_id
            )
        )
        
        # Initialize active_monitors for this chat if not exists
        if chat_id not in active_monitors:
            active_monitors[chat_id] = {}
            
        # Add the new monitor to the active monitors
        active_monitors[chat_id][query_id] = task
        
        # Send confirmation to both alert group and admin
        await bot.send_message(
            chat_id=alert_group_id,
            text=f"✅ Monitoring started for {query_info['query']} (ID: {query_id[:8]})!\n\n"
                 f"Filter mode: {mode_text}\n"
                 f"I will notify you when there are arbitrage opportunities with >{query_info['min_percentage']}% difference.\n"
                 "Use /stop command to stop monitoring.",
            message_thread_id=topic_id,
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        
        await callback.message.answer(f"✅ Started monitoring {query_info['query']} (ID: {query_id[:8]}) with minimum arbitrage set to {query_info['min_percentage']}%\nFilter mode: {mode_text}")
    except Exception as e:
        await callback.answer(f"❌ Error starting monitoring: {str(e)}")

@router.message(Command("addcoin"))
async def cmd_add_coin(message: Message):
    """Add a new coin to monitor"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Check if user is admin and message is in private chat
    if not is_admin(user_id) or message.chat.type != "private":
        # Only respond in private chats
        if message.chat.type == "private":
            await message.answer("❌ Only admins can add coins to monitor")
        return
    
    # Parse coin symbol from command
    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Please specify a coin to monitor.\nExample: /addcoin BTC")
        return
    
    # Get the coin symbol from the command
    query = args[1].strip().upper()
    
    if not query:
        await message.answer("Please send a valid coin name")
        return

    # Generate a unique ID for this monitoring request
    query_id = generate_query_id()
    
    # Initialize user_queries for this chat if not exists
    if chat_id not in user_queries:
        user_queries[chat_id] = {}
    
    # Store the query information
    user_queries[chat_id][query_id] = {
        'query': query, 
        'min_percentage': MIN_ARBITRAGE_PERCENTAGE, 
        'filter_mode': "all",
        'query_id': query_id
    }
    
    # Ask for filter mode
    logger.info(f"Showing filter keyboard to user {user_id} for coin {query}")
    await message.answer(
        f"Please select which opportunities to monitor for {query}:",
        reply_markup=get_filter_mode_keyboard()
    )
    return

@router.message(Command("listcoins"))
async def cmd_list_coins(message: Message):
    """List all coins being monitored"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Check if user is admin and message is in private chat
    if not is_admin(user_id) or message.chat.type != "private":
        # Only respond in private chats
        if message.chat.type == "private":
            await message.answer("❌ Only admins can view monitored coins")
        return
    
    if chat_id not in active_monitors or not active_monitors[chat_id]:
        await message.answer("⚠️ No coins are currently being monitored")
        return
    
    # Collect information about active monitors
    monitors_info = []
    coin_count = len(active_monitors[chat_id])
    
    for query_id, _ in active_monitors[chat_id].items():
        # Find the associated query information if available
        query_info = "Unknown"
        filter_mode = "all"
        min_percentage = MIN_ARBITRAGE_PERCENTAGE
        
        for chat_data in user_queries.values():
            if query_id in chat_data:
                query_info = chat_data[query_id].get('query', 'Unknown')
                filter_mode = chat_data[query_id].get('filter_mode', 'all')
                min_percentage = chat_data[query_id].get('min_percentage', MIN_ARBITRAGE_PERCENTAGE)
                break
        
        # Format the filter mode for display
        if filter_mode == "dex_only":
            mode_text = "DEX Only"
        elif filter_mode == "cex_only":
            mode_text = "CEX-CEX Only"
        elif filter_mode == "cex_dex_only":
            mode_text = "CEX-DEX Only"
        elif filter_mode == "future":
            mode_text = "Future Only"
        else:
            mode_text = "All Types"
        
        monitors_info.append(f"• {query_info} (ID: {query_id[:8]})\n  - {mode_text}\n  - Min: {min_percentage}%")
    
    # Build the response message
    message_text = f"🔍 Currently monitoring {coin_count} coin{'s' if coin_count != 1 else ''}:\n\n"
    message_text += "\n\n".join(monitors_info)
    message_text += "\n\nUse /stop <ID> to stop a specific monitor or /stop to stop all."
    
    await message.answer(message_text)

@router.message(Command("setmin"))
async def cmd_set_min_percentage(message: Message):
    """Set minimum arbitrage percentage for a specific coin monitor"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    # Check if user is admin and message is in private chat
    if not is_admin(user_id) or message.chat.type != "private":
        # Only respond in private chats
        if message.chat.type == "private":
            await message.answer("❌ Only admins can set minimum arbitrage percentage")
        return
    
    # Parse arguments: /setmin <monitor_id> <percentage>
    args = message.text.split()
    if len(args) < 3:
        await message.answer("⚠️ Please specify a monitor ID and percentage.\nExample: /setmin abc123 0.5")
        return
    
    monitor_id = args[1]
    try:
        min_percentage = float(args[2])
        if min_percentage <= 0:
            await message.answer("❌ Minimum percentage must be greater than 0")
            return
    except ValueError:
        await message.answer("❌ Invalid percentage value. Please enter a valid number")
        return
    
    if chat_id not in active_monitors or not active_monitors[chat_id]:
        await message.answer("❌ No active monitors found")
        return
    
    # Find the monitor by ID
    found = False
    for query_id, task in list(active_monitors[chat_id].items()):
        if query_id.startswith(monitor_id):
            # Cancel the current task
            task.cancel()
            
            # Find the associated query information
            query_info = None
            for chat_data in user_queries.values():
                if query_id in chat_data:
                    query_info = chat_data[query_id]
                    # Update the minimum percentage
                    query_info['min_percentage'] = min_percentage
                    break
            
            if not query_info:
                # If we can't find the query info, recreate it with default values
                query_info = {
                    'query': f"Unknown_{query_id[:8]}",
                    'min_percentage': min_percentage,
                    'filter_mode': "all",
                    'query_id': query_id
                }
                
                if chat_id not in user_queries:
                    user_queries[chat_id] = {}
                user_queries[chat_id][query_id] = query_info
            
            # Restart the monitor with the new minimum percentage
            alert_group_id = int(os.getenv("ALERT_GROUP_ID"))
            topic_id = int(os.getenv("TOPIC_ID", "0"))
            
            # Start new monitoring task
            task = asyncio.create_task(
                monitor_prices(
                    chat_id, 
                    query_info['query'], 
                    message.bot, 
                    min_percentage, 
                    query_info.get('network'), 
                    query_info.get('pool_address'), 
                    query_id
                )
            )
            
            # Update the active monitor
            active_monitors[chat_id][query_id] = task
            
            # Send confirmation
            await message.answer(f"✅ Updated minimum arbitrage for {query_info['query']} (ID: {query_id[:8]}) to {min_percentage}%")
            
            # Notify alert group
            await message.bot.send_message(
                chat_id=alert_group_id, 
                text=f"⚙️ Updated minimum arbitrage for {query_info['query']} (ID: {query_id[:8]}) to {min_percentage}%", 
                message_thread_id=topic_id, 
                parse_mode="HTML", 
                disable_web_page_preview=True
            )
            
            found = True
            break
    
    if not found:
        await message.answer(f"❌ No monitor found with ID: {monitor_id}")
        # List available monitors to help the user
        await cmd_list_coins(message) 