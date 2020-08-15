"""This module contains Clown of the Week, a feature where users are nominated
to be a clown for past actions or things they said that is complete tomfoolery.
The status is kept on them for a week, hence the name.
"""
import asyncio
import logging

import discord
from discord.ext import commands


class Clown(commands.Cog):
    """Stuff related to clown of the week"""
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.server_clowns = {}

    def cog_unload(self):
        self.log.info("Cog unloaded; resetting all clowns to no one")
        self.server_clowns = {}

    @commands.group(name="clown")
    @commands.cooldown(rate=1, per=3.0, type=commands.BucketType.guild)
    async def clown(self, ctx):
        """Shows who the clown is in a server."""
        if ctx.invoked_subcommand is None:
            if ctx.guild.id not in self.server_clowns:
                self.server_clowns[ctx.guild.id] = None
            server_clown = self.server_clowns[ctx.guild.id]
            if server_clown is None:
                await ctx.send(f"{self.bot.icons['info']} The clown is no one.")
            elif server_clown.nick is None:
                await ctx.send(f"{self.bot.icons['info']} The clown is `{server_clown}`.")
            else:
                await ctx.send(
                    f"{self.bot.icons['info']} The clown is `{server_clown.nick} ({server_clown})`.")

    # Using the magic of Member Converter
    # this transforms a string mention of a user into a discord Member object
    @clown.command(name="set")
    async def set_clown(self, ctx, mention):
        """Sets the clown in a server to a mentioned user."""
        try:
            mention = await commands.MemberConverter().convert(ctx, mention)
        except commands.BadArgument:
            raise commands.BadArgument("Specified user is not in the server or you didn't @ them.")

        if mention in ctx.guild.members:
            if (ctx.guild.id not in self.server_clowns or
                    self.server_clowns[ctx.guild.id] is None or
                    self.server_clowns[ctx.guild.id].id != ctx.message.author.id):
                self.server_clowns[ctx.guild.id] = mention
                if mention.nick is None:
                    await ctx.send(f"{self.bot.icons['info']} The clown is set to `{mention}`.")
                else:
                    await ctx.send(
                        f"{self.bot.icons['info']} The clown is set to `{mention.nick} ({mention})`.")
            else:
                raise commands.BadArgument("Clowns are not allowed to do that.")

    @set_clown.error
    async def set_clown_error(self, ctx, error):
        """Error check to see if a clown was not set beforehand in a server."""
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{self.bot.icons['fail']} No clown was specified.")

    @clown.command(name="reset")
    async def reset_clown(self, ctx):
        """Reset the clown in a server to no one."""
        self.server_clowns[ctx.guild.id] = None
        await ctx.send(f"{self.bot.icons['info']} The clown is set to no one.")

    @clown.command(name="honk", case_insensitive=True)
    @commands.bot_has_guild_permissions(connect=True, speak=True)
    async def honk(self, ctx):
        """Honk at the clown when they're in the same voice channel as you."""
        file_name = "soundfx/honk.mp3"
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(file_name))
        ctx.voice_client.play(source)
        # voice_client.play debug:
        # ctx.voice_client.play(source, after=lambda e: print("Player error: {}".format(e)))

    @honk.before_invoke
    async def prepare_clown(self, ctx):
        """Custom voice channel permission checker was implemented because...
        1. @commands.bot_has_guild_permissions(...) decorator only checks if the bot has
            this permission in one of the roles it has in the SERVER, and the
        2. @commands.bot_has_permissions(...) decorator checks the permissions in the
            current TEXT channel, but not the actual voice channel.
        """
        # If initial set command was not run or clown in server is set to no one
        if ctx.guild.id not in self.server_clowns or self.server_clowns[ctx.guild.id] is None:
            raise commands.BadArgument("No clown was set.")
        # Check if bot is already connected to a voice channel
        if ctx.voice_client is None:
            # Check if the command issuer is connected to a voice channel
            if ctx.author.voice is None:
                raise commands.BadArgument("You are not connected to a voice channel.")

            # Custom voice channel permission check
            self_permissions = ctx.author.voice.channel.permissions_for(ctx.me)
            required_perms = {"connect": self_permissions.connect, "speak": self_permissions.speak}
            if self_permissions.connect and self_permissions.speak:
                await ctx.author.voice.channel.connect()
            else:
                missing_perms = "`, `".join(perm for perm, val in required_perms.items() if not val)
                raise commands.BadArgument(
                    f"I'm missing the `{missing_perms}` permission(s) for the voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @honk.after_invoke
    async def cleanup_clown(self, ctx):
        """Stay connected to the voice channel until the honk plays fully."""
        while ctx.voice_client.is_playing():
            await asyncio.sleep(1.0)
        await ctx.voice_client.disconnect()

    # TODO: Rework this feature to make it less buggy
    # @commands.Cog.listener()
    # async def on_voice_state_update(self, member, before, after):
    #     # Due to the asynchronous nature, this code is subject to race conditions
    #     # This will only run when they are connected to any voice channels beforehand
    #     if before.channel is None and after.channel is not None:
    #         current_guild = after.channel.guild.id
    #         if current_guild in self.guild_clowns and member == self.guild_clowns[current_guild]:
    #             await asyncio.sleep(1)
    #             if after.channel.guild.voice_client.is_connected() is False:
    #                 await after.channel.connect()
    #
    #             file_name = "soundfx/honk.mp3"
    #             source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(file_name))
    #             if after.channel.guild.voice_client.is_playing() is False:
    #                 after.channel.guild.voice_client.play(
    #                   source,
    #                   after=lambda e: print("Player error: %s" % e) if e else None)
    #             while after.channel.guild.voice_client.is_playing():
    #                 await asyncio.sleep(1)
    #
    #             after.channel.guild.voice_client.stop()
    #             await after.channel.guild.voice_client.disconnect()


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Clown(bot))
