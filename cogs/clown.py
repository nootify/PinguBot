import asyncio
import logging
from datetime import date, datetime, timedelta

import discord
import wavelink
from discord.ext import commands, tasks

from db import db
from common.settings import Icons
from db.models import Clown


class ClownWeek(commands.Cog):
    """Anything related to clown of the week"""

    NOMINATION_POLLS = {}
    GUILD_CLOWNS = None
    WAVELINK_NODE_NAME = "CLOWN"

    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.update_cache.start()

        # Avoid overwriting the wavelink client on cog reload
        if not hasattr(bot, "wavelink"):
            self.bot.wavelink = wavelink.Client(bot=self.bot)

        self.bot.loop.create_task(self.start_nodes())

    async def start_nodes(self):
        """Establish connection to the Lavalink server"""
        await self.bot.wait_until_ready()

        node = self.bot.wavelink.get_node(ClownWeek.WAVELINK_NODE_NAME)
        if not node:
            node = await self.bot.wavelink.initiate_node(
                host=self.bot.lavalink_host,
                port=self.bot.lavalink_port,
                rest_uri=f"http://{self.bot.lavalink_host}:{self.bot.lavalink_port}",
                password=self.bot.lavalink_password,
                identifier=ClownWeek.WAVELINK_NODE_NAME,
                region=self.bot.lavalink_region,
            )
        node.set_hook(self.on_event_hook)

    async def on_event_hook(self, event):
        """Catch events from a Wavelink node"""
        # Disconnect Pingu when the audio finishes playing or an error occurs
        if isinstance(event, (wavelink.TrackEnd, wavelink.TrackException)):
            await event.player.destroy()

    # def cog_unload(self):
    #     self.log.info("Disconnecting from all voice channels")

    @tasks.loop(count=1)
    async def update_cache(self):
        """Updates the in-memory cache of the clown data"""
        async with db.with_bind(self.bot.postgres_url):
            ClownWeek.GUILD_CLOWNS = await Clown.query.gino.all()
        self.log.info("Updated cache")

    @update_cache.before_loop
    async def wait_for_bot(self):
        """Prevent cache updates until the bot is ready"""
        await self.bot.wait_until_ready()

    @commands.group(name="whoisclown", aliases=["clown"])
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.user)
    async def clown_info(self, ctx):
        """Check who the clown is in the server"""
        if ClownWeek.GUILD_CLOWNS is None:
            await ctx.send(f"{Icons.WARN} Clown data not available yet. Try again later.")
            return

        if ctx.invoked_subcommand:
            return

        guild_exists = ctx.guild.id in (clown.guild_id for clown in ClownWeek.GUILD_CLOWNS)
        if not guild_exists:
            await ctx.send(f"{Icons.ALERT} The clown is no one.")
            return

        # MemberConverter requires a string value
        guild_clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == ctx.guild.id)
        try:
            server_clown = await commands.MemberConverter().convert(ctx, str(guild_clown_data.clown_id))
        except commands.BadArgument:
            raise commands.BadArgument("The clown is no longer in the server.")
        else:
            time_spent = date.today() - guild_clown_data.nomination_date
            await ctx.send(f"{Icons.ALERT} The clown is `{server_clown}` (clowned {time_spent.days} day(s) ago).")

    @clown_info.error
    async def clown_info_error_handler(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{Icons.ERROR} {error}")

    @clown_info.command(name="nominate")
    async def old_nominate(self, ctx: commands.Context):
        """Use the new nominate command."""
        await ctx.send(f"{Icons.ALERT} Use `{ctx.prefix}nominate ...` instead of `{ctx.prefix}clown nominate ...`")

    @commands.command(name="nominate", aliases=["nom"])
    async def nominate_clown(self, ctx: commands.Context, *, user: discord.Member):
        """Nominate someone to be clown of the week

        - Make sure to put a reason or else the nomination will be cancelled
        - You can either ping someone or type a Discord username/nickname exactly without the @.
        """
        if ClownWeek.GUILD_CLOWNS is None:
            await ctx.send(f"{Icons.WARN} Clown data not available yet. Try again later.")
            return

        if ctx.guild.id in ClownWeek.NOMINATION_POLLS and ClownWeek.NOMINATION_POLLS[ctx.guild.id]:
            raise commands.BadArgument("Only one nomination can happen in a server at a time.")

        if user.bot:
            raise commands.BadArgument("Clown cannot be a bot.")

        # Check if targeting the noot noot, then assign to nominator
        if user.id == self.bot.owner_id and ctx.author.id != self.bot.owner_id:
            user = ctx.author

        # Prevent the clown from nominating until a week passed
        clown_data = next(
            (clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == ctx.guild.id),
            None,
        )
        if clown_data is not None:
            if user.id == clown_data.previous_clown_id:
                raise commands.BadArgument("User was already clown of the week. Nominate someone else.")

            current_clown = ctx.author.id == clown_data.clown_id
            time_spent = date.today() - clown_data.nomination_date
            eligible = time_spent >= timedelta(days=7)
            if current_clown and not eligible:
                raise commands.BadArgument(
                    f"You can't nominate anyone yet ({max(0, 7 - time_spent.days)} day(s) left as clown of the week)."
                )

        # Set poll semaphore
        ClownWeek.NOMINATION_POLLS[ctx.guild.id] = True

        # Confirm the message received is indeed the user that sent it
        nominator = ctx.message.author
        nomination_time = 30  # seconds
        nomination_prompt = await ctx.send(f"{nominator.mention} has {nomination_time} seconds to give a reason:")

        def confirm_message(msg):
            return msg.author.id == nominator.id and msg.channel.id == ctx.message.channel.id

        try:
            nomination_reason = await self.bot.wait_for("message", timeout=nomination_time, check=confirm_message)
            await nomination_prompt.delete()
        except asyncio.TimeoutError:
            ClownWeek.NOMINATION_POLLS[ctx.guild.id] = False
            await nomination_prompt.delete()
            raise commands.BadArgument("No reason given. Canceling nomination.")

        def create_poll(reason: discord.Message, delay: int) -> discord.Embed:
            """A template to create the nomination poll"""
            poll_embed = discord.Embed(colour=self.bot.embed_colour)
            poll_embed.set_author(name="Clown of the Week Nomination")
            poll_embed.title = f"{user}"
            poll_embed.set_thumbnail(url=user.avatar_url)
            poll_embed.set_footer(
                text=f"Nominated by: {ctx.author} • Voting ends in: {delay} seconds", icon_url=ctx.author.avatar_url
            )

            # Cut off text that exceeds 1000 characters
            max_embed_message_length = 1000
            if len(reason.content) <= max_embed_message_length:
                poll_embed.description = reason.content
            else:
                poll_embed.description = f"{reason.content[:max_embed_message_length]} ..."
            return poll_embed

        # Store the nomination message in the semaphore
        poll_delay = 60  # seconds
        ClownWeek.NOMINATION_POLLS[ctx.guild.id] = await ctx.send(embed=create_poll(nomination_reason, poll_delay))
        await ClownWeek.NOMINATION_POLLS[ctx.guild.id].add_reaction("\N{white heavy check mark}")
        await ClownWeek.NOMINATION_POLLS[ctx.guild.id].add_reaction("\N{cross mark}")
        await asyncio.sleep(poll_delay)

        # Refresh message for reaction changes
        try:
            ClownWeek.NOMINATION_POLLS[ctx.guild.id] = await ctx.message.channel.fetch_message(
                ClownWeek.NOMINATION_POLLS[ctx.guild.id].id
            )
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            ClownWeek.NOMINATION_POLLS[ctx.guild.id] = False
            raise commands.BadArgument("The poll was deleted or Unable to retrieve votes. Canceling nomination.")

        # Check the results of the poll
        poll_reactions = ClownWeek.NOMINATION_POLLS[ctx.guild.id].reactions

        total_reactions = sum(reaction.count for reaction in poll_reactions if reaction.emoji in ("❌", "✅")) - 2
        vote_reactions = {reaction.emoji: (reaction.count - 1) for reaction in poll_reactions}
        self.log.info("Results: %s, Total: %s", vote_reactions, total_reactions)

        if total_reactions < 0 or vote_reactions["❌"] < 0 or vote_reactions["✅"] < 0:
            ClownWeek.NOMINATION_POLLS[ctx.guild.id] = False
            await ctx.send(f"{Icons.HMM} Someone manipulated the votes. Canceling nomination.")
            return
        elif total_reactions == 0:
            ClownWeek.NOMINATION_POLLS[ctx.guild.id] = False
            raise commands.BadArgument("No one voted. Canceling nomination.")

        nomination_percent = int(vote_reactions["✅"] / total_reactions) * 100
        nomination_threshold = 50
        if nomination_percent < nomination_threshold:
            ClownWeek.NOMINATION_POLLS[ctx.guild.id] = False
            raise commands.BadArgument(
                f"Nomination did not get enough support ({100 - nomination_percent}% voted against)."
            )

        # Change the clown because enough votes were in favor of the nomination
        async with db.with_bind(self.bot.postgres_url) as engine:
            if clown_data is None:
                new_clown = Clown(
                    guild_id=ctx.guild.id,
                    clown_id=user.id,
                    previous_clown_id=user.id,
                    join_time=datetime.utcfromtimestamp(0),
                )
                await new_clown.create(bind=engine)
            else:
                new_clown = clown_data
                await new_clown.update(
                    clown_id=user.id,
                    previous_clown_id=clown_data.clown_id,
                    nomination_date=datetime.utcnow(),
                    join_time=datetime.utcfromtimestamp(0),
                ).apply()
        self.update_cache.start()

        # Display who the new clown is
        await ctx.send(f"{Icons.ALERT} The clown is now `{user}`.")

        # Undo semaphore
        ClownWeek.NOMINATION_POLLS[ctx.guild.id] = False

    @nominate_clown.error
    async def nominate_error_handler(self, ctx: commands.Context, error):
        """Error check for missing arguments"""
        if isinstance(error, commands.MemberNotFound):
            await ctx.send(f"{Icons.ERROR} No user with that Discord username or server nickname was found.")
            return
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "user":
                await ctx.send(f"{Icons.ERROR} Missing user to nominate.")
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{Icons.ERROR} {error}")

    @commands.command(name="honk", case_insensitive=True)
    @commands.cooldown(rate=1, per=60.0, type=commands.BucketType.guild)
    # Removed since this throws a CheckFailure
    # @commands.bot_has_guild_permissions(connect=True, speak=True)
    async def honk(self, ctx: commands.Context, *, channel: discord.VoiceChannel = None):
        """Honk at the clown when they're in a voice channel

        - You can omit **[channel]** if the clown is in the same voice channel as you
        """
        if not channel:
            try:
                channel = ctx.author.voice.channel
            except AttributeError:
                raise commands.BadArgument("Join a voice channel or specify it by name.")

        # Check the clown is in the voice channel
        connected_users = set(member.id for member in channel.members)
        clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == ctx.guild.id)
        if clown_data.clown_id not in connected_users:
            raise commands.BadArgument("The clown is not in the voice channel.")
        time_spent = date.today() - clown_data.nomination_date
        if time_spent >= timedelta(days=7):
            raise commands.BadArgument("A new clown nomination is needed to use this command.")

        player = self.bot.wavelink.get_player(ctx.guild.id, node_id=ClownWeek.WAVELINK_NODE_NAME)
        if not player.is_connected and not await self.can_connect(channel, ctx=ctx):
            return

        tracks = await self.bot.wavelink.get_tracks("./soundfx/honk.mp3")
        await player.connect(channel.id)
        await player.play(tracks[0])

    @honk.before_invoke
    async def prepare_clown(self, ctx: commands.Context):
        """Ensures all the conditions are good before connecting to voice"""
        # If no record exists in the database
        if ClownWeek.GUILD_CLOWNS is None:
            await ctx.send(f"{Icons.WARN} Clown data not available yet. Try again later.")
            return

        if ctx.guild.id not in (clown.guild_id for clown in ClownWeek.GUILD_CLOWNS):
            raise commands.BadArgument("No clown was nominated in this server.")

    @honk.error
    async def honk_error(self, ctx: commands.Context, error):
        """Local error handler for the honk command"""
        if isinstance(error, commands.BotMissingPermissions):
            self.bot.get_command("honk").reset_cooldown(ctx)
            missing_perms = "`, `".join(error.missing_perms)
            await ctx.send(f"{Icons.WARN} I'm missing the `{missing_perms}` permission(s) for the server.")
        if isinstance(error, commands.BadArgument):
            self.bot.get_command("honk").reset_cooldown(ctx)
            await ctx.send(f"{Icons.ERROR} {error}")

    async def can_connect(self, voice: discord.VoiceChannel, ctx: commands.Context = None) -> bool:
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
            required_perms = {
                "connect": self_permissions.connect,
                "speak": self_permissions.speak,
                "view channel": self_permissions.view_channel,
            }
            missing_perms = "`, `".join(perm for perm, val in required_perms.items() if not val)
            await ctx.send(f"{Icons.WARN} I'm missing `{missing_perms}` permission(s) for the voice channel.")
        return False

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Triggers when the clown joins a voice channel and was not previously in another voice
        channel in the server.

        It will ignore rapid connects and disconnects from the clown, and will only reconnect
        when the audio playing fully finishes and Pingu disconnects from the voice channel.
        """
        # Ignore bots joining the voice channels
        if member.bot:
            return

        # Skip if clown is not connecting to a voice channel in the guild for the first time
        if not before.channel and after.channel:
            if ClownWeek.GUILD_CLOWNS is None:
                self.log.debug("Data did not load yet.")
                return
            # Skip if the server id does not exist in the records
            if member.guild.id not in (clown.guild_id for clown in ClownWeek.GUILD_CLOWNS):
                self.log.debug("Guild does not exist in the database records")
                return
            # Skip if the clown id does not match records
            clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == member.guild.id)
            if member.id != clown_data.clown_id:
                self.log.debug("User does not match clown id")
                return
            # Skip if a week or more passed
            time_spent = date.today() - clown_data.nomination_date
            if time_spent >= timedelta(days=7):
                self.log.debug(
                    "New nomination needed in '%s'",
                    member.guild.id,
                )
                return
            # Skip if the clown is spamming the bot
            last_joined = datetime.utcnow() - clown_data.join_time
            self.log.debug(
                "Clown '%s' last joined %s second(s) ago",
                member.id,
                last_joined.total_seconds(),
            )
            if last_joined <= timedelta(minutes=10):
                self.log.debug("Potential spam connect by '%s' in '%s'", member.id, member.guild.id)
                return

            # Update join time of clown
            async with db.with_bind(self.bot.postgres_url):
                new_clown = clown_data
                await new_clown.update(join_time=datetime.utcnow()).apply()
            self.update_cache.start()

            # Play the audio
            player = self.bot.wavelink.get_player(member.guild.id, node_id=ClownWeek.WAVELINK_NODE_NAME)
            if not player.is_connected and await self.can_connect(after.channel):
                tracks = await self.bot.wavelink.get_tracks("./soundfx/honk.mp3")
                await player.connect(after.channel.id)
                await player.play(tracks[0])


def setup(bot):
    bot.add_cog(ClownWeek(bot))
