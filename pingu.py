#!/usr/bin/env python
import asyncio
import logging
import os
import sys
import traceback
from datetime import datetime

import discord
from discord.ext import commands
from gino import Gino

from db import db
from common.settings import Settings


class Pingu(commands.Bot):
    """The main module that runs all of Pingu.
    Commands must be created in a cog and not in here.
    """

    def __init__(self, constants: Settings):
        self.boot_time = datetime.now()

        # This avoids naming conflicts with attributes in commands.Bot
        self.pingu_constants = constants
        self.pingu_activity = self.pingu_constants.DEFAULT_ACTIVITY
        self.pingu_description = self.pingu_constants.DEFAULT_DESCRIPTION
        self.pingu_prefix = self.pingu_constants.DEFAULT_PREFIX
        self.pingu_status = self.pingu_constants.DEFAULT_STATUS
        self.pingu_version = self.pingu_constants.VERSION

        self.embed_colour = self.pingu_constants.EMBED_COLOUR
        self.icons = self.pingu_constants.ICONS

        self.lavalink_host = self.pingu_constants.LAVALINK_HOST
        self.lavalink_port = self.pingu_constants.LAVALINK_PORT
        self.lavalink_password = self.pingu_constants.LAVALINK_PASSWORD
        self.lavalink_region = self.pingu_constants.LAVALINK_REGION

        self.postgres_url = self.pingu_constants.POSTGRES_URL

        self.log = logging.getLogger("pingu")
        self.log.info("Starting instance")

        # Required to get member info
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(
            command_prefix=self.pingu_prefix,
            description=self.pingu_description,
            activity=self.pingu_activity,
            status=self.pingu_status,
            intents=intents,
        )

        # Load debugging toolset
        self.log.info("Loading jishaku module")
        self.load_extension("jishaku")

        # Load all of the modules
        for dirpath, dirnames, filenames in os.walk("./cogs"):
            for file in filenames:
                cog = file[:-3]  # Trim .py file extension
                self.log.info("Loading %s module", cog)
                self.load_extension(f"cogs.{cog}")

    async def on_ready(self):
        """Runs when the bot is ready to receive commands.

        However, the ready state can be triggered multiple times due to the
        way Discord handles connections.
        """
        self.log.info("Instance is ready to receive commands")

    async def on_message(self, message):
        """Actions that are performed for any message that the bot can see."""
        # Ignore messages from DMs
        if not message.guild:
            return

        # This makes sure the owner_id gets set and the query is only run once
        if not self.owner_id:
            await self.is_owner(message.author)

        # Allow information to pass through
        await super().process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error):
        """Errors that occur while processing or executing a command."""
        # Errors that are unnecessary or are handled locally in each cog
        ignored_errors = (
            commands.CheckFailure,
            commands.CommandNotFound,
            commands.MissingRequiredArgument,
            commands.TooManyArguments,
        )
        if isinstance(error, ignored_errors):
            self.log.debug("%s: %s", type(error).__name__, error)
            return
        # Overridden global error handling
        error_icon = self.icons["fail"]
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"{error_icon} Stop! You violated the law. " f"Wait {error.retry_after:.02f} seconds.")
            return
        if isinstance(error, commands.DisabledCommand):
            await ctx.send(f"{error_icon} This command has been disabled for now.")
            return
        # Catch errors that have been specified to be local only
        if hasattr(ctx, "local_error_only"):
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{error_icon} {error}")
            return
        # Catch-all formatter for any CommandError related messages
        if isinstance(error, commands.CommandError):
            self.log.error("%s: %s", type(error).__name__, error)
            await ctx.send("Something went wrong while processing this command.")
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
            return


async def setup_db(db_url: str, db: Gino):
    """Helper function to manage PostgreSQL database."""
    async with db.with_bind(db_url) as engine:
        await db.gino.create_all(bind=engine)


constants = Settings()


if __name__ == "__main__":
    # Logs events to the log file and the console
    LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    TIMESTAMP_FORMAT = "%m-%d-%Y %I:%M:%S %p %Z"
    logFormat = logging.Formatter(fmt=LOG_FORMAT, datefmt=TIMESTAMP_FORMAT)
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        datefmt=TIMESTAMP_FORMAT,
        stream=sys.stdout,
    )

    # Setup environment vars
    if not constants.TOKEN:
        raise ValueError("Token was not specified in $PINGU_TOKEN")

    pingu = Pingu(constants)
    asyncio.get_event_loop().run_until_complete(setup_db(constants.POSTGRES_URL, db))
    pingu.run(constants.TOKEN)
