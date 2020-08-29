"""This module stores all of the default settings of Pingu.
Also retrieves the token stored in the .env file.
"""
import os

import discord
from dotenv import load_dotenv


load_dotenv()

DEFAULT = {"activity": discord.Activity(type=discord.ActivityType.watching,
                                        name="Pingu in the City"),
           "desc": "Noot Noot at your service",
           "prefix": "%",
           "status": discord.Status.online}
COGS = ["alert", "clown", "help", "miscellaneous", "schedules"]
LAVALINK = {"HOST": os.environ.get("LAVALINKHOST"),
            "PORT": os.environ.get("LAVALINKPORT"),
            "PASSWORD": os.environ.get("LAVALINKPASSWORD"),
            "REGION": os.environ.get("LAVALINKREGION")}
TOKEN = os.environ.get("PINGU_TOKEN")
VERSION = "0.0.3"
