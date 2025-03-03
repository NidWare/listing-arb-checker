import asyncio
import logging
import os
from aiogram import Bot, Dispatcher, Router
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.filters import Command
from config.config_manager import ConfigManager
from middlewares.message_logging import MessageLoggingMiddleware
from handlers.exchange_handlers import monitor_prices

# Configure logging
logger = logging.getLogger(__name__)

# Admin bot instance
admin_bot = Bot(
    token=ConfigManager.get_admin_bot_token(),
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

# Create dispatcher and router
admin_dp = Dispatcher()
admin_router = Router()

# Store active monitoring tasks
active_monitors = {}

# Store temporary user queries while waiting for min percentage input
user_queries = {}

# Register message logging middleware
admin_dp.message.middleware(MessageLoggingMiddleware())

@admin_router.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id in ConfigManager.get_admin_user_ids():
        await message.answer(
            "Welcome to the Admin Bot! 🛡\n\n"
            "Available commands:\n"
            "/status - Check system status\n"
            "/stats - View monitoring statistics\n"
            "/monitor [coin] - Start monitoring a coin\n"
            "/stop_monitor - Stop monitoring"
        )
    else:
        await message.answer("⚠️ You don't have permission to use this bot.")

@admin_router.message(Command("status"))
async def cmd_status(message: Message):
    if message.from_user.id in ConfigManager.get_admin_user_ids():
        # Add your status check logic here
        await message.answer(
            "🟢 System Status:\n\n"
            "- Admin Bot: Online\n"
            "- Main Bot: Online\n"
            "- Exchange Service: Active"
        )
    else:
        await message.answer("⚠️ You don't have permission to use this command.")

@admin_router.message(Command("stats"))
async def cmd_stats(message: Message):
    if message.from_user.id in ConfigManager.get_admin_user_ids():
        # Add your statistics gathering logic here
        await message.answer(
            "📊 System Statistics:\n\n"
            f"- Active Monitors: {len(active_monitors)}\n"
            "- Total Requests: 0\n"
            "- Uptime: 0h 0m"
        )
    else:
        await message.answer("⚠️ You don't have permission to use this command.")

@admin_router.message(Command("monitor"))
async def cmd_monitor(message: Message):
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
    
@admin_router.message(Command("cancel"))
async def cmd_cancel(message: Message):
    """Cancel the current monitoring setup process"""
    user_id = message.from_user.id
    
    if user_id in user_queries:
        # Remove the query from waiting list
        coin = user_queries.pop(user_id)
        await message.answer(f"✅ Monitoring setup for {coin} has been cancelled.")
    else:
        await message.answer("No monitoring setup in progress to cancel.")

@admin_router.message(lambda message: message.from_user.id in user_queries)
async def handle_min_percentage(message: Message):
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

        # Send initial message
        await message.bot.send_message(
            chat_id,
            f"🔍 Starting price monitoring for {coin} with minimum arbitrage of {min_percentage}%...",
            message_thread_id=topic_id
        )

        # Start new monitoring task with the custom min_arbitrage_percentage
        task = asyncio.create_task(monitor_prices(chat_id, coin, admin_bot, min_percentage))
        active_monitors[chat_id] = task

        await message.bot.send_message(
            chat_id,
            f"✅ Monitoring started for {coin}!\n\n"
            f"I will notify you when there are arbitrage opportunities with >{min_percentage}% difference.\n"
            "Use /stop_monitor command to stop monitoring.",
            message_thread_id=topic_id
        )
        
        # Also send confirmation to the admin
        await message.answer(f"✅ Started monitoring {coin} with minimum arbitrage set to {min_percentage}%")

    except Exception as e:
        logger.error(f"Error starting monitoring: {str(e)}", exc_info=True)
        # Try to send error message to the user who initiated the command
        await message.answer(f"❌ Error starting monitoring: {str(e)}")

@admin_router.message(Command("stop_monitor"))
async def cmd_stop_monitor(message: Message):
    if message.from_user.id not in ConfigManager.get_admin_user_ids():
        await message.answer("⚠️ You don't have permission to use this command.")
        return

    # Use the supergroup ID for monitoring
    chat_id = ConfigManager.get_alert_group_id()
    topic_id = int(os.getenv("TOPIC_ID", "1"))

    if chat_id in active_monitors:
        active_monitors[chat_id].cancel()
        del active_monitors[chat_id]
        await message.bot.send_message(
            chat_id,
            "✅ Monitoring stopped",
            message_thread_id=topic_id
        )
    else:
        await message.bot.send_message(
            chat_id,
            "❌ No active monitoring found",
            message_thread_id=topic_id
        )

@admin_router.message()
async def debug_chat_info(message: Message):
    """Debug handler to log chat information"""
    # Skip if waiting for min percentage input
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

# Register router
admin_dp.include_router(admin_router)

async def start_admin_bot():
    try:
        await admin_bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting admin bot in polling mode...")
        
        me = await admin_bot.get_me()
        logger.info(f"Admin bot started successfully! Username: @{me.username}")
        
        await admin_dp.start_polling(admin_bot, allowed_updates=[
            "message",
            "callback_query"
        ])
    except Exception as e:
        logger.error(f"Critical error during admin bot startup: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("Admin bot stopped")
        await admin_bot.session.close() 