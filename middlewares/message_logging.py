from typing import Any, Awaitable, Callable, Dict
from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
import logging

logger = logging.getLogger(__name__)

class MessageLoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: Message,
        data: Dict[str, Any]
    ) -> Any:
        # Log message details
        user = event.from_user
        if event.chat.type == "supergroup":
            return
        
        if user:
            logger.info(
                f"Message received - {event.chat.type}"
                f"User: {user.full_name} (ID: {user.id}), "
                f"Chat: {event.chat.type} (ID: {event.chat.id}), "
                f"Text: {event.text if event.text else '<no text>'}, "
                f"Content Type: {event.content_type}, "
                f"Bot: {event.bot.id}"
            )
        
        # Continue processing the message
        return await handler(event, data) 