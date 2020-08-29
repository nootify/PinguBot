"""This module contains Clown of the Week, a feature where users are nominated
to be a clown for past actions or things they said that is complete tomfoolery.
The status is kept on them for a week, hence the name.
"""
import asyncio
import logging
from datetime import date, datetime, timedelta

import discord
import wavelink
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

        # Does not overwrite the client on cog reload
        if not hasattr(bot, 'wavelink'):
            self.bot.wavelink = wavelink.Client(bot=self.bot)

        self.bot.loop.create_task(self.start_nodes())

    async def start_nodes(self):
        """Establish connections to the Lavalink server"""
        await self.bot.wait_until_ready()

        node_name = "CLOWN"
        node = self.bot.wavelink.get_node(node_name)
        if not node:
            node = await self.bot.wavelink.initiate_node(
                host=self.bot.lavalink["HOST"],
                port=int(self.bot.lavalink["PORT"]),
                rest_uri=f"http://{self.bot.lavalink['HOST']}:{self.bot.lavalink['PORT']}",
                password=self.bot.lavalink["PASSWORD"],
                identifier=node_name,
                region=self.bot.lavalink["REGION"])

        # Disconnect Pingu when the audio finishes playing or an error occurs
        node.set_hook(self.on_event_hook)

    async def on_event_hook(self, event):
        """Catch events from a node"""
        if isinstance(event, (wavelink.TrackEnd, wavelink.TrackException)):
            await event.player.disconnect()

    def cog_unload(self):
        self.log.info("Cog unloaded; disconnecting from voice channels")

    @tasks.loop(count=1)
    async def update_cache(self):
        """Updates the memory cache on startup or entry update"""
        async with self.bot.db.acquire() as conn:
            results = await conn.fetch("SELECT * FROM clowns;")
            self.server_clowns = {result["guild_id"]: {
                "clown_id": result["clown_id"],
                "clowned_on": result["clowned_on"]
            } for result in results}
        self.log.info("Refreshed memory cache of server clowns")

    @tasks.loop(count=1)
    async def fetch_row(self):
        """Sends a fetch_row query to the PostgreSQL server"""
        # Make sure the input is sanitized before executing queries
        async with self.bot.db.acquire() as conn:
            self.result = await conn.fetchrow(self.query)

    @fetch_row.before_loop
    @update_cache.before_loop
    async def delay_queries(self):
        """Prevents queries from executing until a database connection can be established"""
        await self.bot.wait_until_ready()

    @commands.group(name="clown")
    @commands.cooldown(rate=1, per=5.0, type=commands.BucketType.guild)
    async def clown(self, ctx):
        """Shows who the clown is in a server"""
        if ctx.invoked_subcommand:
            return

        if not self.server_clowns:
            raise commands.BadArgument("Unable to retrieve data. Try again later.")
        if (ctx.guild.id not in self.server_clowns or
            not self.server_clowns[ctx.guild.id]["clown_id"]):
            info_icon = self.bot.icons["info"]
            await ctx.send(f"{info_icon} The clown is no one.")
            return

        # MemberConverter requires a string value
        try:
            server_clown = await commands.MemberConverter().convert(
                ctx, str(self.server_clowns[ctx.guild.id]["clown_id"]))
            self.log.debug(self.server_clowns[ctx.guild.id]["clown_id"])
        except commands.BadArgument as exc:
            raise commands.BadArgument("The clown is no longer in the server.") from exc
        else:
            info_icon = self.bot.icons["info"]
            if not server_clown.nick:
                await ctx.send(f"{info_icon} The clown is `{server_clown}`.")
            else:
                await ctx.send(
                    f"{info_icon} The clown is `{server_clown}` (`{server_clown.nick}`).")

    @clown.command(name="nominate", aliases=["nom"])
    async def nominate_clown(self, ctx: commands.Context, mention: str, *, reason: str):
        """Nominate someone to be clown of the week"""
        # Parse arguments
        if ctx.message.guild.id in self.polls and self.polls[ctx.message.guild.id]:
            raise commands.BadArgument("A nomination is currently in progress.")
        if len(reason) > 1900:
            raise commands.BadArgument("1900 characters or less, por favor.")
        try:
            mention = await commands.MemberConverter().convert(ctx, mention)
        except commands.BadArgument as exc:
            raise commands.BadArgument(
                "This user is not in the server or you didn't @ them.") from exc
        else:
            if mention.bot:
                raise commands.BadArgument("This command is unavailable for bots.")

        # Pull latest data from database
        self.query = f"SELECT clown_id, clowned_on FROM clowns WHERE guild_id = {ctx.message.guild.id};" # pylint: disable=line-too-long
        self.fetch_row.start() # pylint: disable=no-member
        while self.fetch_row.is_running(): # pylint: disable=no-member
            await asyncio.sleep(1)

        # Prevent the clown from un-clowning themselves until a week passed
        if (self.result and
                (date.today() - self.result["clowned_on"] <= timedelta(days=7)) and
                self.result["clown_id"] == ctx.message.author.id):
            raise commands.BadArgument("Clowns are not allowed to do that.")

        # Create the clown of the week nomination message
        poll_delay = 120 # This is in seconds
        poll_embed = discord.Embed(title="Clown of the Week",
                                   description=f"{mention} was nominated because:\n\n{reason}",
                                   colour=self.bot.embed_colour,
                                   timestamp=(datetime.utcnow() + timedelta(seconds=poll_delay)))
        poll_embed.set_author(name=f"Nominated by: {ctx.message.author}",
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
        if "❌" not in results or "✅" not in results:
            # Undo semaphore
            self.polls[ctx.message.guild.id] = None
            raise commands.BadArgument("Someone with moderator powers removed all the votes :eyes:")
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
        """Error check for missing arguments"""
        error_icon = self.bot.icons["fail"]
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "mention":
                await ctx.send(f"{error_icon} No candidate was specified.")
            elif error.param.name == "reason":
                await ctx.send(f"{error_icon} No reason was provided for the nomination.")
            return

    @clown.command(name="honk", case_insensitive=True)
    # @commands.bot_has_guild_permissions(connect=True, speak=True) # This throws a CheckFailure
    async def honk(self, ctx: commands.Context, *, channel: discord.VoiceChannel=None):
        """Honk at the clown they're in a voice channel"""
        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                raise commands.BadArgument("Join a voice channel or specify it by name.")

        # Check the clown is in the voice channel
        connected_users = set(member.id for member in channel.members)
        if self.server_clowns[ctx.guild.id]["clown_id"] not in connected_users:
            raise commands.BadArgument("Clown is not in the voice channel.")

        player = self.bot.wavelink.get_player(ctx.guild.id)
        if player.is_connected:
            raise commands.BadArgument("Something is already playing in a voice channel.")
        if not await self.can_connect(channel, ctx=ctx):
            return

        tracks = await self.bot.wavelink.get_tracks("./soundfx/honk.mp3")
        await player.connect(channel.id)
        await player.play(tracks[0])

    @honk.before_invoke
    async def prepare_clown(self, ctx):
        """Ensures all the conditions are good before connecting to voice"""
        # If no record exists in the database
        if (ctx.guild.id not in self.server_clowns or
            not self.server_clowns[ctx.guild.id]["clown_id"]):
            raise commands.BadArgument("No clown was set.")

    async def can_connect(self, voice: discord.VoiceChannel, ctx: commands.Context=None) -> bool:
        """Custom voice channel permission checker that was implemented because...
        1. @commands.bot_has_guild_permissions(...) decorator only checks if the bot has
            this permission in one of the roles it has in the SERVER, and the
        2. @commands.bot_has_permissions(...) decorator checks the permissions in the
            current TEXT channel, but not the actual voice channel.
        3. Wavelink does not check for permissions before connecting, so no errors can
           be emitted.
        """
        self_permissions = voice.permissions_for(voice.guild.me)
        if self_permissions.connect and self_permissions.speak:
            return True

        if ctx:
            required_perms = {"connect": self_permissions.connect,
                              "speak": self_permissions.speak,
                              "view channel": self_permissions.view_channel}
            missing_perms = "`, `".join(perm for perm, val in required_perms.items() if not val)
            icon = self.bot.icons["fail"]
            await ctx.send(f"{icon} I'm missing `{missing_perms}` permission(s) for the voice channel.")
        return False

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Triggers when the clown joins a voice channel and was not previously in another voice
        channel in the server.

        It will ignore rapid connects and disconnects from the clown, and will only reconnect
        when the audio playing fully finishes and Pingu disconnects from the voice channel.
        """
        # Ignore other music bots joining voice channels
        if member.bot:
            return

        # Skip if clown is not connecting to a voice channel in the guild for the first time,
        # meaning they were not in any voice channels in the guild, but then connected to one
        if not before.channel and after.channel:
            # Skip if the server id does not exist in the records
            if member.guild.id not in self.server_clowns:
                self.log.debug("Guild does not exist in the database records")
                return
            # Skip if the clown id does not match records
            if member.id != self.server_clowns[member.guild.id]["clown_id"]:
                self.log.debug("Clown does not match database records")
                return
            # Skip if a week or more passed
            if (datetime.now().date() - self.server_clowns[member.guild.id]["clowned_on"]) >= timedelta(days=7):
                self.log.debug("New nomination is needed for the auto-honk feature to activate")
                return

            player = self.bot.wavelink.get_player(member.guild.id)
            if await self.can_connect(after.channel) and not player.is_connected:
                tracks = await self.bot.wavelink.get_tracks("./soundfx/honk.mp3")
                await player.connect(after.channel.id)
                await player.play(tracks[0])


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Clown(bot))
