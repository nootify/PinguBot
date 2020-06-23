import discord

import pingutoken

default = {'activity': discord.Activity(type=discord.ActivityType.watching, name='Pingu in the City'),
           'desc': 'Noot noot',
           'prefix': '%',
           'status': discord.Status.online}
token = pingutoken.secret
cogs = ['admin']
version = '0.0.1a'
