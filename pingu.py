#!/usr/bin/env python
"""To use Pingu, you must first set your token in the $PINGU_TOKEN environment variable.
The easiest way to do this persistently is to create a .env file and store it there.
Afterwards, run pingu.py normally as you would any Python script.
"""
import asyncio
import logging
import platform
import sys
import traceback

import asyncpg
import discord
from discord.ext import commands

import settings


class Pingu(commands.Bot):
    """The main module that run all of Pingu.
    Commands must be created in a cog and not in here.
    """
    def __init__(self):
        super().__init__(command_prefix=settings.default["prefix"],
                         description=settings.default["desc"])
        self.default = settings.default
        self.current = {"activity": self.default["activity"],
                        "desc": self.default["desc"],
                        "prefix": self.default["prefix"],
                        "status": self.default["status"]}
        self.icons = {"fail": ":x:",
                      "info": ":information_source:",
                      "success": ":white_check_mark:"}
        self.log = logging.getLogger("pingu")
        self.log.info("Started Pingu instance")

        # Load the default modules as specified in settings.py
        for cog in settings.COGS:
            self.log.info("Loading cog module '%s'", cog)
            self.load_extension(f"cogs.{cog}")

    async def on_ready(self):
        """Prints debug information about the token, bot usage, and the dependencies being used.
        Also sets the bot's presence on Discord.

        Warning: The ready state can be triggered multiple times due to the way the library
        handles connections.
        """
        await super().change_presence(status=self.current["status"],
                                      activity=self.current["activity"])
        total_servers = len(super().guilds)
        total_users = len(set(super().get_all_members()))
        debug_output = (f"--- [ General Information ] ---\n"
                        f"[ Login ]\n"
                        f"Logged in as:\n"
                        f"- Username: {super().user}\n"
                        f"- ID: {super().user.id}\n"
                        f"[ Connections ]\n"
                        f"Currently connected to:\n"
                        f"- {total_servers} servers\n"
                        f"- {total_users} unique users\n"
                        f"[ Dependencies ]\n"
                        f"Library versions being used:\n"
                        f"- Python v{platform.python_version()}\n"
                        f"- discord.py[voice] v{discord.__version__}\n"
                        f"- Pingu v{settings.VERSION}\n"
                        f"---------------------------------")
        self.log.debug(debug_output)
        self.log.info("Instance is ready to receive commands")

    async def on_message(self, message):
        """Actions that are performed for any message that the bot can see."""
        # Ignore messages from itself, other bots, or from DMs
        # Note: this can't catch users that are selfbotting
        if message.author.bot or message.guild is None:
            return

        # Allow information to pass through
        await super().process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error): # pylint: disable=arguments-differ
        """Errors that occur while processing or executing a command."""
        # Errors that are unnecessary or are handled locally in each cog
        ignored_errors = (commands.CommandNotFound, commands.MissingRequiredArgument)
        if isinstance(error, ignored_errors):
            self.log.debug("%s: %s", type(error).__name__, error)
            return
        # Overridden global error handling
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"{self.icons['fail']} Stop! You violated the law. "
                           f"Wait {error.retry_after:.02f} seconds.")
            return
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.send(f"{self.icons['fail']} I'm missing the "
                           f"`{'`, `'.join(error.missing_perms)}` permission(s) for the server.")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{self.icons['fail']} {error}")
            return
        # A catch-all formatter for any CommandError related messages
        if isinstance(error, commands.CommandError):
            self.log.info("%s: %s", type(error).__name__, error)
            await ctx.send(f"{self.icons['fail']} {error}. Check the logs for more details.")
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
            return


async def attach_db(bot: Pingu):
    """Helper function to attach a PostgreSQL connection to Pingu.
    No paramaters are passed in because it uses the ~/.pgpass file.
    """
    bot.db = await asyncpg.create_pool()


if __name__ == "__main__":
    # Logs events to the log file and the console
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

    # Check for the token
    if settings.TOKEN is None:
        raise ValueError("Token was not specified in $PINGU_TOKEN")

    # This enables discord.py to handle the bot, while the DB connection is left to the dev
    pingu = Pingu()
    db_loop = asyncio.get_event_loop()
    db_loop.run_until_complete(attach_db(pingu))
    pingu.run(settings.TOKEN)
