import os
from enum import Enum

import discord
from dotenv import load_dotenv


load_dotenv()


class Settings:
    __slots__ = ()

    DEFAULT_ACTIVITY = discord.Activity(type=discord.ActivityType.watching, name="you 👀")
    DEFAULT_DESCRIPTION = "noot noot"
    DEFAULT_PREFIX = "%"
    DEFAULT_STATUS = discord.Status.online

    EMBED_COLOUR = discord.Colour.from_rgb(138, 181, 252)

    LOG_FORMAT = "[%(asctime)s] [%(levelname)s] %(name)s: %(message)s"
    TIMESTAMP_FORMAT = "%m-%d-%Y %I:%M:%S %p %Z"

    LAVALINK_HOST = os.environ.get("LAVALINK_HOST")
    LAVALINK_PORT = int(os.environ.get("LAVALINK_PORT"))
    LAVALINK_PASSWORD = os.environ.get("LAVALINK_PASSWORD")
    LAVALINK_REGION = os.environ.get("LAVALINK_REGION")

    POSTGRES_HOST = os.environ.get("POSTGRES_HOST")
    POSTGRES_PORT = os.environ.get("POSTGRES_PORT")
    POSTGRES_DB = os.environ.get("POSTGRES_DB")
    POSTGRES_USER = os.environ.get("POSTGRES_USER")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")
    POSTGRES_URL = (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    VERSION = "1.0"


class Icons(Enum):
    ALERT = ":information_source:"
    ERROR = ":no_entry:"
    HMM = ":eyes:"
    SUCCESS = ":ballot_box_with_check:"
    WARN = ":warning:"

    def __str__(self):
        return str(self.value)
