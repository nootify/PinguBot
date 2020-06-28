import discord

import pingutoken

default = {"activity": discord.Activity(type=discord.ActivityType.watching, name="Pingu in the City"),
           "desc": "Noot Noot at your service",
           "prefix": "%",
           "status": discord.Status.online}
token = pingutoken.secret
cogs = ["admin", "help"]
version = "0.0.2"
