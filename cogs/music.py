import asyncio
import discord
import youtube_dl
from discord.ext import commands


# This class has been retrieved from the basic voice bot example on the discord.py GitHub page.
# Modified from original code by adding a queue functionality.
ytdl_format_options = {
    "format": "bestaudio/best",
    "outtmpl": "%(extractor)s-%(id)s-%(title)s.%(ext)s",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "auto",
    "source_address": "0.0.0.0"  # Bind to ipv4 since ipv6 addresses cause issues sometimes
}
ffmpeg_options = {
    "options": "-vn"
}
ytdl = youtube_dl.YoutubeDL(ytdl_format_options)


class YTDLSource(discord.PCMVolumeTransformer):
    def __init__(self, source, *, data, volume=0.5):
        super().__init__(source, volume)
        self.data = data
        self.title = data.get("title")
        self.url = data.get("url")

    @classmethod
    async def from_url(cls, url, *, loop=None, stream=False):
        loop = loop or asyncio.get_event_loop()
        data = await loop.run_in_executor(None, lambda: ytdl.extract_info(url, download=not stream))

        if "entries" in data:
            # Take first item from a playlist
            data = data["entries"][0]

        filename = data["url"] if stream else ytdl.prepare_filename(data)
        return cls(discord.FFmpegPCMAudio(filename, **ffmpeg_options), data=data)


class Music(commands.Cog):
    """This is not ready to be used."""
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="stop")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def stop_music(self, ctx):
        """Stop playing music and disconnect from the voice channel."""
        if ctx.voice_client is not None:
            await ctx.voice_client.disconnect()
            await ctx.send(":information_source: Leaving voice channel.")
        else:
            await ctx.send(":information_source: Nothing is playing right now.")

    @commands.command(name="clear")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def clear_music(self, ctx):
        """Clear the current music queue."""
        await ctx.send("No queue system exists yet.")

    @commands.command(name="play")
    @commands.cooldown(1, 5, commands.BucketType.guild)
    async def play_music(self, ctx, url):
        """Play something from a given valid URL."""
        if ctx.voice_client.is_playing():
            await ctx.send("No queue system implemented yet. Can only play one song at a time.")

        async with ctx.typing():
            try:
                player = await YTDLSource.from_url(url, loop=self.bot.loop)
                ctx.voice_client.play(player, after=lambda e: print(f"Player error: {e}") if e else None)
            except (youtube_dl.DownloadError, youtube_dl.utils.UnsupportedError):
                raise commands.CommandError("Something went wrong or this URL is unsupported.")

        await ctx.send(f":musical_note: Now playing: {player.title}")

    @play_music.before_invoke
    async def prepare_music(self, ctx):
        if ctx.voice_client is None:
            if ctx.author.voice is None:
                raise commands.CommandError("You are not connected to a voice channel.")
            else:
                # Custom permission checker because the library does not have built-in support
                # for voice channels. You cannot use @commands.bot_has_permissions(...)
                # This also applies to @commands.has_permissions(...),
                # which is for the command invoker
                self_permissions = ctx.author.voice.channel.permissions_for(ctx.me)
                if self_permissions.connect and self_permissions.speak:
                    await ctx.author.voice.channel.connect()
                else:
                    raise commands.CommandError("Missing permissions to speak/connect to the voice channel.")

    @play_music.after_invoke
    async def cleanup_music(self, ctx):
        while ctx.voice_client is not None and ctx.voice_client.is_playing():
            await asyncio.sleep(1)
        ctx.voice_client.stop()

    @play_music.error
    async def play_music_error(self, ctx, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(":x: No URL was found.")


def setup(bot):
    bot.add_cog(Music(bot))
