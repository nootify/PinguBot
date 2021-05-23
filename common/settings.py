import os
from enum import Enum

import discord
from dotenv import load_dotenv


load_dotenv()


class Settings:
    __slots__ = ()

    DEFAULT_ACTIVITY = discord.Activity(type=discord.ActivityType.watching, name="Pingu in the City")
    DEFAULT_DESCRIPTION = "noot noot"
    DEFAULT_PREFIX = "%"
    DEFAULT_STATUS = discord.Status.online

    EMBED_COLOUR = discord.Colour.from_rgb(138, 181, 252)

    # Docker service name hosting the Lavalink instance
    LAVALINK_HOST = "audio"
    LAVALINK_PORT = 2333
    LAVALINK_PASSWORD = os.environ.get("LAVALINK_PASSWORD")
    LAVALINK_REGION = os.environ.get("LAVALINK_REGION")

    # Docker service name hosting the PostgreSQL instance
    POSTGRES_HOST = "db"
    POSTGRES_PORT = 5432
    POSTGRES_DATABASE = os.environ.get("POSTGRES_DB")
    POSTGRES_USER = os.environ.get("POSTGRES_USER")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD")
    POSTGRES_URL = (
        f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DATABASE}"
    )

    TOKEN = os.environ.get("PINGU_TOKEN")
    VERSION = "0.0.5"


class Icons(Enum):
    ALERT = ":information_source:"
    ERROR = ":no_entry:"
    HMM = ":eyes:"
    SUCCESS = ":ballot_box_with_check:"
    WARN = ":warning:"

    def __str__(self):
        return str(self.value)
