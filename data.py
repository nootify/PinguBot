import os

import discord

default = {"activity": discord.Activity(type=discord.ActivityType.watching,
                                        name="Pingu in the City"),
           "desc": "Noot Noot at your service",
           "prefix": "%",
           "status": discord.Status.online}
TOKEN = os.getenv("PINGU_TOKEN", None)
COGS = ["admin", "clown", "help", "1234"]
VERSION = "0.0.2"
