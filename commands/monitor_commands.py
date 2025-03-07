import asyncio
import logging
import os
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
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
# Format: {user_id: {"coin": coin_name, "filter_mode": None or "cex_only"/"all", 
#                    "network": None or network_name, "token_address": None or address}}
user_monitoring_setup = {}

# Keep this for backward compatibility with imports
user_queries = {}

def get_filter_mode_keyboard() -> InlineKeyboardMarkup:
    """Create a keyboard for selecting filter mode"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="CEX-CEX Only",
        callback_data="filter_cex"
    )

    builder.button(
        text="CEX-DEX Only",
        callback_data="filter_cex_dex_only"
    )
    
    builder.button(
        text="DEX + CEX (ONLY FUTURE)",
        callback_data="filter_future"
    )
    
    builder.button(
        text="ALL",
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

@monitor_router.callback_query(F.data.startswith("filter_"))
async def handle_filter_mode_callback(callback: CallbackQuery):
    """Handle filter mode selection"""
    user_id = callback.from_user.id
    chat_id = callback.message.chat.id
    
    logger.info(f"Received filter callback from user {user_id}: {callback.data}")
    
    # Check if user is admin
    if user_id not in ConfigManager.get_admin_user_ids():
        logger.warning(f"Non-admin user {user_id} attempted to change filter settings")
        await callback.answer("Only admins can change filter settings", show_alert=True)
        return
    
    # Check if user has an active setup
    if user_id not in user_monitoring_setup:
        await callback.answer("No active monitoring setup found. Please use /monitor command first.", show_alert=True)
        return
    
    # Extract filter mode from callback data
    callback_data = callback.data
    
    # Determine the filter mode based on the full callback data
    if callback_data == "filter_cex":
        filter_mode = "cex_only"
    elif callback_data == "filter_cex_dex_only":
        filter_mode = "cex_dex_only"
    elif callback_data == "filter_future":
        filter_mode = "future"
    elif callback_data == "filter_all":
        filter_mode = "all"
    else:
        logger.warning(f"Unknown filter mode callback: {callback_data}")
        filter_mode = "all"  # Default to all
    
    logger.info(f"Parsed filter mode: {filter_mode} from callback data: {callback_data}")
    
    # Store the filter mode in the user's setup
    user_monitoring_setup[user_id]["filter_mode"] = filter_mode
    # Initialize network and token address fields if not present
    if "network" not in user_monitoring_setup[user_id]:
        user_monitoring_setup[user_id]["network"] = None
    if "pool_address" not in user_monitoring_setup[user_id]:
        user_monitoring_setup[user_id]["pool_address"] = None
        
    logger.info(f"Set filter mode for user {user_id} to {filter_mode}")
    
    # Get the stored coin
    coin = user_monitoring_setup[user_id]["coin"]
    
    # Prepare the display text
    if filter_mode == "cex_only":
        mode_text = "CEX-CEX Only (no DEX)"
    elif filter_mode == "cex_dex_only":
        mode_text = "ONLY CEX-DEX"
    elif filter_mode == "future":
        mode_text = "DEX + CEX (ONLY FUTURE)"
    else:
        mode_text = "CEX-CEX + DEX"
    
    logger.info(f"Display text for filter mode {filter_mode}: {mode_text}")
    
    # Always answer the callback to prevent the "loading" state
    await callback.answer(f"Filter set to: {mode_text}")
    
    # For DEX related filters, ask for network and token address first
    if filter_mode in ["cex_dex_only", "future", "all"]:
        await callback.message.answer(
            f"Coin: {coin}\nFilter mode: {mode_text}\n\n"
            f"For DEX operations, please enter the network name (e.g., Ethereum, BSC, Polygon)"
        )
        # Mark that we're waiting for network input
        user_monitoring_setup[user_id]["waiting_for"] = "network"
    else:
        # For CEX-only mode, proceed to ask for minimum arbitrage percentage
        await callback.message.answer(
            f"Coin: {coin}\nFilter mode: {mode_text}\n\n"
            f"Step 2/2: Please enter the minimum arbitrage percentage (e.g., 0.5 for 0.5%)"
        )
        # Mark that we're waiting for percentage input
        user_monitoring_setup[user_id]["waiting_for"] = "percentage"

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
    waiting_for = setup_data.get("waiting_for", "percentage")  # Default to percentage for backward compatibility
    
    # Ensure filter mode is set
    if not filter_mode:
        # If filter mode is not set, ask for it first
        await message.answer(
            f"⚠️ Please select a filter mode for {coin} first:", 
            reply_markup=get_filter_mode_keyboard()
        )
        return
    
    # If waiting for network information
    if waiting_for == "network":
        network = message.text.strip()
        setup_data["network"] = network
        setup_data["waiting_for"] = "pool_address"
        await message.answer(
            f"Network: {network}\n\n"
            f"Now, please enter the pool address for {coin} on {network}"
        )
        return
    
    # If waiting for pool address
    elif waiting_for == "pool_address":
        pool_address = message.text.strip()
        setup_data["pool_address"] = pool_address
        setup_data["waiting_for"] = "percentage"
        
        # Get network for display
        network = setup_data["network"]
        
        await message.answer(
            f"Pool address: {pool_address}\n"
            f"Network: {network}\n\n"
            f"Finally, please enter the minimum arbitrage percentage (e.g., 0.5 for 0.5%)"
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
    
    # For DEX modes, ensure network and pool address are provided
    if filter_mode in ["cex_dex_only", "future", "all"]:
        network = setup_data.get("network")
        pool_address = setup_data.get("pool_address")
        
        if not network or not pool_address:
            missing = []
            if not network:
                missing.append("network name")
            if not pool_address:
                missing.append("pool address")
            
            await message.answer(f"⚠️ Missing required information: {', '.join(missing)}. Please use /cancel and try again.")
            return
    
    # Store setup data for use in monitoring
    network = setup_data.get("network")
    pool_address = setup_data.get("pool_address")
    
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
        
        # Store the filter mode for this monitoring session
        user_filter_preferences[chat_id] = filter_mode
        logger.info(f"Saved filter mode {filter_mode} for chat_id {chat_id}")

        # Get the display text for the filter mode
        if filter_mode == "cex_only":
            filter_mode_text = "CEX-CEX Only (no DEX)"
        elif filter_mode == "cex_dex_only":
            filter_mode_text = "ONLY CEX-DEX"
        elif filter_mode == "future":
            filter_mode_text = "DEX + CEX (ONLY FUTURE)"
        else:
            filter_mode_text = "CEX-CEX + DEX"
        
        logger.info(f"Final display text: {filter_mode_text} for filter mode: {filter_mode}")

        # Prepare network and pool address info for display
        dex_info = ""
        if filter_mode in ["cex_dex_only", "future", "all"]:
            dex_info = f"\nNetwork: {network}\nPool Address: {pool_address}"

        # Send status message ONLY to the admin who initiated the command
        await message.answer(f"🔍 Starting price monitoring for {coin} with minimum arbitrage of {min_percentage}%...\nFilter mode: {filter_mode_text}{dex_info}")

        # Start new monitoring task with the custom min_arbitrage_percentage and DEX info if applicable
        task = asyncio.create_task(monitor_prices(chat_id, coin, admin_bot, min_percentage, network=network, pool_address=pool_address))
        active_monitors[chat_id] = task

        # Send confirmation ONLY to the admin who initiated the command
        await message.answer(
            f"✅ Monitoring started for {coin}!\n\n"
            f"Filter mode: {filter_mode_text}{dex_info}\n"
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

@monitor_router.message(Command("set_filter"))
async def cmd_set_filter(message: Message):
    """Explicitly set the filter mode for monitoring"""
    logger.info(f"Received /set_filter command from user {message.from_user.id}")
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Extract filter mode from command
    args = message.text.split()
    if len(args) < 2 or args[1].lower() not in ["cex", "cex_dex", "all"]:
        await message.answer("❌ Please specify a valid filter mode. Example: /set_filter cex (for CEX-CEX only), /set_filter cex_dex (for ONLY CEX-DEX), or /set_filter all (for CEX+DEX)")
        return

    # Get the filter mode
    if args[1].lower() == "cex":
        filter_mode = "cex_only"
    elif args[1].lower() == "cex_dex":
        filter_mode = "cex_dex_only"
    else:
        filter_mode = "all"
    
    # Get the group ID where opportunities will be posted
    chat_id = ConfigManager.get_alert_group_id()
    
    # Store the user's preference
    user_filter_preferences[chat_id] = filter_mode
    logger.info(f"Set filter mode for user {message.from_user.id} to {filter_mode}")
    
    # Send confirmation
    if filter_mode == "cex_only":
        filter_mode_text = "CEX-CEX Only (no DEX)"
    elif filter_mode == "cex_dex_only":
        filter_mode_text = "ONLY CEX-DEX"
    else:
        filter_mode_text = "CEX-CEX + DEX"
    
    await message.answer(f"✅ Filter mode set to: {filter_mode_text}")
    
    # If user has a pending query, continue with appropriate next step
    if message.from_user.id in user_monitoring_setup:
        coin = user_monitoring_setup[message.from_user.id]["coin"]
        user_monitoring_setup[message.from_user.id]["filter_mode"] = filter_mode
        
        # Initialize network and pool address fields
        if "network" not in user_monitoring_setup[message.from_user.id]:
            user_monitoring_setup[message.from_user.id]["network"] = None
        if "pool_address" not in user_monitoring_setup[message.from_user.id]:
            user_monitoring_setup[message.from_user.id]["pool_address"] = None
        
        # For DEX related filters, ask for network and pool address
        if filter_mode in ["cex_dex_only", "all"]:
            user_monitoring_setup[message.from_user.id]["waiting_for"] = "network"
            await message.answer(
                f"Coin: {coin}\nFilter mode: {filter_mode_text}\n\n"
                f"For DEX operations, please enter the network name (e.g., Ethereum, BSC, Polygon)"
            )
        else:
            # For CEX-only mode, proceed to ask for minimum arbitrage percentage
            user_monitoring_setup[message.from_user.id]["waiting_for"] = "percentage"
            await message.answer(
                f"Coin: {coin}\nFilter mode: {filter_mode_text}\n\n"
                f"Please enter the minimum arbitrage percentage (e.g., 0.5 for 0.5%)"
            ) 