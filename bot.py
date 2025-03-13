import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from middlewares.message_logging import MessageLoggingMiddleware
from config.config_manager import ConfigManager
from commands import basic_router, monitor_router
from commands.bot_instance import set_bot_instance

# Configure logging with more detail
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Main bot instance (formerly admin_bot)
bot = Bot(
    token=ConfigManager.get_bot_token(),
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)

# Make bot instance available to commands
set_bot_instance(bot)

# Create dispatcher
dp = Dispatcher()

# Register message logging middleware
dp.message.middleware(MessageLoggingMiddleware())

# Register routers - important to register monitor_router first to give it priority
dp.include_router(monitor_router)
dp.include_router(basic_router)

async def start_bot():
    """Start the bot in polling mode"""
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting bot in polling mode...")
        
        me = await bot.get_me()
        logger.info(f"Bot started successfully! Username: @{me.username}")
        
        await dp.start_polling(bot, allowed_updates=[
            "message",
            "callback_query"
        ])
    except Exception as e:
        logger.error(f"Critical error during bot startup: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("Bot stopped")
        await bot.session.close()

async def main():
    try:
        # Run bot
        await start_bot()
    except Exception as e:
        logger.error(f"Error running bot: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.critical(f"Unhandled exception: {str(e)}", exc_info=True) 