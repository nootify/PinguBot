#!/usr/bin/env python
import asyncio
import logging
import os
import re
import sys
import traceback

import discord
from discord.ext import commands
from discord.utils import utcnow
from dotenv import load_dotenv

from common.utils import Icons
from models import Base, engine


class Pingu(commands.Bot):
    """The main module that runs all of Pingu.

    Commands must be created in a cog and not in here.
    """

    def __init__(
        self,
        *args,
        pingu_cogs: list[str],
        lavalink_host: str,
        lavalink_port: str,
        lavalink_password: str,
        boot_time: str,
        embed_colour: discord.Color,
        pingu_version: str,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.log = logging.getLogger("pingu")
        self.log.info("Starting instance")

        self.pingu_cogs = pingu_cogs
        self.lavalink_host = lavalink_host
        self.lavalink_port = lavalink_port
        self.lavalink_password = lavalink_password
        self.boot_time = boot_time
        self.embed_colour = embed_colour
        self.pingu_version = pingu_version

    def create_embed(self, **kwargs) -> discord.Embed:
        embed_template = discord.Embed(colour=self.embed_colour, **kwargs)
        return embed_template

    async def setup_hook(self) -> None:
        self.log.info("Connecting to database")
        async with engine.begin() as conn:
            # await conn.run_sync(Base.metadata.drop_all)
            await conn.run_sync(Base.metadata.create_all)
        # await engine.dispose()

        self.log.info("Loading 'jishaku'")
        await self.load_extension("jishaku")
        for cog in self.pingu_cogs:
            self.log.info("Loading '%s' (cogs.%s)", cog, cog)
            await self.load_extension(f"cogs.{cog}")

    async def on_ready(self):
        """Runs when the bot is ready to receive commands.

        However, the ready state can be triggered multiple times due to the way
        Discord handles connections (so don't put anything important here).
        """
        self.log.info("Instance is ready to receive commands")

    async def on_message(self, message: discord.Message) -> None:
        """Actions that are performed for any message that the bot can see."""
        # Ignore DMs
        if not message.guild:
            return

        # This makes sure the owner_id gets set and the query is only run once
        if not self.owner_id:
            await self.is_owner(message.author)

        if tiktok_link := re.search(r"https?://(www\.)?tiktok\.com/(t/|@(.*?)/)(.*?)/", message.content):
            tiktok_embed = tiktok_link.group(0).replace("tiktok.com/", "vxtiktok.com/", 1)
            await message.reply(f"[View on Tiktok]({tiktok_embed})", mention_author=False)

        # Let the library parse the text
        await super().process_commands(message)

    async def on_command_error(self, ctx: commands.Context, error) -> None:
        """Errors that occur while processing or executing a command."""
        # Errors that are unnecessary or handled locally
        ignored_errors = (
            commands.BadArgument,
            commands.CommandNotFound,
            commands.DisabledCommand,
            commands.MissingRequiredArgument,
            commands.TooManyArguments,
        )
        if isinstance(error, ignored_errors):
            self.log.debug("Ignored %s: %s", type(error).__name__, error)
            return

        error_embed = self.create_embed()
        if isinstance(error, commands.CommandOnCooldown):
            error_embed.description = (
                f"{Icons.WARN} Don't spam commands. Try again after {error.retry_after:.1f} second(s)."
            )
            await ctx.send(embed=error_embed)
        elif isinstance(error, commands.CheckFailure):
            self.log.debug("CheckFail: %s", error)
            error_embed.description = f"{Icons.ERROR} Sorry, but you don't have permission to do that."
            await ctx.send(embed=error_embed)
        # Catch unhandled exceptions from a command
        elif isinstance(error, commands.CommandError):
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)
            error_embed.description = f"{Icons.ERROR} Unexpected error occurred."
            await ctx.send(embed=error_embed)


async def main():
    load_dotenv()

    TOKEN = os.environ.get("PINGU_TOKEN")
    if not TOKEN:
        raise ValueError("Token not set in $PINGU_TOKEN")

    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(name)s: %(message)s",
        datefmt="%m-%d-%Y %I:%M:%S %p %Z",
        stream=sys.stdout,
    )
    logging.getLogger("sqlalchemy.engine.Engine").setLevel(logging.ERROR)

    settings = {
        "activity": discord.Activity(type=discord.ActivityType.watching, name="you 👀"),
        "description": "noot noot",
        "intents": discord.Intents.all(),
        "status": discord.Status.online,
        "pingu_cogs": [cog[:-3] for cog in sorted(os.listdir("./cogs")) if cog.endswith(".py")],
        "lavalink_host": os.environ.get("LAVALINK_HOST"),
        "lavalink_port": int(os.environ.get("LAVALINK_PORT")),
        "lavalink_password": os.environ.get("LAVALINK_PASSWORD"),
        "boot_time": utcnow(),
        "embed_colour": discord.Colour.from_rgb(138, 181, 252),
        "pingu_version": "2.1",
    }

    async with Pingu("%", **settings) as pingu:
        await pingu.start(TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
