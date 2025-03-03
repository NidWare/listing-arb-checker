import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from middlewares.message_logging import MessageLoggingMiddleware
from config.config_manager import ConfigManager
from commands import basic_router, monitor_router
from commands.bot_instance import set_bot_instance

# Configure logging
logger = logging.getLogger(__name__)

# Admin bot instance
admin_bot = Bot(
    token=ConfigManager.get_admin_bot_token(),
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

# Make bot instance available to commands
set_bot_instance(admin_bot)

# Create dispatcher
admin_dp = Dispatcher()

# Register message logging middleware
admin_dp.message.middleware(MessageLoggingMiddleware())

# Register routers - important to register monitor_router first to give it priority
admin_dp.include_router(monitor_router)
admin_dp.include_router(basic_router)

async def start_admin_bot():
    """Start the admin bot in polling mode"""
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