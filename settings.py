"""This module stores all of the default settings of Pingu.
Also retrieves the token stored in the .env file.
"""
import os

import discord
from dotenv import load_dotenv


load_dotenv()

COGS = ["alert", "clown", "help", "miscellaneous", "schedules"]
DEFAULT = {"activity": discord.Activity(type=discord.ActivityType.watching,
                                        name="Pingu in the City"),
           "desc": "Noot Noot at your service",
           "prefix": "%",
           "status": discord.Status.online}
EMBED_COLOUR = discord.Colour.from_rgb(138, 181, 252)
ICONS = {"audio": ":speaker:",
         "fail": ":x:",
         "info": ":information_source:",
         "success": ":white_check_mark:"}
LAVALINK = {"HOST": os.environ.get("LAVALINKHOST"),
            "PORT": os.environ.get("LAVALINKPORT"),
            "PASSWORD": os.environ.get("LAVALINKPASSWORD"),
            "REGION": os.environ.get("LAVALINKREGION")}
TOKEN = os.environ.get("PINGU_TOKEN")
VERSION = "0.0.4"
