import logging
from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command
from config.config_manager import ConfigManager

# Configure logging
logger = logging.getLogger(__name__)

basic_router = Router()

@basic_router.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id in ConfigManager.get_admin_user_ids():
        await message.answer(
            "Welcome to the Admin Bot! 🛡\n\n"
            "Available commands:\n"
            "/status - Check system status\n"
            "/stats - View monitoring statistics\n\n"
            "🔍 Multi-Coin Monitoring:\n"
            "/addcoin [coin] - Add a new coin to monitor\n"
            "/listcoins - Show all monitored coins\n"
            "/stop [code] - Stop monitoring a specific coin\n"
            "/stop_monitor - Stop all monitoring\n"
            "/setmin [code] [percentage] - Set minimum arbitrage %\n"
        )
    else:
        await message.answer("⚠️ You don't have permission to use this bot.")

@basic_router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id in ConfigManager.get_admin_user_ids():
        from commands.monitor_commands import active_monitors as cmd_monitors
        from handlers.exchange_handlers import active_monitors as handler_monitors
        
        # Count total monitors from both implementations
        total_monitors = 0
        
        # Count monitors from handler implementation (multiple coins per user)
        handler_coin_count = 0
        for user_monitors in handler_monitors.values():
            handler_coin_count += len(user_monitors)
            
        # Count monitors from command implementation
        cmd_coin_count = len(cmd_monitors)
        
        total_monitors = handler_coin_count + cmd_coin_count
        
        await message.answer(
            "📊 System Statistics:\n\n"
            f"- Active Monitors: {total_monitors} total\n"
            f"  • Handler Implementation: {handler_coin_count} coins\n"
            f"  • Command Implementation: {cmd_coin_count} coins\n"
            "- Uptime: Active"
        )
    else:
        await message.answer("⚠️ You don't have permission to use this command.")

# We need to make sure this catch-all handler doesn't interfere with other command handlers
# To do that, we'll check if the message starts with a command prefix and ignore it
@basic_router.message(lambda message: not message.text.startswith('/'))
async def debug_chat_info(message: Message):
    """Debug handler to log chat information"""
    # Skip if waiting for min percentage input (will be handled by monitor_commands)
    from commands.monitor_commands import user_queries
    if message.from_user.id in user_queries:
        return
        
    logger.info(
        f"Debug Chat Info:\n"
        f"Chat ID: {message.chat.id}\n"
        f"Chat Type: {message.chat.type}\n"
        f"Chat Title: {message.chat.title if message.chat.title else 'N/A'}\n"
        f"Username: {message.chat.username if hasattr(message.chat, 'username') else 'N/A'}\n"
        f"Message From: {message.from_user.full_name} (ID: {message.from_user.id})"
    ) 