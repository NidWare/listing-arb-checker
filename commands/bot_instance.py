from aiogram import Bot

# This will be set in admin_bot.py
admin_bot = None

def set_bot_instance(bot_instance):
    global admin_bot
    admin_bot = bot_instance
    
def get_bot_instance():
    return admin_bot 