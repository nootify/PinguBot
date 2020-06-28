import logging

import asyncio
import discord
from discord.ext import commands


class Clown(commands.Cog):
    """Stuff related to clown of the week"""
    def __init__(self, bot):
        self.bot = bot
        self.server_clowns = {}
        self.log = logging.getLogger(__name__)

    @commands.group(name="clown")
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
                await ctx.send(f"{self.bot.icons['info']} The clown is `{server_clown.nick} ({server_clown})`.")

    # Using the magic of Member Converter
    # this transforms a string mention of a user into a discord Member object
    @clown.command(name="set")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def set_clown(self, ctx, mention: discord.Member):
        """Sets the clown in a server to a mentioned user."""
        if mention in ctx.guild.members:
            self.server_clowns[ctx.guild.id] = mention
            if mention.nick is None:
                await ctx.send(f"{self.bot.icons['info']} The clown is now set to `{mention}`.")
            else:
                await ctx.send(f"{self.bot.icons['info']} The clown is now set to `{mention.nick} ({mention})`.")

    @clown.command(name="reset")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def reset_clown(self, ctx):
        """Reset the clown in a server to no one."""
        self.server_clowns[ctx.guild.id] = None
        await ctx.send(f"{self.bot.icons['info']} The clown is now set to no one.")

    @clown.command(name="honk", case_insensitive=True)
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def honk(self, ctx):
        """Honk at the clown when they are in the same voice chat as you."""
        file_name = "soundfx/honk.mp3"
        source = discord.PCMVolumeTransformer(discord.FFmpegPCMAudio(file_name))
        ctx.voice_client.play(source)
        # voice_client.play debug:
        # ctx.voice_client.play(source, after=lambda e: print("Player error: {}".format(e)))

    @honk.before_invoke
    async def prepare_clown(self, ctx):
        # Prepares necessary conditions to connect to the voice channel
        if ctx.guild.id not in self.server_clowns or self.server_clowns[ctx.guild.id] is None:
            raise commands.CommandError(f"{self.bot.icons['fail']} No clown was set.")
        elif ctx.voice_client is None:
            if ctx.author.voice is None:
                raise commands.CommandError(f"{self.bot.icons['fail']} You are not connected to a voice channel.")
            else:
                # Custom permission checker because the library does not have built-in support
                # for voice channels. You cannot use @commands.bot_has_permissions(...) decorators.
                # This also applies to @commands.has_permissions(...) decorators,
                # which is for the command invoker.
                self_permissions = ctx.author.voice.channel.permissions_for(ctx.me)
                if self_permissions.connect and self_permissions.speak:
                    await ctx.author.voice.channel.connect()
                else:
                    raise commands.CommandError(f"{self.bot.icons['fail']} Missing permissions to speak/connect to the voice channel.")
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @honk.after_invoke
    async def cleanup_clown(self, ctx):
        while ctx.voice_client.is_playing():
            await asyncio.sleep(1)
        await ctx.voice_client.disconnect()

    # TODO: Rework scrapped functionality
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
    #                 after.channel.guild.voice_client.play(source, after=lambda e: print("Player error: %s" % e) if e else None)
    #             while after.channel.guild.voice_client.is_playing():
    #                 await asyncio.sleep(1)
    #
    #             after.channel.guild.voice_client.stop()
    #             await after.channel.guild.voice_client.disconnect()


def setup(bot):
    bot.add_cog(Clown(bot))
