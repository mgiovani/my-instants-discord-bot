import asyncio
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
        name='WE'RE BACK BABYYYYYYYYY /mi',
    ),
    intents=intents,
)


@bot.event
async def on_ready():
    logger.debug(f'Logged in as: {bot.user.name} - {bot.user.id}')
    synced = await bot.tree.sync()
    logger.debug(f'Synced {len(synced)} command(s)')


async def add_cogs(bot):
    await bot.add_cog(InstantClient(bot))


bot_token = os.getenv('MYINSTANTS_BOT_TOKEN')
if not bot_token:
    raise MissingBotToken

asyncio.run(add_cogs(bot))
bot.run(bot_token)
