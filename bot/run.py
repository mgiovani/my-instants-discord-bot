import os

from discord.ext import commands
from loguru import logger

from bot.client import InstantClient


bot = commands.Bot(command_prefix=commands.when_mentioned_or(">"),
                   description='Play audio from myinstants')


@bot.event
async def on_ready():
    logger.debug(f'Logged in as: {bot.user.name} - {bot.user.id}')

bot.add_cog(InstantClient(bot))
bot.run(os.getenv('MYINSTANTS_BOT_TOKEN'))
