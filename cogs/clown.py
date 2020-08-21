"""This module contains Clown of the Week, a feature where users are nominated
to be a clown for past actions or things they said that is complete tomfoolery.
The status is kept on them for a week, hence the name.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta

import discord
from discord.ext import commands, tasks


class Clown(commands.Cog):
    """Stuff related to clown of the week"""
    def __init__(self, bot):
        self.bot = bot
        self.polls = {}
        self.query = None
        self.result = None
        self.server_clowns = None
        self.update_cache.start() # pylint: disable=no-member
        self.log = logging.getLogger(__name__)

    def cog_unload(self):
        self.polls = {}
        self.query = None
        self.result = None
        self.server_clowns = None
        self.log.info("Cog unloaded; disconnecting from voice channels")

    @tasks.loop(count=1)
    async def update_cache(self):
        """Updates the memory cache on startup or entry update."""
        async with self.bot.db.acquire() as conn:
            results = await conn.fetch("SELECT * FROM clowns;")
            self.server_clowns = {result["guild_id"]: result["clown_id"] for result in results}
        self.log.info("Refreshed memory cache of server clowns")

    @tasks.loop(count=1)
    async def fetch_row(self):
        """Sends a fetch_row query to the PostgreSQL server."""
        # Make sure the input is sanitized before executing queries
        async with self.bot.db.acquire() as conn:
            self.result = await conn.fetchrow(self.query)

    @fetch_row.before_loop
    @update_cache.before_loop
    async def delay_queries(self):
        """Prevents queries from executing until a database connection can be established."""
        await self.bot.wait_until_ready()

    @commands.group(name="clown")
    @commands.cooldown(rate=1, per=3.0, type=commands.BucketType.guild)
    async def clown(self, ctx):
        """Shows who the clown is in a server."""
        if ctx.invoked_subcommand is None:
            if not self.server_clowns:
                raise commands.BadArgument("Unable to retrieve data. Try again later.")
            if ctx.guild.id not in self.server_clowns or not self.server_clowns[ctx.guild.id]:
                info_icon = self.bot.icons["info"]
                await ctx.send(f"{info_icon} The clown is no one.")
                return

            # MemberConverter requires a string value
            try:
                server_clown = await commands.MemberConverter().convert(
                    ctx, str(self.server_clowns[ctx.guild.id]))
                self.log.debug(self.server_clowns[ctx.guild.id])
            except commands.BadArgument:
                raise commands.BadArgument("The clown is no longer in the server.")
            else:
                info_icon = self.bot.icons["info"]
                if not server_clown.nick:
                    await ctx.send(f"{info_icon} The clown is `{server_clown}`.")
                else:
                    await ctx.send(
                        f"{info_icon} The clown is `{server_clown}` (`{server_clown.nick}`).")

    @clown.command(name="nominate")
    async def nominate_clown(self, ctx: commands.Context, mention: str, *, reason: str):
        """Nominate someone to be clown of the week."""
        # Parse arguments
        if ctx.message.guild.id in self.polls and self.polls[ctx.message.guild.id]:
            raise commands.BadArgument("A nomination is currently in progress.")
        if len(reason) > 1900:
            raise commands.BadArgument("1900 characters or less, por favor.")
        try:
            mention = await commands.MemberConverter().convert(ctx, mention)
        except commands.BadArgument:
            raise commands.BadArgument("This user is not in the server or you didn't @ them.")
        if mention.bot:
            raise commands.BadArgument("This command is unavailable for bots.")

        # Pull latest data from database
        self.query = f"SELECT clown_id, clowned_on FROM clowns WHERE guild_id = {ctx.message.guild.id};" # pylint: disable=line-too-long
        self.fetch_row.start() # pylint: disable=no-member
        while self.fetch_row.is_running(): # pylint: disable=no-member
            await asyncio.sleep(1)

        # Prevent the clown from un-clowning themselves until a week passed
        if (self.result and
                (self.result["clowned_on"] + timedelta(days=7)) >= date.today() and
                self.result["clown_id"] == ctx.message.author.id):
            raise commands.BadArgument("Clowns are not allowed to do that.")

        # Create the clown of the week nomination message
        poll_delay = 120 # This is in seconds
        poll_embed = discord.Embed(title="Clown of the Week Nomination",
                                   description=f"{mention} was nominated because:\n\n{reason}",
                                   colour=self.bot.embed_colour,
                                   timestamp=(datetime.utcnow() + timedelta(seconds=poll_delay)))
        poll_embed.set_author(name=f"Nomination started by: {ctx.message.author}",
                              icon_url=ctx.author.avatar_url)
        poll_embed.set_footer(text="Voting will end")

        # Set a poll semaphore for the server and then send the nomination message
        self.polls[ctx.message.guild.id] = await ctx.send(embed=poll_embed)
        await self.polls[ctx.message.guild.id].add_reaction("\N{white heavy check mark}")
        await self.polls[ctx.message.guild.id].add_reaction("\N{cross mark}")

        await asyncio.sleep(poll_delay)
        # def vote_check(reaction, user):
        #     return user == ctx.message.author and str(reaction.emoji) in ["✅", "❌"]

        # Refresh message for reaction changes
        self.polls[ctx.message.guild.id] = await ctx.message.channel.fetch_message(
            self.polls[ctx.message.guild.id].id)
        # Check the results of the poll
        results = {reaction.emoji: reaction.count
                   for reaction in self.polls[ctx.message.guild.id].reactions}
        if results["❌"] >= results["✅"]:
            # Undo semaphore
            self.polls[ctx.message.guild.id] = None
            raise commands.BadArgument("Nomination failed to gain enough votes.")

        # Change the clown because enough votes were in favor of the nomination
        if self.result:
            self.query = f"UPDATE clowns SET clown_id = {mention.id}, clowned_on = NOW() WHERE guild_id = {ctx.message.guild.id};" # pylint: disable=line-too-long
        else:
            self.query = f"INSERT INTO clowns (guild_id, clown_id, clowned_on) VALUES('{ctx.message.guild.id}', '{mention.id}', NOW());" # pylint: disable=line-too-long
        self.fetch_row.start() # pylint: disable=no-member
        while self.fetch_row.is_running(): # pylint: disable=no-member
            await asyncio.sleep(1)
        self.update_cache.start() # pylint: disable=no-member

        # Display who the new clown is
        if not mention.nick:
            await ctx.send(f"{self.bot.icons['info']} The clown is now `{mention}`.")
        else:
            await ctx.send(
                f"{self.bot.icons['info']} The clown is now `{mention}` (`{mention.nick}`).")

        # Undo semaphore
        self.polls[ctx.message.guild.id] = None

    @nominate_clown.error
    async def nominate_clown_error(self, ctx, error):
        """Error check to see if a clown was not mentioned."""
        error_icon = self.bot.icons['fail']
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "mention":
                await ctx.send(f"{error_icon} No candidate was specified.")
            elif error.param.name == "reason":
                await ctx.send(f"{error_icon} No reason was provided for the nomination.")
            return

    @clown.command(name="honk", case_insensitive=True, hidden=True)
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
        if not ctx.voice_client:
            # Check if the command issuer is connected to a voice channel
            if not ctx.author.voice:
                raise commands.BadArgument("You are not connected to a voice channel.")

            # Custom voice channel permission check
            await self.connect_voice(ctx.author.voice.channel, ctx=ctx)
        elif ctx.voice_client.is_playing():
            ctx.voice_client.stop()

    @honk.after_invoke
    async def cleanup_clown(self, ctx):
        """Stay connected to the voice channel until the honk plays fully."""
        while ctx.voice_client.is_playing():
            await asyncio.sleep(1.0)
        await ctx.voice_client.disconnect()

    async def connect_voice(self, voice: discord.VoiceChannel, ctx: commands.Context = None):
        """Custom voice channel permission checker that was implemented because...
        1. @commands.bot_has_guild_permissions(...) decorator only checks if the bot has
            this permission in one of the roles it has in the SERVER, and the
        2. @commands.bot_has_permissions(...) decorator checks the permissions in the
            current TEXT channel, but not the actual voice channel.
        """
        self_permissions = voice.permissions_for(voice.guild.me)
        if self_permissions.connect and self_permissions.speak:
            await voice.connect()
            return
        if ctx:
            required_perms = {"connect": self_permissions.connect, "speak": self_permissions.speak}
            missing_perms = "`, `".join(perm for perm, val in required_perms.items() if not val)
            icon = self.bot.icons["fail"]
            ctx.send(f"{icon} I'm missing `{missing_perms}` permission(s) for the voice channel.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        """Triggers when the clown joins a voice channel and was not previously in another voice
        channel in the server. It will also ignore rapid connects and disconnects from the clown.
        """
        await self.bot.wait_until_ready()
        if not before.channel and after.channel:
            current_server_id = after.channel.guild.id
            if (current_server_id in self.server_clowns and
                    member.id == self.server_clowns[current_server_id]):
                await asyncio.sleep(1) # Buggy sound without delay
                after_cache = after.channel
                if after_cache and not after_cache.guild.voice_client:
                    await self.connect_voice(after_cache)

                    if (after_cache.guild.voice_client and
                            not after_cache.guild.voice_client.is_playing()):
                        sound_file = "soundfx/honk.mp3"
                        sound_source = discord.PCMVolumeTransformer(
                            discord.FFmpegPCMAudio(
                                executable="/usr/bin/ffmpeg",
                                source=sound_file))

                        def cleanup(error):
                            self.log.error("voice_client: %s", error)
                            disconnect = after_cache.guild.voice_client.disconnect()
                            run = asyncio.run_coroutine_threadsafe(disconnect, self.bot.loop)
                            try:
                                run.result()
                            except Exception as exc: # pylint: disable=broad-except
                                self.log.error("%s: %s", type(exc).__name__, exc)

                        after_cache.guild.voice_client.play(
                            sound_source, after=cleanup)

def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Clown(bot))
