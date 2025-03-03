import asyncio
import logging
import os
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from config.config_manager import ConfigManager
from handlers.exchange_handlers import monitor_prices
from commands.bot_instance import get_bot_instance

# Configure logging
logger = logging.getLogger(__name__)

# Create router with name to help with debugging
monitor_router = Router(name="monitor_commands")

# Store active monitoring tasks
active_monitors = {}

# Store temporary user queries while waiting for min percentage input
user_queries = {}

@monitor_router.message(Command("monitor"))
async def cmd_monitor(message: Message):
    logger.info(f"Received /monitor command from user {message.from_user.id}")
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Extract coin name from command
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Please specify a coin to monitor. Example: /monitor BTC")
        return

    coin = args[1].upper()
    
    # Ask for minimum arbitrage percentage
    await message.answer(f"Coin: {coin}\nPlease enter the minimum arbitrage percentage (e.g., 0.5 for 0.5%)")
    
    # Store the query information to start monitoring after getting the percentage
    user_queries[message.from_user.id] = coin
    logger.info(f"Added user {message.from_user.id} to user_queries with coin {coin}")
    
@monitor_router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    """Cancel the current monitoring setup process"""
    user_id = message.from_user.id
    
    if user_id in user_queries:
        # Remove the query from waiting list
        coin = user_queries.pop(user_id)
        await message.answer(f"✅ Monitoring setup for {coin} has been cancelled.")
    else:
        await message.answer("No monitoring setup in progress to cancel.")

# This filter needs to run before the catch-all handler in basic_commands
@monitor_router.message(lambda message: message.from_user.id in user_queries and not message.text.startswith('/'))
async def handle_min_percentage(message: Message):
    logger.info(f"Processing input from user {message.from_user.id} who is in user_queries")
    user_id = message.from_user.id
    
    if user_id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return
    
    # Get the stored coin
    coin = user_queries.get(user_id)
    
    # Parse the minimum percentage
    try:
        min_percentage = float(message.text.strip())
        if min_percentage <= 0:
            await message.answer("Minimum percentage must be greater than 0. Please try again or use /cancel to abort.")
            return
    except ValueError:
        await message.answer("Please enter a valid number (e.g., 0.5 for 0.5%). Try again or use /cancel to abort.")
        return
    
    # Remove the query from the waiting list
    user_queries.pop(user_id, None)
    
    # Use the supergroup ID for monitoring
    chat_id = ConfigManager.get_alert_group_id()  # Get from config
    topic_id = int(os.getenv("TOPIC_ID", "1"))  # Get topic ID from env
    logger.info(f"Attempting to send message to chat_id: {chat_id} with topic_id: {topic_id}")

    try:
        # Cancel existing monitoring task if any
        if chat_id in active_monitors:
            active_monitors[chat_id].cancel()
            del active_monitors[chat_id]

        # Get bot instance
        admin_bot = get_bot_instance()

        # Send status message ONLY to the admin who initiated the command
        await message.answer(f"🔍 Starting price monitoring for {coin} with minimum arbitrage of {min_percentage}%...")

        # Start new monitoring task with the custom min_arbitrage_percentage
        task = asyncio.create_task(monitor_prices(chat_id, coin, admin_bot, min_percentage))
        active_monitors[chat_id] = task

        # Send confirmation ONLY to the admin who initiated the command
        await message.answer(f"✅ Monitoring started for {coin}!\n\n"
                             f"I will notify you when there are arbitrage opportunities with >{min_percentage}% difference.\n"
                             "Use /stop_monitor command to stop monitoring.")

    except Exception as e:
        logger.error(f"Error starting monitoring: {str(e)}", exc_info=True)
        # Try to send error message to the user who initiated the command
        await message.answer(f"❌ Error starting monitoring: {str(e)}")

@monitor_router.message(Command("stop_monitor"))
async def cmd_stop_monitor(message: Message):
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Use the supergroup ID for monitoring
    chat_id = ConfigManager.get_alert_group_id()

    if chat_id in active_monitors:
        active_monitors[chat_id].cancel()
        del active_monitors[chat_id]
        
        # Send "Monitoring stopped" message ONLY to the admin who initiated the command
        await message.answer("✅ Monitoring stopped")
    else:
        await message.answer("❌ No active monitoring found") 