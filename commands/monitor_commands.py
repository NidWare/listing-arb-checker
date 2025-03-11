import asyncio
import logging
import os
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters import Command
from config.config_manager import ConfigManager
from handlers.exchange_handlers import monitor_prices, user_filter_preferences, active_monitors as handler_active_monitors, cmd_add_coin, cmd_list_coins
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

# Function to generate a unique ID for each query
def generate_query_id() -> str:
    """Generate a unique ID for a monitoring query"""
    return str(uuid.uuid4())

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

        # Generate a unique query ID for this monitoring task
        query_id = generate_query_id()
        
        # Use the handlers implementation for multi-coin support
        try:
            # Import what we need from handlers
            from handlers.exchange_handlers import active_monitors as handler_active_monitors
            from handlers.exchange_handlers import user_queries as handler_user_queries
            from handlers.exchange_handlers import monitor_prices
            
            # Set up the multi-coin monitoring (similar to what addcoin command does)
            user_chat_id = message.chat.id
            
            # Store the query information
            if user_chat_id not in handler_user_queries:
                handler_user_queries[user_chat_id] = {}
                
            handler_user_queries[user_chat_id][query_id] = {
                'query': coin, 
                'min_percentage': min_percentage, 
                'filter_mode': filter_mode,
                'query_id': query_id,
                'network': network,
                'pool_address': pool_address
            }
            
            # Start monitoring task using multi-coin implementation
            task = asyncio.create_task(
                monitor_prices(
                    user_chat_id, 
                    coin, 
                    admin_bot, 
                    min_percentage, 
                    network=network, 
                    pool_address=pool_address,
                    query_id=query_id
                )
            )
            
            # Store the task in handler's active_monitors
            if user_chat_id not in handler_active_monitors:
                handler_active_monitors[user_chat_id] = {}
                
            handler_active_monitors[user_chat_id][query_id] = task
            
            # Do NOT set active_monitors[chat_id] = task as this would replace any existing monitors
            # Instead, just add it to the alert group's active_monitors as a new entry
            
            # Success! Send confirmation message
            await message.answer(
                f"✅ Monitoring started for {coin} (Monitor ID: {query_id[:8]})!\n\n"
                f"Filter mode: {filter_mode_text}{dex_info}\n"
                f"I will notify you when there are arbitrage opportunities with >{min_percentage}% difference.\n"
                "Use /stop command with ID to stop specific monitoring or /stop_monitor to stop all."
            )
            
        except ImportError:
            # Fall back to the original implementation if handlers not available
            logger.warning("Could not import handler implementation, falling back to original")
            
            # Start new monitoring task with the original implementation
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
        await message.answer("⚠️ Please specify a monitor ID.\nExample: /stop abc123\nUse /listcoins to see available monitors.")
        return
    
    # Try to find the monitor in the handler implementation
    try:
        from handlers.exchange_handlers import active_monitors as handler_active_monitors
        
        found = False
        
        # Check each chat's monitors
        for chat_id, monitors in handler_active_monitors.items():
            for query_id, task in list(monitors.items()):
                if query_id.startswith(monitor_id):
                    # Found the monitor, stop it
                    task.cancel()
                    del handler_active_monitors[chat_id][query_id]
                    
                    # If no more monitors for this chat, remove the chat entry
                    if not handler_active_monitors[chat_id]:
                        del handler_active_monitors[chat_id]
                    
                    await message.answer(f"✅ Stopped monitoring for Monitor ID: {query_id[:8]}")
                    
                    # Also notify the alert group
                    alert_group_id = ConfigManager.get_alert_group_id()
                    topic_id = int(os.getenv("TOPIC_ID", "0"))
                    bot = get_bot_instance()
                    
                    await bot.send_message(
                        chat_id=alert_group_id,
                        text=f"✅ Monitoring stopped for Monitor ID: {query_id[:8]}",
                        message_thread_id=topic_id,
                        parse_mode="HTML",
                        disable_web_page_preview=True
                    )
                    
                    found = True
                    return
        
        if not found:
            # If we're here, we couldn't find the monitor in the handler implementation
            await message.answer(f"❌ No monitor found with ID: {monitor_id}")
            # List available monitors to help the user
            await cmd_list_coins(message)
    
    except (ImportError, AttributeError) as e:
        logger.error(f"Error accessing handler implementation: {str(e)}")
        await message.answer("❌ An error occurred trying to stop the monitor")

@monitor_router.message(Command("stop_monitor"))
async def cmd_stop_monitor(message: Message):
    """Stop all monitoring (both implementations)"""
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Stop monitors from command implementation
    chat_id = ConfigManager.get_alert_group_id()
    stopped_count = 0

    if chat_id in active_monitors:
        active_monitors[chat_id].cancel()
        del active_monitors[chat_id]
        stopped_count += 1
    
    # Stop all monitors from handler implementation
    from handlers.exchange_handlers import active_monitors as handler_monitors
    handler_stopped = 0
    
    for user_id, monitors in list(handler_monitors.items()):
        for query_id, task in list(monitors.items()):
            task.cancel()
        handler_stopped += len(monitors)
        del handler_monitors[user_id]
    
    total_stopped = stopped_count + handler_stopped
    
    # Send "Monitoring stopped" message ONLY to the admin who initiated the command
    await message.answer(f"✅ Monitoring stopped for all {total_stopped} coins")
    
    # Also log the details
    logger.info(f"Stopped {total_stopped} monitors ({stopped_count} from command impl, {handler_stopped} from handler impl)")

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

@monitor_router.message(Command("addcoin"))
async def cmd_add_coin(message: Message):
    """Add a new coin to monitor - using the same flow as monitor command"""
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
    
    # Check monitors from the admin bot implementation
    alert_group_id = ConfigManager.get_alert_group_id()
    admin_monitors = []
    
    if alert_group_id in active_monitors:
        # For backward compatibility, the admin bot implementation only stores one monitor per alert group
        coin = active_monitors[alert_group_id].get_name() if hasattr(active_monitors[alert_group_id], 'get_name') else "Unknown"
        admin_monitors.append(f"• {coin}")
    
    # Get monitors from the handlers implementation, if available
    handler_monitors = []
    try:
        from handlers.exchange_handlers import active_monitors as handler_active_monitors
        from handlers.exchange_handlers import user_queries as handler_user_queries
        
        for chat_id, monitors in handler_active_monitors.items():
            for query_id, _ in monitors.items():
                # Find the associated query information if available
                query_info = "Unknown"
                filter_mode = "all"
                min_percentage = 0.1
                
                for chat_data in handler_user_queries.values():
                    if query_id in chat_data:
                        query_info = chat_data[query_id].get('query', 'Unknown')
                        filter_mode = chat_data[query_id].get('filter_mode', 'all')
                        min_percentage = chat_data[query_id].get('min_percentage', 0.1)
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
                
                # Escape the ID tag to prevent HTML parsing issues
                handler_monitors.append(f"• {query_info} (Monitor ID: {query_id[:8]})\n  - {mode_text}\n  - Min: {min_percentage}%")
    except (ImportError, AttributeError) as e:
        logger.warning(f"Could not access handler monitors: {str(e)}")

    # Build the response message
    if not admin_monitors and not handler_monitors:
        await message.answer("⚠️ No coins are currently being monitored")
        return
    
    message_text = "🔍 Currently monitoring:\n\n"
    
    if admin_monitors:
        message_text += "Admin Bot Monitors:\n"
        message_text += "\n".join(admin_monitors)
        message_text += "\n\n"
    
    if handler_monitors:
        message_text += "Handler Bot Monitors:\n"
        message_text += "\n\n".join(handler_monitors)
        
    message_text += "\n\nCommands:\n• /stop <ID> - Stop a specific monitor\n• /stop_monitor - Stop all monitoring\n• /setmin <ID> <percentage> - Set minimum %"
    
    await message.answer(message_text)

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
    
    # Try to find the monitor in the handler implementation
    try:
        from handlers.exchange_handlers import active_monitors as handler_active_monitors
        from handlers.exchange_handlers import user_queries as handler_user_queries
        
        found = False
        
        # Check each chat's monitors
        for chat_id, monitors in handler_active_monitors.items():
            for query_id, task in list(monitors.items()):
                if query_id.startswith(monitor_id):
                    # Found the monitor, pass to handler implementation
                    from handlers.exchange_handlers import cmd_set_min_percentage as handler_setmin
                    
                    # We'll create a properly formatted message text with the original ID
                    original_text = message.text
                    message.text = f"/setmin {query_id} {min_percentage}"
                    
                    # Call the handler implementation
                    await handler_setmin(message)
                    
                    # Restore the original message text
                    message.text = original_text
                    
                    found = True
                    return
        
        if not found:
            # If we're here, we couldn't find the monitor in the handler implementation
            # Check the admin bot implementation
            alert_group_id = ConfigManager.get_alert_group_id()
            if alert_group_id in active_monitors:
                # For now, just notify that we can't set min percentage for the admin bot implementation
                await message.answer("⚠️ Setmin is only supported for multi-coin monitors. Use /stop_monitor and /monitor again to set a new percentage.")
            else:
                await message.answer(f"❌ No monitor found with ID: {monitor_id}")
                # List available monitors to help the user
                await cmd_list_coins(message)
    
    except (ImportError, AttributeError) as e:
        logger.error(f"Error accessing handler implementation: {str(e)}")
        await message.answer("❌ An error occurred trying to set the minimum percentage") 