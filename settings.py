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
COGS = ["admin", "clown", "help", "1234"]
VERSION = "0.0.2"
