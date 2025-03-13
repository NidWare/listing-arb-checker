from aiogram import Bot

# This will be set in bot.py
bot = None

def set_bot_instance(bot_instance):
    global bot
    bot = bot_instance
    
def get_bot_instance():
    return bot 