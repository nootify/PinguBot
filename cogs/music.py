"""This module houses music/video streaming. There's unresolved bugs, so don't
use this thing yet.
Base implementation taken from:
https://github.com/PythonistaGuild/Wavelink/blob/master/examples/playlist.py
"""
import asyncio
import datetime
import itertools
import re
import sys
import traceback
from typing import Union

import discord
import humanize
import wavelink
from discord.ext import commands, tasks


RURL = re.compile(r"https?://(?:www\.)?.+")

class MusicController: # pylint: disable=too-few-public-methods
    """Handles audio queuing for the Music module"""
    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id
        self.channel = None

        self.next = asyncio.Event()
        self.queue = asyncio.Queue()

        self.volume = 50
        self.now_playing = None

        self.bot.loop.create_task(self.controller_loop())

    async def controller_loop(self):
        """The actual queue system implementation"""
        await self.bot.wait_until_ready()

        player = self.bot.wavelink.get_player(self.guild_id)
        await player.set_volume(self.volume)

        while True:
            if self.now_playing:
                await self.now_playing.delete()

            self.next.clear()

            song = await self.queue.get()
            await player.play(song)
            self.now_playing = await self.channel.send(f"Now playing: `{song}`")

            await self.next.wait()


class Music(commands.Cog):
    """Pretty self-explanatory"""
    def __init__(self, bot):
        self.bot = bot
        self.controllers = {}

        if not hasattr(bot, "wavelink"):
            self.bot.wavelink = wavelink.Client(bot=self.bot)

        self.bot.loop.create_task(self.start_nodes())

    async def start_nodes(self):
        """Establish connections to the Lavalink server"""
        await self.bot.wait_until_ready()

        # Initiate our nodes. For this example we will use one server.
        # Region should be a discord.py guild.region
        # e.g sydney or us_central (this is not technically required)
        node = await self.bot.wavelink.initiate_node(
            host=self.bot.lavalink["HOST"],
            port=int(self.bot.lavalink["PORT"]),
            rest_uri=f"http://{self.bot.lavalink['HOST']}:{self.bot.lavalink['PORT']}",
            password=self.bot.lavalink["PASSWORD"],
            identifier="PinguMusic",
            region=self.bot.lavalink["REGION"])

        # Set our node hook callback
        node.set_hook(self.on_event_hook)

    async def on_event_hook(self, event):
        """Node hook callback."""
        if isinstance(event, (wavelink.TrackEnd, wavelink.TrackException)):
            controller = self.get_controller(event.player)
            controller.next.set()

    def get_controller(self, value: Union[commands.Context, wavelink.Player]):
        "Get the queue for the guild"
        if isinstance(value, commands.Context):
            gid = value.guild.id
        else:
            gid = value.guild_id

        try:
            controller = self.controllers[gid]
        except KeyError:
            controller = MusicController(self.bot, gid)
            self.controllers[gid] = controller

        return controller

    async def cog_check(self, ctx): # pylint: disable=invalid-overridden-method
        """A local check which applies to all commands in this cog."""
        if not ctx.guild:
            raise commands.NoPrivateMessage
        return True

    async def cog_command_error(self, ctx, error):
        """A local error handler for all errors arising from commands in this cog."""
        if isinstance(error, commands.NoPrivateMessage):
            try:
                return await ctx.send("This command can not be used in Private Messages.")
            except discord.HTTPException:
                pass

        print("Ignoring exception in command {}:".format(ctx.command), file=sys.stderr)
        traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)

    @tasks.loop(minutes=5)
    async def disconnect_idle(self):
        """Disconnects idle instances Pingu in voice channels every 5 minutes"""
        # TODO: Figure out how to do this
        pass

    @commands.command(name="join", aliases=["connect"])
    async def join_channel(self, ctx, *, channel: discord.VoiceChannel=None):
        """Connect to a voice channel"""
        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError as exc:
                raise commands.BadArgument(
                    "Not connected to a voice channel. Join one or specify it by name.") from exc

        player = self.bot.wavelink.get_player(ctx.guild.id)
        if not await self.can_connect(channel, ctx=ctx):
            return

        await ctx.send(f"{self.bot.icons['audio']} Connected to **`{channel.name}`**")
        await player.connect(channel.id)

        # return await ctx.send(
        #     f"{self.bot.icons['fail']} Already connected to **`{channel.name}`**")

        controller = self.get_controller(ctx)
        controller.channel = ctx.channel

    @commands.command(name="leave", aliases=["disconnect", "dc"])
    async def leave_channel(self, ctx):
        """Disconnect from the voice channel"""
        # TODO: Fix bug where queue keeps playing while not in a voice channel
        player = self.bot.wavelink.get_player(ctx.guild.id)

        if player.is_playing and not player.paused:
            await player.set_pause(True)
            await player.disconnect()
            return await ctx.send(":play_pause: Pausing the queue and disconnecting from channel")

        if player:
            await player.disconnect()
            return await ctx.send(":eject: Disconnecting from channel")

    @commands.command()
    async def play(self, ctx, *, query: str):
        """Search for a song and add it to the queue"""
        if not RURL.match(query):
            query = f"ytsearch:{query}"

        tracks = await self.bot.wavelink.get_tracks(f"{query}")

        if not tracks:
            return await ctx.send(f"{self.bot.icons['fail']} Unable to find requested query.")

        player = self.bot.wavelink.get_player(ctx.guild.id)
        if not player.is_connected:
            await ctx.invoke(self.join_channel)

        track = tracks[0]

        controller = self.get_controller(ctx)
        await controller.queue.put(track)
        await ctx.send(f"{self.bot.icons['success']} Added {str(track)} to the queue")

    @commands.command()
    async def pause(self, ctx):
        """Pause the queue"""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        if not player.is_playing:
            return await ctx.send(f"{self.bot.icons['fail']} Nothing is playing")

        await ctx.send(":pause_button: Paused the queue")
        await player.set_pause(True)

    @commands.command()
    async def resume(self, ctx):
        """Resume the queue"""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        if not player.paused:
            return await ctx.send(f"{self.bot.icons['fail']} Nothing is playing")

        await ctx.send(":arrow_forward: Resumed the queue")
        await player.set_pause(False)

    @commands.command()
    async def skip(self, ctx):
        """Skip the current song"""
        player = self.bot.wavelink.get_player(ctx.guild.id)

        if not player.is_playing:
            return await ctx.send(f"{self.bot.icons['fail']} Nothing to skip")

        await ctx.send(":fast_forward: Skipped the current song")
        await player.stop()

    @commands.command(hidden=True, enabled=False)
    async def volume(self, ctx, *, vol: int):
        """Set the player volume"""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        controller = self.get_controller(ctx)

        vol = max(min(vol, 100), 0)
        controller.volume = vol

        await ctx.send(f":arrow_up_down: Setting the volume to `{vol}%`")
        await player.set_volume(vol)

    @commands.command(name="nowplaying", aliases=["np", "current"])
    async def now_playing(self, ctx):
        """Show the currently playing song"""
        player = self.bot.wavelink.get_player(ctx.guild.id)

        if not player.current:
            return await ctx.send(
                f"{self.bot.icons['info']} Nothing is playing or the ")

        controller = self.get_controller(ctx)
        await controller.now_playing.delete()

        controller.now_playing = await ctx.send(f":musical_note: Now playing: `{player.current}`")

    @commands.command(aliases=["q"])
    async def queue(self, ctx):
        """Shows the next 5 songs in the queue"""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        controller = self.get_controller(ctx)

        if not player.current or not controller.queue._queue:
            return await ctx.send(f"{self.bot.icons['info']} The queue is empty")

        upcoming = list(itertools.islice(controller.queue._queue, 0, 5))

        fmt = "\n".join(f"**`{str(song)}`**" for song in upcoming)
        embed = discord.Embed(title=f"Upcoming - Next {len(upcoming)}", description=fmt)

        await ctx.send(embed=embed)

    @commands.command(name="clear", aliases=["stop"])
    async def clear_queue(self, ctx):
        """Clear the queue and disconnect from the voice channel"""
        player = self.bot.wavelink.get_player(ctx.guild.id)

        try:
            del self.controllers[ctx.guild.id]
        except KeyError:
            await player.disconnect()
            return await ctx.send(":eject: Disconnecting from channel")

        await player.disconnect()
        await ctx.send(":eject: Clearing the queue and disconnecting from channel")

    @commands.command(name="debug")
    async def debug_info(self, ctx):
        """Retrieve various Node/Server/Player information."""
        player = self.bot.wavelink.get_player(ctx.guild.id)
        node = player.node

        used = humanize.naturalsize(node.stats.memory_used)
        total = humanize.naturalsize(node.stats.memory_allocated)
        free = humanize.naturalsize(node.stats.memory_free)
        cpu = node.stats.cpu_cores

        fmt = f"**WaveLink:** `{wavelink.__version__}`\n\n" \
              f"Connected to `{len(self.bot.wavelink.nodes)}` nodes.\n" \
              f"Best available Node `{self.bot.wavelink.get_best_node().__repr__()}`\n" \
              f"`{len(self.bot.wavelink.players)}` players are distributed on nodes.\n" \
              f"`{node.stats.players}` players are distributed on server.\n" \
              f"`{node.stats.playing_players}` players are playing on server.\n\n" \
              f"Server Memory: `{used}/{total}` | `({free} free)`\n" \
              f"Server CPU: `{cpu}`\n\n" \
              f"Server Uptime: `{datetime.timedelta(milliseconds=node.stats.uptime)}`"
        await ctx.send(fmt)

    async def can_connect(self, voice: discord.VoiceChannel, ctx: commands.Context = None):
        """Custom voice channel permission checker that was implemented because...
        1. @commands.bot_has_guild_permissions(...) decorator only checks if the bot has
            this permission in one of the roles it has in the SERVER, and the
        2. @commands.bot_has_permissions(...) decorator checks the permissions in the
            current TEXT channel, but not the actual voice channel.
        """
        self_permissions = voice.permissions_for(voice.guild.me)
        if self_permissions.connect and self_permissions.speak:
            return True
        if ctx:
            required_perms = {"connect": self_permissions.connect, "speak": self_permissions.speak}
            missing_perms = "`, `".join(perm for perm, val in required_perms.items() if not val)
            icon = self.bot.icons["fail"]
            await ctx.send(
                f"{icon} I'm missing `{missing_perms}` permission(s) for the voice channel.")
        return False


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Music(bot))
