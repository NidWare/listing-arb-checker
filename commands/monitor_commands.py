import asyncio
import logging
import os
from aiogram import Router
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command, Text
from config.config_manager import ConfigManager
from handlers.exchange_handlers import monitor_prices, user_filter_preferences
from commands.bot_instance import get_bot_instance

# Configure logging
logger = logging.getLogger(__name__)

# Create router with name to help with debugging
monitor_router = Router(name="monitor_commands")

# Store active monitoring tasks
active_monitors = {}

# Store temporary user queries while waiting for filter and percentage input
# Format: {user_id: {"coin": coin_name, "filter_mode": None or "cex_only"/"all"}}
user_monitoring_setup = {}

def get_filter_mode_keyboard() -> InlineKeyboardMarkup:
    """Create a keyboard for selecting filter mode"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="CEX-CEX Only",
        callback_data="filter_cex_only"
    )
    
    builder.button(
        text="CEX-CEX + DEX",
        callback_data="filter_all"
    )
    
    builder.adjust(1)
    return builder.as_markup()

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
    
    # Store the coin and initialize setup
    user_monitoring_setup[message.from_user.id] = {
        "coin": coin,
        "filter_mode": None
    }
    
    # Always ask for filter mode
    try:
        keyboard = get_filter_mode_keyboard()
        await message.answer(
            f"Coin: {coin}\nStep 1/2: Please select which opportunities to monitor:",
            reply_markup=keyboard
        )
        logger.info(f"Sent filter selection keyboard to user {message.from_user.id} for coin {coin}")
    except Exception as e:
        logger.error(f"Error creating or sending filter keyboard: {str(e)}", exc_info=True)
        # Cancel the setup if there's an error
        if message.from_user.id in user_monitoring_setup:
            del user_monitoring_setup[message.from_user.id]
        await message.answer("❌ An error occurred setting up monitoring. Please try again.")

@monitor_router.callback_query(Text(startswith="filter_"))
async def handle_filter_mode_callback(callback: CallbackQuery):
    """Handle filter mode selection"""
    user_id = callback.from_user.id
    
    logger.info(f"Received filter callback from user {user_id}: {callback.data}")
    
    if user_id not in ConfigManager.get_admin_user_ids():
        logger.warning(f"Non-admin user {user_id} attempted to change filter settings")
        await callback.answer("Only admins can change filter settings", show_alert=True)
        return
    
    # Check if user has an active setup
    if user_id not in user_monitoring_setup:
        await callback.answer("No active monitoring setup found. Please use /monitor command first.", show_alert=True)
        return
    
    # Extract filter mode from callback data
    filter_mode = callback.data.split("_")[1]  # "cex_only" or "all"
    
    # Store the filter mode in the user's setup
    user_monitoring_setup[user_id]["filter_mode"] = filter_mode
    logger.info(f"Set filter mode for user {user_id} to {filter_mode}")
    
    # Get the stored coin
    coin = user_monitoring_setup[user_id]["coin"]
    
    # Prepare the display text
    if filter_mode == "cex_only":
        mode_text = "CEX-CEX Only (no DEX)"
    else:
        mode_text = "CEX-CEX + DEX"
    
    # Always answer the callback to prevent the "loading" state
    await callback.answer(f"Filter set to: {mode_text}")
    
    # Ask for minimum arbitrage percentage
    await callback.message.answer(
        f"Coin: {coin}\nFilter mode: {mode_text}\n\n"
        f"Step 2/2: Please enter the minimum arbitrage percentage (e.g., 0.5 for 0.5%)"
    )

@monitor_router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    """Cancel the current monitoring setup process"""
    user_id = message.from_user.id
    
    if user_id in user_monitoring_setup:
        # Get the coin being set up
        coin = user_monitoring_setup[user_id]["coin"]
        # Clean up
        del user_monitoring_setup[user_id]
        await message.answer(f"✅ Monitoring setup for {coin} has been cancelled.")
    else:
        await message.answer("No monitoring setup in progress to cancel.")

# This filter needs to run before the catch-all handler in basic_commands
@monitor_router.message(lambda message: message.from_user.id in user_monitoring_setup and not message.text.startswith('/'))
async def handle_min_percentage(message: Message):
    logger.info(f"Processing input from user {message.from_user.id} who is in user_monitoring_setup")
    user_id = message.from_user.id
    
    if user_id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return
    
    # Get the user's setup data
    setup_data = user_monitoring_setup.get(user_id)
    if not setup_data:
        await message.answer("⚠️ No active setup found. Please use /monitor command.")
        return
    
    # Get the coin and filter mode
    coin = setup_data["coin"]
    filter_mode = setup_data["filter_mode"]
    
    # Ensure filter mode is set
    if not filter_mode:
        # If filter mode is not set, ask for it first
        await message.answer(
            f"⚠️ Please select a filter mode for {coin} first:", 
            reply_markup=get_filter_mode_keyboard()
        )
        return
    
    # Parse the minimum percentage
    try:
        min_percentage = float(message.text.strip())
        if min_percentage <= 0:
            await message.answer("Minimum percentage must be greater than 0. Please try again or use /cancel to abort.")
            return
    except ValueError:
        await message.answer("Please enter a valid number (e.g., 0.5 for 0.5%). Try again or use /cancel to abort.")
        return
    
    # Remove the setup from the waiting list
    del user_monitoring_setup[user_id]
    
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
        
        # Get the display text for the filter mode
        filter_mode_text = "CEX-CEX Only" if filter_mode == "cex_only" else "CEX-CEX + DEX"

        # Store the filter mode for this monitoring session
        user_filter_preferences[chat_id] = filter_mode
        logger.info(f"Saved filter mode {filter_mode} for chat_id {chat_id}")

        # Send status message ONLY to the admin who initiated the command
        await message.answer(f"🔍 Starting price monitoring for {coin} with minimum arbitrage of {min_percentage}%...\nFilter mode: {filter_mode_text}")

        # Start new monitoring task with the custom min_arbitrage_percentage
        task = asyncio.create_task(monitor_prices(chat_id, coin, admin_bot, min_percentage))
        active_monitors[chat_id] = task

        # Send confirmation ONLY to the admin who initiated the command
        await message.answer(
            f"✅ Monitoring started for {coin}!\n\n"
            f"Filter mode: {filter_mode_text}\n"
            f"I will notify you when there are arbitrage opportunities with >{min_percentage}% difference.\n"
            "Use /stop_monitor command to stop monitoring."
        )

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