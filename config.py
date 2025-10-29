import pytz
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from environs import Env

MSK = pytz.timezone("Europe/Moscow")

env = Env()
env.read_env('.env')

TOKEN = env.str('TOKEN')
CHAT_ID = env.int('CHAT_ID')
ADMIN_IDS = env.list('ADMIN_IDS')
bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())