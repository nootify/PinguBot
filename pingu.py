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

from common.settings import Icons, Settings
from db import db


class Pingu(commands.Bot):
    """The main module that runs all of Pingu.

    Commands must be created in a cog and not in here.
    """

    def __init__(self, constants: Settings):
        self.boot_time = datetime.utcnow()

        # This avoids naming conflicts with attributes in commands.Bot
        self.pingu_constants = constants
        self.pingu_activity = self.pingu_constants.DEFAULT_ACTIVITY
        self.pingu_description = self.pingu_constants.DEFAULT_DESCRIPTION
        self.pingu_prefix = self.pingu_constants.DEFAULT_PREFIX
        self.pingu_status = self.pingu_constants.DEFAULT_STATUS
        self.pingu_version = self.pingu_constants.VERSION

        self.embed_colour = self.pingu_constants.EMBED_COLOUR

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
            for filename in filenames:
                if filename.endswith(".py"):
                    cog_name = os.path.splitext(filename)[0]  # Trim file extension
                    self.log.info("Loading %s module", cog_name)
                    self.load_extension(f"cogs.{cog_name}")

    async def on_ready(self):
        """Runs when the bot is ready to receive commands.

        However, the ready state can be triggered multiple times due to the
        way Discord handles connections.
        """
        self.log.info("Instance is ready to receive commands")

    async def on_message(self, message):
        """Actions that are performed for any message that the bot can see."""
        # Ignore DMs
        if not message.guild:
            return

        # This makes sure the owner_id gets set and the query is only run once
        if not self.owner_id:
            await self.is_owner(message.author)

        # Let the library parse the text
        await super().process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error):
        """Errors that occur while processing or executing a command."""
        # Errors that are unnecessary or handled locally
        ignored_errors = (
            commands.BadArgument,
            commands.CheckFailure,
            commands.CommandNotFound,
            commands.DisabledCommand,
            commands.MissingRequiredArgument,
            commands.TooManyArguments,
        )
        if isinstance(error, ignored_errors):
            self.log.debug("Ignored %s: %s", type(error).__name__, error)
            return

        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"{Icons.WARN} Don't spam commands. Try again after {error.retry_after:.1f} second(s).")
            return

        # Catch unhandled exceptions from a command
        if isinstance(error, commands.CommandError):
            self.log.error("%s: %s", type(error).__name__, error)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
            await ctx.send(f"{Icons.ERROR} Unexpected error occurred.")


async def setup_db(db: Gino, db_url: str):
    """Helper function to setup PostgreSQL db."""
    async with db.with_bind(db_url) as engine:
        await db.gino.create_all(bind=engine)


constants = Settings()


if __name__ == "__main__":
    LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    TIMESTAMP_FORMAT = "%m-%d-%Y %I:%M:%S %p %Z"
    logFormat = logging.Formatter(fmt=LOG_FORMAT, datefmt=TIMESTAMP_FORMAT)
    logging.basicConfig(
        level=logging.INFO,
        format=LOG_FORMAT,
        datefmt=TIMESTAMP_FORMAT,
        stream=sys.stdout,
    )

    if not constants.TOKEN:
        raise ValueError("Token is not set in $PINGU_TOKEN")

    pingu = Pingu(constants)
    asyncio.get_event_loop().run_until_complete(setup_db(db, constants.POSTGRES_URL))
    pingu.run(constants.TOKEN)
