import logging
import platform
import sys

import discord
from discord.ext import commands

import bot


# Logging module to be used in every other cog, including this one
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s] [%(levelname)s] %(module)s: %(message)s',
                    datefmt='%m/%d/%Y %I:%M:%S%p',
                    filename='pingu.log',
                    filemode='w')
consoleLogFormat = logging.Formatter('[%(asctime)s] [%(levelname)s] %(module)s: %(message)s')
consoleLogger = logging.StreamHandler(sys.stdout)
consoleLogger.setFormatter(consoleLogFormat)
logging.getLogger().addHandler(consoleLogger)

# Instantiate Pingu, apply default values, and load the default modules on startup
pingu = commands.Bot(command_prefix=bot.default['prefix'], description=bot.default['desc'])
pingu.default = bot.default
pingu.current = {'activity': None, 'desc': None, 'prefix': None, 'status': None}
pingu.icons = {'fail': ':x:', 'info': ':information_source:', 'success': ':white_check_mark:'}
pingu.njit_course_schedules = {}

# Loads the specified modules located in the cogs directory
for cog in bot.cogs:
    pingu.load_extension(f'cogs.{cog}')


@pingu.event
async def on_ready():
    """Prints information about the token being used, simple statistics of the bot being used,
    and the versions of the dependencies being used. Also sets one other default parameter of the bot.
    """
    total_servers = len(pingu.guilds)
    total_users = len(set(pingu.get_all_members()))
    print('---Initial Startup Information---')
    print(f'[ Bot Information ]\n'
          f'- Username: {pingu.user}\n'
          f'- ID: {pingu.user.id}')
    print(f'[ Connected To ]\n'
          f'- {total_servers} servers\n'
          f'- {total_users} unique users')
    print(f'[ Dependencies ]\n'
          f'- Python v{platform.python_version()}\n'
          f'- discord.py[voice] v{discord.__version__}\n'
          f'- PinguBot v{bot.version}')
    print('---------------------------------')

    await pingu.change_presence(status=pingu.default['status'], activity=pingu.default['activity'])


@pingu.event
async def on_message(message):
    # Ignore messages from itself, other bots, or from DMs
    if message.author.bot or message.guild is None:
        return

    # Pass information to other cogs
    await pingu.process_commands(message)


if __name__ == '__main__':
    pingu.run(bot.token)
