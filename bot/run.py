import os

from discord import Activity, ActivityType, Intents
from discord.ext import commands
from loguru import logger

from bot.client import InstantClient
from bot.exceptions import MissingBotToken

intents = Intents.default()

bot = commands.Bot(
    command_prefix=commands.when_mentioned_or('>'),
    description='Play audio from myinstants',
    activity=Activity(
        type=ActivityType.listening,
        name='Discord removed my permissions, trying to fix :(',
    ),
    intents=intents,
)


@bot.event
async def on_ready():
    logger.debug(f'Logged in as: {bot.user.name} - {bot.user.id}')


bot_token = os.getenv('MYINSTANTS_BOT_TOKEN')
if not bot_token:
    raise MissingBotToken

bot.add_cog(InstantClient(bot))
bot.run(bot_token)
