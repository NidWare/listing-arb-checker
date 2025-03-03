import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from handlers.exchange_handlers import router as exchange_router
from config.config_manager import ConfigManager
from services.exchange_service import ExchangeService
from middlewares.message_logging import MessageLoggingMiddleware
from admin_bot import start_admin_bot

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

# Bot instance with enhanced error handling
bot = Bot(
    token=ConfigManager.get_bot_token(),
    default=DefaultBotProperties(
        parse_mode=ParseMode.HTML
    )
)
dp = Dispatcher()

# Register message logging middleware
dp.message.middleware(MessageLoggingMiddleware())

# Register routers
dp.include_router(exchange_router)

# Create a single instance of ExchangeService
exchange_service = ExchangeService()

async def start_main_bot():
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        logger.info("Starting main bot in polling mode...")
        
        # Additional startup logging
        me = await bot.get_me()
        logger.info(f"Main bot started successfully! Username: @{me.username}")
        
        # Start polling with enhanced error handling
        await dp.start_polling(bot, allowed_updates=[
            "message",
            "callback_query",
            "inline_query"
        ])
    except Exception as e:
        logger.error(f"Critical error during main bot startup: {str(e)}", exc_info=True)
        raise
    finally:
        logger.info("Main bot stopped")
        await exchange_service.close()
        await bot.session.close()

async def main():
    try:
        # Run both bots concurrently
        await asyncio.gather(
            start_main_bot(),
            start_admin_bot()
        )
    except Exception as e:
        logger.error(f"Error running bots: {str(e)}", exc_info=True)
        raise

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bots stopped by user")
    except Exception as e:
        logger.critical(f"Unhandled exception: {str(e)}", exc_info=True) 