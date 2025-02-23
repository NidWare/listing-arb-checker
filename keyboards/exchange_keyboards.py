from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_exchange_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    exchanges = ["mexc", "gate", "bitget"]
    
    for exchange in exchanges:
        builder.button(
            text=exchange.upper(),
            callback_data=f"exchange_{exchange}"
        )
    
    builder.adjust(1)
    return builder.as_markup()

def get_search_type_keyboard(exchange: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    
    builder.button(
        text="Search by Name",
        callback_data=f"search_name_{exchange}"
    )
    
    if exchange == "mexc":
        builder.button(
            text="Search by Contract",
            callback_data=f"search_contract_{exchange}"
        )
    
    builder.adjust(1)
    return builder.as_markup() 