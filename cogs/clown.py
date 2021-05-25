import asyncio
import logging
from datetime import date, datetime, timedelta

import discord
import wavelink
from discord.ext import commands

from common.util import Icons
from db.models import Clown


class ClownWeek(commands.Cog):
    """Anything related to clown of the week"""

    NOMINATION_POLLS = {}
    GUILD_CLOWNS = None
    WAVELINK_NODE_NAME = "CLOWN"

    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.bot.loop.create_task(self.update_cache())

        # Avoids overwriting the wavelink client on cog reload
        if not hasattr(bot, "wavelink"):
            self.bot.wavelink = wavelink.Client(bot=self.bot)

        self.bot.loop.create_task(self.start_node())

    async def start_node(self):
        """Start a wavelink node"""
        await self.bot.wait_until_ready()
        node = await self.bot.wavelink.initiate_node(
            host=self.bot.lavalink_host,
            port=self.bot.lavalink_port,
            rest_uri=f"http://{self.bot.lavalink_host}:{self.bot.lavalink_port}",
            password=self.bot.lavalink_password,
            identifier=ClownWeek.WAVELINK_NODE_NAME,
            region=self.bot.lavalink_region,
        )
        node.set_hook(self.on_event_hook)

    async def destroy_node(self):
        """Gracefully disconnect from voice channels on cog reload"""
        node = self.bot.wavelink.get_node(ClownWeek.WAVELINK_NODE_NAME)
        # players = tuple(node.players.values())  # Avoids dict resize issue
        # for player in players:
        #     await player.destroy()
        await node.destroy(force=True)

    async def on_event_hook(self, event):
        """Catch events from a wavelink node"""
        if isinstance(event, (wavelink.TrackEnd, wavelink.TrackException)):
            await event.player.destroy()

    def cog_unload(self):
        self.bot.loop.create_task(self.destroy_node())
        self.log.info("Disconnecting from all voice channels")

    async def update_cache(self):
        """Update the in-memory cache of the clown data"""
        await self.bot.wait_until_ready()
        async with self.bot.db.with_bind(self.bot.db_url):
            ClownWeek.GUILD_CLOWNS = await Clown.query.gino.all()
        self.log.info("Updated cache")

    @commands.group(name="whoisclown", aliases=["clown"])
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.user)
    async def clown_info(self, ctx: commands.Context):
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
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.user)
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
            return (
                msg.author.id == nominator.id
                and msg.channel.id == ctx.message.channel.id
                and not msg.content.startswith(ctx.prefix)
            )

        try:
            nomination_reason = await self.bot.wait_for("message", timeout=nomination_time, check=confirm_message)
        except asyncio.TimeoutError:
            ClownWeek.NOMINATION_POLLS[ctx.guild.id] = False
            await nomination_prompt.delete()
            raise commands.BadArgument("No reason given. Canceling nomination.")
        else:
            await nomination_prompt.delete()

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

        nomination_percent = round((vote_reactions["✅"] / total_reactions) * 100)
        nomination_threshold = 67
        if nomination_percent < nomination_threshold:
            ClownWeek.NOMINATION_POLLS[ctx.guild.id] = False
            raise commands.BadArgument(
                f"Nomination needs at least {nomination_threshold}% approval (currently {nomination_percent}%)."
            )

        # Change the clown because enough votes were in favor of the nomination
        async with self.bot.db.with_bind(self.bot.db_url) as engine:
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
        await self.update_cache()

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

    @commands.command(name="honk", hidden=True)
    @commands.is_owner()
    async def honk(self, ctx: commands.Context):
        """Honk at the clown in a voice channel"""
        if ClownWeek.GUILD_CLOWNS is None:
            await ctx.send(f"{Icons.WARN} Clown data not available yet. Try again later.", delete_after=3)
            return

        if ctx.guild.id not in (clown.guild_id for clown in ClownWeek.GUILD_CLOWNS):
            raise commands.BadArgument("No clown was nominated in this server.")

        clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == ctx.guild.id)
        time_spent = date.today() - clown_data.nomination_date
        if time_spent >= timedelta(days=7):
            raise commands.BadArgument("A new clown nomination is needed.")

        found_channel = None
        channels = [channel for channel in ctx.guild.channels if channel.type == discord.ChannelType.voice]
        for channel in channels:
            channel_member_ids = set(member.id for member in channel.members)
            if clown_data.clown_id in channel_member_ids:
                found_channel = channel
                break

        player = self.bot.wavelink.get_player(ctx.guild.id, node_id=ClownWeek.WAVELINK_NODE_NAME)
        if not found_channel or (ctx.guild.afk_channel and found_channel.id == ctx.guild.afk_channel.id):
            raise commands.BadArgument("The clown is not in any voice channel(s).")
        if player.is_connected or player.is_playing:
            raise commands.BadArgument("Already playing in a voice channel.")
        if not await self.can_connect(found_channel, ctx=ctx):
            return

        tracks = await self.bot.wavelink.get_tracks("./soundfx/honk.mp3")
        await player.connect(channel.id)
        await player.play(tracks[0])

    @honk.error
    async def honk_error_handler(self, ctx: commands.Context, error):
        """Local error handler for the honk command"""
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{Icons.ERROR} {error}", delete_after=3)

    @commands.command(name="disconnect", aliases=["dc"], hidden=True)
    @commands.is_owner()
    async def disconnect(self, ctx: commands.Context):
        """Disconnect Pingu from a voice channel for debugging purposes"""
        player = self.bot.wavelink.get_player(ctx.guild.id, node_id=ClownWeek.WAVELINK_NODE_NAME)
        if player and player.is_connected:
            await player.destroy()
            await ctx.send(f"{Icons.ALERT} Disconnected from voice channel.", delete_after=3)
            return
        await ctx.send(f"{Icons.WARN} Not connected to a voice channel.", delete_after=3)

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

    async def clown_check(self, member: discord.Member, channel: discord.VoiceChannel) -> bool:
        # Skip if it is the afk channel
        if channel and member.guild.afk_channel and channel.id == member.guild.afk_channel.id:
            return False
        # Skip if the data is not ready yet
        if ClownWeek.GUILD_CLOWNS is None:
            self.log.debug("Data did not load yet.")
            return False
        # Skip if the server id does not exist in the records
        if member.guild.id not in (clown.guild_id for clown in ClownWeek.GUILD_CLOWNS):
            self.log.debug("Guild does not exist in the database records")
            return False
        # Skip if the clown id does not match records
        clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == member.guild.id)
        if member.id != clown_data.clown_id:
            self.log.debug("User does not match clown id")
            return False
        return True

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
        if member.bot or not await self.clown_check(member, after.channel):
            return

        player = self.bot.wavelink.get_player(member.guild.id, node_id=ClownWeek.WAVELINK_NODE_NAME)

        # Clown connects to voice channel from disconnected state
        if not before.channel and after.channel:
            is_active = player and player.is_connected and player.channel_id == after.channel.id
            is_clown_deaf = member.voice.self_deaf or member.voice.deaf
            if is_active and is_clown_deaf:
                await player.set_pause(True)
                return
            if is_active and not is_clown_deaf:
                await player.set_pause(False)
                return

            clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == member.guild.id)

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
            if last_joined <= timedelta(minutes=60):
                self.log.debug("Potential spam connect by '%s' in '%s'", member.id, member.guild.id)
                return

            # Play the audio
            if not player.is_connected and len(after.channel.members) >= 3 and await self.can_connect(after.channel):
                # Only update the join time when it can connect and play
                async with self.bot.db.with_bind(self.bot.db_url):
                    new_clown = clown_data
                    await new_clown.update(join_time=datetime.utcnow()).apply()
                await self.update_cache()
                await player.connect(after.channel.id)

                tracks = await self.bot.wavelink.get_tracks("./soundfx/honk.mp3")
                await player.play(tracks[0])
                if member.voice.self_deaf or member.voice.deaf:
                    await player.set_pause(True)
            return

        # Only play while the clown can hear the bot
        if before.channel and after.channel:
            is_active = player and player.is_connected and player.channel_id == after.channel.id
            is_clown_deaf = member.voice.self_deaf or member.voice.deaf

            if not is_active or (is_active and is_clown_deaf):
                await player.set_pause(True)

            if is_active and not is_clown_deaf:
                await player.set_pause(False)
            return

        if before.channel and not after.channel:
            if player.is_connected:
                await player.set_pause(True)


def setup(bot):
    bot.add_cog(ClownWeek(bot))
