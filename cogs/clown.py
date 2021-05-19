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
        self.last_joined = datetime.now()
        self.polls = {}
        self.query = None
        self.result = None
        self.server_clowns = None
        self.update_cache.start() # pylint: disable=no-member
        self.log = logging.getLogger(__name__)

        self.node_name = "CLOWN"
        # Does not overwrite the client on cog reload
        if not hasattr(bot, "wavelink"):
            self.bot.wavelink = wavelink.Client(bot=self.bot)

        self.bot.loop.create_task(self.start_nodes())

    async def start_nodes(self):
        """Establish connections to the Lavalink server"""
        await self.bot.wait_until_ready()

        node = self.bot.wavelink.get_node(self.node_name)
        if not node:
            node = await self.bot.wavelink.initiate_node(
                host=self.bot.lavalink["HOST"],
                port=int(self.bot.lavalink["PORT"]),
                rest_uri=f"http://{self.bot.lavalink['HOST']}:{self.bot.lavalink['PORT']}",
                password=self.bot.lavalink["PASSWORD"],
                identifier=self.node_name,
                region=self.bot.lavalink["REGION"])

        # Disconnect Pingu when the audio finishes playing or an error occurs
        node.set_hook(self.on_event_hook)

    async def on_event_hook(self, event):
        """Catch events from a node"""
        if isinstance(event, (wavelink.TrackEnd, wavelink.TrackException)):
            await event.player.destroy()

    def cog_unload(self):
        self.log.info("Cog unloaded; disconnecting from voice channels")

    @tasks.loop(count=1)
    async def update_cache(self):
        """Updates the memory cache on startup or entry update"""
        async with self.bot.db.acquire() as conn:
            results = await conn.fetch("SELECT * FROM clowns;")
            self.server_clowns = {result["guild_id"]: {
                "clown_id": result["clown_id"],
                "clowned_on": result["clowned_on"],
                "last_joined": datetime.now() - timedelta(minutes=15),
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
    @commands.cooldown(rate=1, per=3.0, type=commands.BucketType.guild)
    async def clown(self, ctx):
        """Type `help clown` to see more info on this command

        **clown**
        Show who the clown is in the server
        """
        if ctx.invoked_subcommand:
            return

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
    async def nominate_clown(self, ctx: commands.Context, *, user: discord.Member): # pylint: disable=too-many-return-statements
        """Nominate someone to be clown of the week

        The following are valid when providing a reason:
        - Typing in the reason
        - Attaching a picture
        - Doing both (but make sure it's uploaded together)

        Some other notes:
        - You need to upload the actual image file, not a link
        - Only the first image is used
        """
        # Parse arguments
        error_icon = self.bot.icons["fail"]
        if ctx.guild.id in self.polls and self.polls[ctx.guild.id]:
            await ctx.send(f"{error_icon} A nomination is currently in progress.")
            return
        if user.bot:
            await ctx.send(f"{error_icon} Potential feedback loop detected. Canceling.")
            return
        # Check if targeting the noot noot, and assign to nominator
        if user.id == self.bot.owner_id and ctx.author.id != self.bot.owner_id:
            user = ctx.author
        # Prevent the clown from nominating until a week passed
        if (ctx.guild.id in self.server_clowns and
                (date.today() - self.server_clowns[ctx.guild.id]["clowned_on"] <= timedelta(days=7)) and
                ctx.message.author.id == self.server_clowns[ctx.guild.id]["clown_id"]):
            self.polls[ctx.guild.id] = False
            await ctx.send(f"{error_icon} You cannot nominate someone at this time.")
            return

        # Set poll semaphore
        self.polls[ctx.guild.id] = True

        # Confirm the message received is indeed the user that sent it
        nominator = ctx.message.author
        nomination_time = 60 # seconds
        nomination_prompt = await ctx.send(
            f"{nominator.mention}, you have {nomination_time} seconds to give a reason for the nomination.")
        def confirm_message(msg):
            return msg.author.id == nominator.id and msg.channel.id == ctx.message.channel.id
        try:
            nomination_reason = await self.bot.wait_for("message",
                                                        timeout=nomination_time,
                                                        check=confirm_message)
            await nomination_prompt.delete()
        except asyncio.TimeoutError:
            self.polls[ctx.guild.id] = False
            await nomination_prompt.delete()
            await ctx.send(f"{error_icon} No reason was provided. Canceling nomination.")
            return

        def create_poll(reason: discord.Message, delay: int) -> discord.Embed:
            """A template to create the nomination poll"""
            poll_embed = discord.Embed(title="Clown of the Week",
                                       colour=self.bot.embed_colour,
                                       timestamp=(datetime.utcnow() + timedelta(seconds=delay)))
            poll_embed.set_author(name=f"Nominated by: {ctx.message.author}",
                                  icon_url=ctx.author.avatar_url)
            poll_embed.set_footer(text="Voting will end")

            # Cut off text that exceeds 1800 characters
            if len(reason.content) <= 1800:
                poll_embed.description = f"{user} was nominated because:\n\n{reason.content}"
            else:
                poll_embed.description = f"{user} was nominated because:\n\n{reason.content[:1797]}..."
            # Invalid images/URLs will just set an empty image
            if reason.attachments:
                poll_embed.set_image(url=reason.attachments[0].url)
            return poll_embed

        # Store the nomination message in the semaphore
        poll_delay = 120 # seconds
        self.polls[ctx.guild.id] = await ctx.send(
            embed=create_poll(nomination_reason, poll_delay))
        await self.polls[ctx.guild.id].add_reaction("\N{white heavy check mark}")
        await self.polls[ctx.guild.id].add_reaction("\N{cross mark}")
        await asyncio.sleep(poll_delay)
        # def vote_check(reaction, user):
        #     return user == ctx.message.author and str(reaction.emoji) in ["✅", "❌"]

        # Refresh message for reaction changes
        try:
            self.polls[ctx.guild.id] = await ctx.message.channel.fetch_message(
                self.polls[ctx.guild.id].id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            self.polls[ctx.guild.id] = False
            await ctx.send(f"{error_icon} Unable to retrieve poll data. Canceling nomination.")
            return

        # Check the results of the poll
        results = {reaction.emoji: reaction.count
                   for reaction in self.polls[ctx.guild.id].reactions}
        if "❌" not in results or "✅" not in results:
            self.polls[ctx.guild.id] = False
            await ctx.send(
                f"{error_icon} Someone removed all of the votes for the nomination :eyes:")
            return
        if results["❌"] >= results["✅"]:
            self.polls[ctx.guild.id] = False
            await ctx.send(f"{error_icon} Nomination failed to gain enough votes.")
            return

        # Change the clown because enough votes were in favor of the nomination
        if self.server_clowns and ctx.guild.id in self.server_clowns:
            self.query = f"UPDATE clowns SET clown_id = {user.id}, clowned_on = NOW() WHERE guild_id = {ctx.guild.id};" # pylint: disable=line-too-long
        else:
            self.query = f"INSERT INTO clowns (guild_id, clown_id, clowned_on) VALUES('{ctx.guild.id}', '{user.id}', NOW());" # pylint: disable=line-too-long
        self.fetch_row.start() # pylint: disable=no-member
        while self.fetch_row.is_running(): # pylint: disable=no-member
            await asyncio.sleep(1)
        self.update_cache.start() # pylint: disable=no-member

        # Display who the new clown is
        if not user.nick:
            await ctx.send(f"{self.bot.icons['info']} The clown is now `{user}`.")
        else:
            await ctx.send(
                f"{self.bot.icons['info']} The clown is now `{user}` (`{user.nick}`).")

        # Undo semaphore
        self.polls[ctx.guild.id] = False

    @nominate_clown.error
    async def nominate_clown_error(self, ctx: commands.Context, error):
        """Error check for missing arguments"""
        ctx.local_error_only = True
        error_icon = self.bot.icons["fail"]
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "user":
                await ctx.send(f"{error_icon} No candidate was specified.")
            elif error.param.name == "reason":
                await ctx.send(f"{error_icon} No reason was provided for the nomination.")
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{error_icon} User is not in the server.")
            return

    @clown.command(name="honk", case_insensitive=True)
    # @commands.bot_has_guild_permissions(connect=True, speak=True) # This throws a CheckFailure
    async def honk(self, ctx: commands.Context, *, channel: discord.VoiceChannel=None):
        """Honk at the clown when they're in a voice channel

        Omitting **[channel]** means the clown has to be in the same
        voice channel as you
        """
        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError as exc:
                raise commands.BadArgument("Join a voice channel or specify it by name.") from exc

        # Check the clown is in the voice channel
        connected_users = set(member.id for member in channel.members)
        if self.server_clowns[ctx.guild.id]["clown_id"] not in connected_users:
            raise commands.BadArgument("Clown is not in the voice channel.")

        player = self.bot.wavelink.get_player(ctx.guild.id, node_id=self.node_name)
        if player.is_connected:
            raise commands.BadArgument("Something is already playing in a voice channel.")
        if not await self.can_connect(channel, ctx=ctx):
            return

        tracks = await self.bot.wavelink.get_tracks("./soundfx/honk.mp3")
        await player.connect(channel.id)
        await player.play(tracks[0])

    @honk.before_invoke
    async def prepare_clown(self, ctx: commands.Context):
        """Ensures all the conditions are good before connecting to voice"""
        # If no record exists in the database
        if (ctx.guild.id not in self.server_clowns or
            not self.server_clowns[ctx.guild.id]["clown_id"]):
            raise commands.BadArgument("No clown was set.")

    @honk.error
    async def honk_error(self, ctx: commands.Context, error):
        """Local error handler for the honk command"""
        if isinstance(error, commands.BotMissingPermissions):
            error_icon = self.bot.icons["fail"]
            missing = "`, `".join(error.missing_perms)
            await ctx.send(
                f"{error_icon} I'm missing the `{missing}` permission(s) for the server.")
            return

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
            await ctx.send(
                f"{icon} I'm missing `{missing_perms}` permission(s) for the voice channel.")
        return False

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member,
                                    before: discord.VoiceState, after: discord.VoiceState):
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
            today = datetime.now().date()
            more_than_a_week = (today - self.server_clowns[member.guild.id]["clowned_on"]) >= timedelta(days=7)
            if more_than_a_week:
                self.log.debug(
                    "New nomination in '%s' is needed for the auto-honk feature to activate",
                    member.guild.id)
                return
            # Skip if they are abusing the bot
            spam = (datetime.now() - self.server_clowns[member.guild.id]["last_joined"]) <= timedelta(minutes=15)
            if spam:
                self.log.debug(
                    "Potential spam connect/disconnect by '%s'",
                    member.guild.id)
                return

            self.server_clowns[member.guild.id]["last_joined"] = datetime.now()
            player = self.bot.wavelink.get_player(member.guild.id, node_id=self.node_name)
            if await self.can_connect(after.channel) and not player.is_connected:
                tracks = await self.bot.wavelink.get_tracks("./soundfx/honk.mp3")
                await player.connect(after.channel.id)
                await player.play(tracks[0])


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Clown(bot))
