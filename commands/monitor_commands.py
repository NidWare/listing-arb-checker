import asyncio
import logging
import os
import uuid
from typing import Dict, Any, Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command

from config.config_manager import ConfigManager
from commands.bot_instance import get_bot_instance

# Configure logging
logger = logging.getLogger(__name__)

# Create router with name to help with debugging
monitor_router = Router(name="monitor_commands")

# Format: {user_id: {"coin": coin_name, "filter_mode": None, 
#                   "network": None, "pool_address": None, "waiting_for": step}}
user_monitoring_setup = {}

# Delay import of MonitorService to avoid circular import
# and initialize it later after the module is fully loaded
monitor_service = None

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

def get_network_keyboard() -> InlineKeyboardMarkup:
    """Create a keyboard for selecting network"""
    builder = InlineKeyboardBuilder()
    
    networks = [
        {"text": "Ethereum", "callback_data": "network_ether"},
        {"text": "Solana", "callback_data": "network_solana"},
        {"text": "Base", "callback_data": "network_base"},
        {"text": "Avalanche", "callback_data": "network_avalanche"},
        {"text": "BSC", "callback_data": "network_bsc"},
        {"text": "Arbitrum", "callback_data": "network_arbitrum"}
    ]
    
    for network in networks:
        builder.button(
            text=network["text"],
            callback_data=network["callback_data"]
        )
    
    builder.adjust(2)
    return builder.as_markup()

def get_deposit_withdrawal_check_keyboard() -> InlineKeyboardMarkup:
    """Create a keyboard for selecting deposit/withdrawal check setting"""
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="Yes (More Accurate)",
        callback_data="deposit_check_yes"
    )
    
    builder.button(
        text="No (Faster Alerts)",
        callback_data="deposit_check_no"
    )
    
    builder.adjust(1)
    return builder.as_markup()

def get_filter_mode_display_text(filter_mode: str) -> str:
    """Convert filter mode to human-readable text"""
    if filter_mode == "cex_only":
        return "CEX-CEX Only (no DEX)"
    elif filter_mode == "cex_dex_only":
        return "ONLY CEX-DEX" 
    elif filter_mode == "future":
        return "DEX + CEX (ONLY FUTURE)"
    else:
        return "CEX-CEX + DEX"

@monitor_router.message(Command("monitor"))
async def cmd_monitor(message: Message):
    """Deprecated - redirects users to /addcoin"""
    logger.info(f"Received /monitor command from user {message.from_user.id}")
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Redirect users to use the addcoin command instead
    await message.answer(
        "⚠️ The /monitor command is deprecated.\n\n"
        "Please use /addcoin instead.\n"
        "Example: /addcoin BTC"
    )

@monitor_router.callback_query(F.data.startswith("filter_"))
async def handle_filter_mode_callback(callback: CallbackQuery):
    """Handle filter mode selection"""
    user_id = callback.from_user.id
    
    logger.info(f"Received filter callback from user {user_id}: {callback.data}")
    
    # Check if user is admin
    if user_id not in ConfigManager.get_admin_user_ids():
        logger.warning(f"Non-admin user {user_id} attempted to change filter settings")
        await callback.answer("Only admins can change filter settings", show_alert=True)
        return
    
    # Check if user has an active setup
    if user_id not in user_monitoring_setup:
        await callback.answer("No active monitoring setup found. Please use /addcoin command first.", show_alert=True)
        return
    
    # Ensure MonitorService is initialized
    _ensure_monitor_service()
    
    # Extract filter mode from callback data
    filter_mode = monitor_service.parse_filter_mode(callback.data)
    
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
    
    # Get display text for the selected filter mode
    mode_text = get_filter_mode_display_text(filter_mode)
    
    # Always answer the callback to prevent the "loading" state
    await callback.answer(f"Filter set to: {mode_text}")
    
    # For DEX related filters, ask for network and token address first
    if filter_mode in ["cex_dex_only", "future", "all"]:
        # Show network selection keyboard
        network_keyboard = get_network_keyboard()
        await callback.message.answer(
            f"Coin: {coin}\nFilter mode: {mode_text}\n\n"
            f"Please select the network:",
            reply_markup=network_keyboard
        )
        # Mark that we're waiting for network input
        user_monitoring_setup[user_id]["waiting_for"] = "network"
    else:
        # For CEX-only mode, proceed to ask about deposit/withdrawal checks
        deposit_check_keyboard = get_deposit_withdrawal_check_keyboard()
        await callback.message.answer(
            f"Coin: {coin}\nFilter mode: {mode_text}\n\n"
            f"Would you like to enforce deposit/withdrawal checks?\n"
            f"This makes alerts more accurate but might be slower:",
            reply_markup=deposit_check_keyboard
        )
        # Mark that we're waiting for deposit check input
        user_monitoring_setup[user_id]["waiting_for"] = "deposit_check"

@monitor_router.callback_query(F.data.startswith("network_"))
async def handle_network_callback(callback: CallbackQuery):
    """Handle network selection"""
    user_id = callback.from_user.id
    
    logger.info(f"Received network callback from user {user_id}: {callback.data}")
    
    # Check if user is admin
    if user_id not in ConfigManager.get_admin_user_ids():
        logger.warning(f"Non-admin user {user_id} attempted to select network")
        await callback.answer("Only admins can select network", show_alert=True)
        return
    
    # Check if user has an active setup
    if user_id not in user_monitoring_setup:
        await callback.answer("No active monitoring setup found. Please use /addcoin command first.", show_alert=True)
        return
    
    # Check if user is waiting for network input
    if user_monitoring_setup[user_id].get("waiting_for") != "network":
        await callback.answer("Unexpected network selection", show_alert=True)
        return
    
    # Extract network from callback data (remove "network_" prefix)
    network_id = callback.data[8:]  # Use exact API network identifier
    
    # Map network_id to display name for UI
    network_display_names = {
        "ether": "Ethereum",
        "solana": "Solana",
        "base": "Base",
        "avalanche": "Avalanche",
        "bsc": "BSC",
        "arbitrum": "Arbitrum"
    }
    
    network_display = network_display_names.get(network_id, network_id.capitalize())
    
    # Store the network in the user's setup (using API-compatible network id)
    user_monitoring_setup[user_id]["network"] = network_id
    user_monitoring_setup[user_id]["waiting_for"] = "pool_address"
    
    # Get the stored coin
    coin = user_monitoring_setup[user_id]["coin"]
    
    # Get display text for the selected filter mode
    filter_mode = user_monitoring_setup[user_id]["filter_mode"]
    mode_text = get_filter_mode_display_text(filter_mode)
    
    # Always answer the callback to prevent the "loading" state
    await callback.answer(f"Network set to: {network_display}")
    
    # Ask for pool address
    await callback.message.answer(
        f"Coin: {coin}\nFilter mode: {mode_text}\nNetwork: {network_display}\n\n"
        f"Now, please enter the pool address for {coin} on {network_display}"
    )

@monitor_router.callback_query(F.data.startswith("deposit_check_"))
async def handle_deposit_check_callback(callback: CallbackQuery):
    """Handle deposit/withdrawal check selection"""
    user_id = callback.from_user.id
    
    logger.info(f"Received deposit check callback from user {user_id}: {callback.data}")
    
    # Check if user is admin
    if user_id not in ConfigManager.get_admin_user_ids():
        logger.warning(f"Non-admin user {user_id} attempted to set deposit check")
        await callback.answer("Only admins can change this setting", show_alert=True)
        return
    
    # Check if user has an active setup
    if user_id not in user_monitoring_setup:
        await callback.answer("No active monitoring setup found. Please use /addcoin command first.", show_alert=True)
        return
    
    # Check if user is waiting for deposit check input
    if user_monitoring_setup[user_id].get("waiting_for") != "deposit_check":
        await callback.answer("Unexpected deposit check selection", show_alert=True)
        return
    
    # Extract deposit check setting from callback data
    deposit_check = callback.data == "deposit_check_yes"
    
    # Store the setting in the user's setup
    user_monitoring_setup[user_id]["enforce_deposit_withdrawal_checks"] = deposit_check
    user_monitoring_setup[user_id]["waiting_for"] = "percentage"
    
    # Get the stored coin and other information for display
    coin = user_monitoring_setup[user_id]["coin"]
    filter_mode = user_monitoring_setup[user_id]["filter_mode"]
    mode_text = get_filter_mode_display_text(filter_mode)
    
    # Prepare other information for display
    additional_info = ""
    if filter_mode in ["cex_dex_only", "future", "all"]:
        network = user_monitoring_setup[user_id]["network"]
        pool_address = user_monitoring_setup[user_id]["pool_address"]
        additional_info = f"\nNetwork: {network}\nPool Address: {pool_address}"
    
    # Always answer the callback to prevent the "loading" state
    check_status = "Enabled" if deposit_check else "Disabled"
    await callback.answer(f"Deposit/Withdrawal Checks: {check_status}")
    
    # Ask for minimum percentage
    await callback.message.answer(
        f"Coin: {coin}\nFilter mode: {mode_text}{additional_info}\n"
        f"Deposit/Withdrawal Checks: {check_status}\n\n"
        f"Finally, please enter the minimum arbitrage percentage (e.g., 0.5 for 0.5%)"
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
    """Handle input for monitoring setup wizard (pool address or percentage)"""
    logger.info(f"Processing input from user {message.from_user.id} who is in user_monitoring_setup")
    user_id = message.from_user.id
    
    if user_id not in ConfigManager.get_admin_user_ids():
        return
    
    # Get the user's setup data
    setup_data = user_monitoring_setup.get(user_id)
    if not setup_data:
        await message.answer("⚠️ No active setup found. Please use /addcoin command.")
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
    
    # If waiting for pool address
    if waiting_for == "pool_address":
        pool_address = message.text.strip()
        setup_data["pool_address"] = pool_address
        setup_data["waiting_for"] = "deposit_check"
        
        # Get network for display
        network = setup_data["network"]
        
        # Show deposit/withdrawal check selection keyboard
        deposit_check_keyboard = get_deposit_withdrawal_check_keyboard()
        await message.answer(
            f"Pool address: {pool_address}\n"
            f"Network: {network}\n\n"
            f"Would you like to enforce deposit/withdrawal checks?\n"
            f"This makes alerts more accurate but might be slower:",
            reply_markup=deposit_check_keyboard
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
    enforce_deposit_withdrawal_checks = setup_data.get("enforce_deposit_withdrawal_checks", False)
    
    # Generate a unique query ID
    query_id = str(uuid.uuid4())
    
    # Remove the setup from the waiting list
    del user_monitoring_setup[user_id]
    
    # Ensure MonitorService is initialized
    _ensure_monitor_service()
    
    try:
        # Start monitoring using the service
        result = await monitor_service.start_monitoring(
            user_id=user_id,
            query=coin,
            bot=message.bot,
            min_percentage=min_percentage,
            filter_mode=filter_mode,
            network=network,
            pool_address=pool_address,
            query_id=query_id,
            enforce_deposit_withdrawal_checks=enforce_deposit_withdrawal_checks
        )
        
        if result["success"]:
            # Get display text for the filter mode
            mode_text = get_filter_mode_display_text(filter_mode)
            
            # Prepare network and pool address info for display
            dex_info = ""
            if filter_mode in ["cex_dex_only", "future", "all"]:
                dex_info = f"\nNetwork: {network}\nPool Address: {pool_address}"
            
            # Add deposit/withdrawal check info
            check_status = "Enabled" if enforce_deposit_withdrawal_checks else "Disabled"
                
            # Send success message to the user
            await message.answer(
                f"✅ Monitoring started for {coin} (Monitor ID: {query_id[:8]})!\n\n"
                f"Filter mode: {mode_text}{dex_info}\n"
                f"Deposit/Withdrawal Checks: {check_status}\n"
                f"I will notify you when there are arbitrage opportunities with >{min_percentage}% difference.\n"
                "Use /stop command with ID to stop specific monitoring or /stop_monitor to stop all.",
                parse_mode=None
            )
        else:
            await message.answer(f"❌ Error starting monitoring: {result['error']}")
    except Exception as e:
        logger.error(f"Error starting monitoring: {str(e)}", exc_info=True)
        await message.answer(f"❌ Error starting monitoring: {str(e)}")

@monitor_router.message(Command("stop"))
async def cmd_stop(message: Message):
    """Stop monitoring a specific coin by ID"""
    logger.info(f"Received /stop command from user {message.from_user.id}")
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Parse arguments: /stop [monitor_id]
    args = message.text.split()
    monitor_id = args[1] if len(args) > 1 else None
    
    if not monitor_id:
        await message.answer("⚠️ Please specify a monitor ID.\nExample: /stop abc123\nUse /listcoins to see available monitors.", parse_mode=None)
        return
    
    # Ensure MonitorService is initialized
    _ensure_monitor_service()
    
    result = await monitor_service.stop_monitoring(monitor_id)
    
    if result["success"]:
        await message.answer(f"✅ Stopped monitoring for Monitor ID: {result['query_id'][:8]}", parse_mode=None)
    else:
        await message.answer(f"❌ {result['error']}", parse_mode=None)
        # List available monitors to help the user
        await cmd_list_coins(message)

@monitor_router.message(Command("stop_monitor"))
async def cmd_stop_monitor(message: Message):
    """Stop all monitoring tasks"""
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Ensure MonitorService is initialized
    _ensure_monitor_service()
    
    result = await monitor_service.stop_all_monitoring()
    
    # Send "Monitoring stopped" message ONLY to the admin who initiated the command
    await message.answer(f"✅ Monitoring stopped for all {result['count']} coins")
    
    # Also log the details
    logger.info(f"Stopped {result['count']} monitors ({result['details']})")

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

    # Ensure MonitorService is initialized
    _ensure_monitor_service()
    
    # Get the filter mode
    filter_mode = monitor_service.parse_filter_mode_from_command(args[1].lower())
    
    # Set the filter mode using the service
    monitor_service.set_global_filter_mode(filter_mode)
    
    # Get display text for the filter mode
    mode_text = get_filter_mode_display_text(filter_mode)
    
    # Send confirmation
    await message.answer(f"✅ Filter mode set to: {mode_text}")
    
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
        if filter_mode in ["cex_dex_only", "future", "all"]:
            user_monitoring_setup[message.from_user.id]["waiting_for"] = "network"
            # Show network selection keyboard
            network_keyboard = get_network_keyboard()
            await message.answer(
                f"Coin: {coin}\nFilter mode: {mode_text}\n\n"
                f"Please select the network:",
                reply_markup=network_keyboard
            )
        else:
            # For CEX-only mode, proceed to ask about deposit/withdrawal checks
            user_monitoring_setup[message.from_user.id]["waiting_for"] = "deposit_check"
            deposit_check_keyboard = get_deposit_withdrawal_check_keyboard()
            await message.answer(
                f"Coin: {coin}\nFilter mode: {mode_text}\n\n"
                f"Would you like to enforce deposit/withdrawal checks?\n"
                f"This makes alerts more accurate but might be slower:",
                reply_markup=deposit_check_keyboard
            )

@monitor_router.message(Command("addcoin"))
async def cmd_add_coin(message: Message):
    """Add a new coin to monitor"""
    logger.info(f"Received /addcoin command from user {message.from_user.id}")
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Extract coin name from command
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Please specify a coin to monitor. Example: /addcoin BTC")
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

@monitor_router.message(Command("listcoins"))
async def cmd_list_coins(message: Message):
    """List all coins being monitored"""
    logger.info(f"Received /listcoins command from user {message.from_user.id}")
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return
    
    # Ensure MonitorService is initialized
    _ensure_monitor_service()
    
    monitors = await monitor_service.list_all_monitors()
    
    # Build the response message
    if not monitors:
        await message.answer("⚠️ No coins are currently being monitored")
        return
    
    message_text = "🔍 Currently monitoring:\n\n"
    message_text += "\n\n".join(monitors)
    message_text += "\n\nCommands:\n• /stop <code> - Stop a specific monitor\n• /stop_monitor - Stop all monitoring\n• /setmin <code> <percentage> - Set minimum %"
    
    await message.answer(message_text, parse_mode=None)

@monitor_router.message(Command("setmin"))
async def cmd_set_min_percentage(message: Message):
    """Set minimum arbitrage percentage for a specific coin by ID"""
    logger.info(f"Received /setmin command from user {message.from_user.id}")
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Parse arguments: /setmin <monitor_id> <percentage>
    args = message.text.split()
    if len(args) < 3:
        await message.answer("⚠️ Please specify a monitor ID and percentage.\nExample: /setmin abc123 0.5", parse_mode=None)
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
    
    # Ensure MonitorService is initialized
    _ensure_monitor_service()
    
    # Update the minimum percentage using the service
    result = await monitor_service.update_min_percentage(monitor_id, min_percentage)
    
    if result["success"]:
        await message.answer(f"✅ Minimum percentage for {result['query']} (ID: {result['query_id'][:8]}) set to {min_percentage}%")
    else:
        await message.answer(f"❌ {result['error']}")
        # List available monitors to help the user
        await cmd_list_coins(message)

def _ensure_monitor_service():
    """Ensure that the monitor service is initialized"""
    global monitor_service
    if monitor_service is None:
        from services.monitor_service import MonitorService
        monitor_service = MonitorService() 