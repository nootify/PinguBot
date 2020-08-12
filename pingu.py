#!/usr/bin/env python
"""To use Pingu, you must first set your token in the $PINGU_TOKEN enviornment variable.
The easiest way to do this persistently is to use setup.sh and create a .env file.
Then run pingu.py normally as you would any Python script.
"""
import logging
import platform
import sys
import traceback

import discord
from discord.ext import commands

import data

# Main logger to log events to the file and console
FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
DATEFMT = "%m-%d-%Y %I:%M:%S %p"
logFormat = logging.Formatter(fmt=FORMAT, datefmt=DATEFMT)
logging.basicConfig(level=logging.INFO,
                    format=FORMAT,
                    datefmt=DATEFMT,
                    filename="pingu.log",
                    filemode="w")
consoleLogger = logging.StreamHandler(sys.stdout)
consoleLogger.setFormatter(logFormat)
logging.getLogger().addHandler(consoleLogger)

# Return logging information from this module
log = logging.getLogger("pingu")
log.info("Starting Pingu instance")

# Instantiate Pingu and apply default values
pingu = commands.Bot(command_prefix=data.default["prefix"], description=data.default["desc"])
pingu.default = data.default
pingu.current = {"activity": pingu.default["activity"],
                 "desc": pingu.default["desc"],
                 "prefix": pingu.default["prefix"],
                 "status": pingu.default["status"]}
pingu.icons = {"fail": ":x:",
               "info": ":information_source:",
               "success": ":white_check_mark:"}
pingu.njit_course_schedules = {}

# Load the specified default modules
for cog in data.COGS:
    log.info("Loading cog module '%s'", cog)
    pingu.load_extension(f"cogs.{cog}")

@pingu.event
async def on_ready():
    """Prints information about the token being used, simple statistics of the bot
    being used, and the versions of the dependencies being used. Also sets one other
    default parameter of the bot.
    """
    total_servers = len(pingu.guilds)
    total_users = len(set(pingu.get_all_members()))
    debug_output = (f"--- [ General Information ] ---\n"
                    f"[ Login ]\n"
                    f"Logged in as:\n"
                    f"- Username: {pingu.user}\n"
                    f"- ID: {pingu.user.id}\n"
                    f"[ Connections ]\n"
                    f"Currently connected to:\n"
                    f"- {total_servers} servers\n"
                    f"- {total_users} unique users\n"
                    f"[ Dependencies ]\n"
                    f"Library versions being used:\n"
                    f"- Python v{platform.python_version()}\n"
                    f"- discord.py[voice] v{discord.__version__}\n"
                    f"- Pingu v{data.VERSION}\n"
                    f"---------------------------------")
    log.debug(debug_output)

    await pingu.change_presence(status=pingu.current["status"], activity=pingu.current["activity"])
    log.info("Instance is ready to receive commands")

@pingu.event
async def on_message(message):
    """Actions that are performed for any message that the bot can see."""
    # Ignore messages from itself, other bots, or from DMs (can't catch users that are selfbotting)
    if message.author.bot or message.guild is None:
        return

    # Allow information to pass through
    await pingu.process_commands(message)

@pingu.event
async def on_command_error(ctx, error):
    """Errors that occur while processing or executing a command."""
    # Errors that are unnecessary or are handled locally in each cog
    ignored_errors = (commands.CommandNotFound, commands.MissingRequiredArgument)
    if isinstance(error, ignored_errors):
        log.debug("%s: %s", type(error).__name__, error)
        return
    # Overridden global error handling
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"{pingu.icons['fail']} Stop! You violated the law."
                       f" Wait {error.retry_after:.02f} seconds.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send(f"{pingu.icons['fail']} I'm missing the `{'`, `'.join(error.missing_perms)}`"
                       f"permission(s) for the server.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"{pingu.icons['fail']} {error}")
    # A catch-all formatter to add an "x" icon in front of unspecified CommandError messages
    elif isinstance(error, commands.CommandError):
        log.info("%s: %s", type(error).__name__, error)
        await ctx.send(f"{pingu.icons['fail']} {error}")
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

if __name__ == "__main__":
    if data.TOKEN is None:
        raise ValueError("Token was not specified in $PINGU_TOKEN")
    pingu.run(data.TOKEN)
