"""This module stores all of the default settings of Pingu.
Also retrieves the token stored in the .env file.
"""

import os

import discord
from dotenv import load_dotenv

load_dotenv()

default = {"activity": discord.Activity(type=discord.ActivityType.watching,
                                        name="Pingu in the City"),
           "desc": "Noot Noot at your service",
           "prefix": "%",
           "status": discord.Status.online}
TOKEN = os.environ.get("PINGU_TOKEN")
COGS = ["admin", "clown", "help", "alert1234"]
VERSION = "0.0.3"
