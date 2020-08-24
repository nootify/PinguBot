#!/usr/bin/env python
"""To use Pingu, you must first set your token in the $PINGU_TOKEN environment variable.
The easiest way to do this persistently is to create a .env file and store it there.
Afterwards, run pingu.py normally as you would any Python script.
"""
import asyncio
import logging
import sys
import traceback
from datetime import datetime

import asyncpg
import discord
from discord.ext import commands

import settings


class Pingu(commands.Bot):
    """The main module that run all of Pingu.
    Commands must be created in a cog and not in here.
    """
    def __init__(self):
        self.boot_time = datetime.now()
        self.default = settings.default
        self.current = {"activity": self.default["activity"],
                        "desc": self.default["desc"],
                        "prefix": self.default["prefix"],
                        "status": self.default["status"]}
        self.embed_colour = discord.Colour.from_rgb(138, 181, 252)
        self.icons = {"fail": ":x:",
                      "info": ":information_source:",
                      "success": ":white_check_mark:"}
        self.log = logging.getLogger("pingu")
        self.log.info("Starting instance")

        super().__init__(command_prefix=self.current["prefix"],
                         description=self.current["desc"],
                         activity=self.current["activity"],
                         status=self.current["status"])

        # Important debugging tools
        self.log.info("Loading jishaku")
        self.load_extension("jishaku")

        # Load the default modules as specified in settings.py
        for cog in settings.COGS:
            self.log.info("Loading cog module '%s'", cog)
            self.load_extension(f"cogs.{cog}")

    async def on_ready(self):
        """Warning: The ready state can be triggered multiple times due to the
        way Discord handles connections.
        """
        self.log.debug("Make sure nothing important runs in here")
        self.log.info("Instance is ready to receive commands")

    async def on_message(self, message):
        """Actions that are performed for any message that the bot can see."""
        # Ignore messages from itself, other bots, or from DMs
        # Note: this can't catch users that are selfbotting
        if message.author.bot or not message.guild:
            return

        # This makes sure the owner_id gets set and the query is only run once
        if not self.owner_id:
            await self.is_owner(message.author)

        # Allow information to pass through
        await super().process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error): # pylint: disable=arguments-differ
        """Errors that occur while processing or executing a command."""
        # Errors that are unnecessary or are handled locally in each cog
        ignored_errors = (commands.CheckFailure, commands.CommandNotFound,
                          commands.MissingRequiredArgument, commands.TooManyArguments)
        if isinstance(error, ignored_errors):
            self.log.debug("%s: %s", type(error).__name__, error)
            return
        # Overridden global error handling
        error_icon = self.icons["fail"]
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"{error_icon} Stop! You violated the law. "
                           f"Wait {error.retry_after:.02f} seconds.")
            return
        if isinstance(error, commands.BotMissingPermissions):
            missing = "`, `".join(error.missing_perms)
            await ctx.send(
                f"{error_icon} I'm missing the `{missing}` permission(s) for the server.")
            return
        if isinstance(error, commands.DisabledCommand):
            await ctx.send(f"{error_icon} This command has been disabled for now.")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{error_icon} {error}")
            return
        # A catch-all formatter for any CommandError related messages
        if isinstance(error, commands.CommandError):
            self.log.info("%s: %s", type(error).__name__, error)
            await ctx.send(f"{error_icon} {error} Check the logs for more details.")
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
            return


async def attach_db(bot: Pingu):
    """Helper function to attach a PostgreSQL connection to Pingu.
    Parameters should be passed in using environment variables.
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
    if not settings.TOKEN:
        raise ValueError("Token was not specified in $PINGU_TOKEN")

    # This enables discord.py to handle the bot, while the DB connection is left to the dev
    pingu = Pingu()
    db_loop = asyncio.get_event_loop()
    db_loop.run_until_complete(attach_db(pingu))
    pingu.run(settings.TOKEN)
