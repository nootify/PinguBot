import asyncio
import logging
from datetime import timedelta

import discord
import wavelink
from discord.ext import commands
from discord.utils import sleep_until, utcnow
from sqlalchemy import select, update

from common.exception import MissingClown, MissingData, MissingVoicePermissions
from common.utils import Icons
from models import Clown, async_session


class ClownWeek(commands.Cog):
    """Anything related to clown of the week"""

    NOMINATION_POLLS = {}
    GUILD_CLOWNS = None
    IDLE_PLAYERS = {}
    WAVELINK_NODE_NAME = "CLOWN"

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.bot.loop.create_task(self.create_node())
        self.bot.loop.create_task(self.update_cache())

    async def cog_unload(self) -> None:
        self.log.info("Cog unloaded. Disconnecting all players.")

    async def create_node(self) -> None:
        """Start a wavelink node"""
        await self.bot.wait_until_ready()
        node: wavelink.Node = wavelink.Node(
            id=ClownWeek.WAVELINK_NODE_NAME,
            uri=f"http://{self.bot.lavalink_host}:{self.bot.lavalink_port}",
            password=self.bot.lavalink_password,
        )
        await wavelink.NodePool.connect(
            client=self.bot,
            nodes=[node],
        )

    # TODO: the lib updated the way these work, so a rewrite is necessary
    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, node: wavelink.Node) -> None:
        self.log.info("Wavelink node '%s' ready to process requests", node.id)

    @commands.Cog.listener()
    async def on_wavelink_track_end(self, payload: wavelink.TrackEventPayload) -> None:
        if payload.reason == "FINISHED":
            await payload.player.disconnect()

    @commands.Cog.listener()
    async def on_wavelink_track_event(self, payload: wavelink.TrackEventPayload) -> None:
        self.log.error("Wavelink %s %s", payload.event.name, payload.reason)
        await payload.player.disconnect()

    async def update_cache(self) -> None:
        """Update the in-memory cache of the clown data"""
        await self.bot.wait_until_ready()
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(select(Clown))
                ClownWeek.GUILD_CLOWNS = result.scalars().all()

        self.log.info("Updated cache")

    def clown_cache_exists():
        def predicate(ctx: commands.Context):
            if ClownWeek.GUILD_CLOWNS is None:
                raise MissingData("Clown data not available yet. Try again later.")
            return True

        return commands.check(predicate)

    def clown_exists(self, ctx: commands.Context) -> bool:
        return ctx.guild.id in (clown.guild_id for clown in ClownWeek.GUILD_CLOWNS)

    def check_voice_permissions(self, channel: discord.VoiceChannel) -> bool:
        """Custom voice channel permission checker

        Note:
        - @commands.bot_has_guild_permissions(...) only checks if the bot has this
        permission in one of the roles it has in the guild
        - @commands.bot_has_permissions(...) can only check the permissions of the
        text channel it processed the command from, but not the actual voice channel
        - Wavelink does not check for permissions before connecting, so errors are
        silently eaten
        """
        voice_permissions = channel.permissions_for(channel.guild.me)
        if voice_permissions.connect and voice_permissions.speak:
            return True
        return False

    def check_clown_voice_state(self, member: discord.Member, channel: discord.VoiceChannel) -> bool:
        # Skip if afk channel
        if channel and member.guild.afk_channel and channel.id == member.guild.afk_channel.id:
            return False
        # Skip if data is not ready yet
        if ClownWeek.GUILD_CLOWNS is None:
            self.log.debug("Data did not load yet.")
            return False
        # Skip if the guild id is not in the records
        if member.guild.id not in (clown.guild_id for clown in ClownWeek.GUILD_CLOWNS):
            self.log.debug("Guild does not exist in the database records")
            return False
        # Skip if the user id does not match the clown id
        clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == member.guild.id)
        if member.id != clown_data.clown_id:
            self.log.debug("User does not match clown id")
            return False
        return True

    async def disconnect_idle_player(self, player: wavelink.Player, guild_id: int) -> None:
        await asyncio.sleep(600)
        self.log.info("Player idled in %s. Closing connection.", guild_id)
        await player.disconnect()
        ClownWeek.IDLE_PLAYERS.pop(guild_id)

    @commands.group(name="clown", invoke_without_command=True)
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.member)
    @clown_cache_exists()
    async def clown_info(self, ctx: commands.Context) -> None:
        """Check who the clown is in the server"""
        if not self.clown_exists(ctx):
            raise MissingClown("No clown has been nominated.")

        clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == ctx.guild.id)
        try:
            # MemberConverter needs a string value
            server_clown = await commands.MemberConverter().convert(ctx, str(clown_data.clown_id))
        except commands.BadArgument:
            raise MissingClown("The clown is no longer in the server.")
        else:
            time_spent = utcnow().date() - clown_data.nomination_date
            embed = self.bot.create_embed(
                description=f"{Icons.ALERT} The clown is {server_clown.mention} (clowned {time_spent.days} days ago)."
            )
            await ctx.send(embed=embed)

    @clown_info.error
    async def clown_info_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed = self.bot.create_embed()
        if isinstance(error, (MissingClown, MissingData)):
            error_embed.description = f"{Icons.WARN} {error}"
            await ctx.send(embed=error_embed)
        elif isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @clown_info.command(name="nominate")
    async def old_nominate(self, ctx: commands.Context) -> None:
        """Use the new nominate command"""
        embed = self.bot.create_embed(
            description=f"{Icons.ALERT} Use `{ctx.prefix}nominate ...` instead of `{ctx.prefix}clown nominate ...`"
        )
        await ctx.send(embed=embed)

    def create_poll_embed(self, ctx: commands.Context, user: discord.Member, reason: str, delay: int) -> discord.Embed:
        """A template to create the nomination poll"""
        poll_body_text = f"{user.mention} {reason}"
        poll_embed = self.bot.create_embed(description=poll_body_text)
        poll_embed.set_author(name="Clown of the Week Nomination")
        poll_embed.set_thumbnail(url=user.display_avatar)
        poll_embed.set_footer(
            text=f"Nominated by: {ctx.author} • Voting ends in: {delay} seconds", icon_url=ctx.author.display_avatar
        )
        return poll_embed

    @commands.command(name="nominate", aliases=["nom"])
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.member)
    @clown_cache_exists()
    async def nominate_clown(self, ctx: commands.Context, *, user: discord.Member) -> None:
        """Nominate someone to be clown of the week

        - You can either ping someone or type a Discord username/nickname exactly without the @
        - Make sure to put a reason afterwards or else the nomination will be cancelled
        """
        if ctx.guild.id in ClownWeek.NOMINATION_POLLS:
            raise commands.BadArgument("Only one nomination can happen at a time in a server.")

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
        if clown_data:
            if user.id == clown_data.previous_clown_id:
                raise commands.BadArgument(f"{user.mention} was already clown of the week. Nominate someone else.")

            current_clown = ctx.author.id == clown_data.clown_id
            time_spent = utcnow().date() - clown_data.nomination_date
            eligible = time_spent >= timedelta(days=7)
            if current_clown and not eligible:
                raise commands.BadArgument(
                    f"You can't nominate anyone yet ({max(0, 7 - time_spent.days)} day(s) left as clown of the week)."
                )

        # Set poll semaphore
        nominator = ctx.author
        nomination_time = 30  # seconds
        embed = self.bot.create_embed(description=f"{nominator.mention} has {nomination_time} seconds to give a reason")
        ClownWeek.NOMINATION_POLLS[ctx.guild.id] = await ctx.send(embed=embed)

        def confirm_message(msg):
            """Check the response is from the person who started the nomination and the message is not a command"""
            return (
                msg.author.id == nominator.id
                and msg.channel.id == ctx.channel.id
                and not msg.content.startswith(ctx.prefix)
            )

        try:
            nominator_response = await self.bot.wait_for("message", timeout=nomination_time, check=confirm_message)
        except asyncio.TimeoutError:
            await ClownWeek.NOMINATION_POLLS.pop(ctx.guild.id).delete()
            raise commands.BadArgument("No reason given. Canceling nomination.")
        else:
            await ClownWeek.NOMINATION_POLLS[ctx.guild.id].delete()
        if len(nominator_response.content) > 1000:
            ClownWeek.NOMINATION_POLLS.pop(ctx.guild.id)
            raise commands.BadArgument("Nomination reason is too long.")

        delay_poll = 60  # seconds
        delay_datetime = utcnow() + timedelta(seconds=delay_poll)
        ClownWeek.NOMINATION_POLLS[ctx.guild.id] = await ctx.send(
            embed=self.create_poll_embed(ctx, user, nominator_response.content, delay_poll)
        )
        valid_emoji = ("✅", "❌")
        for emoji in valid_emoji:
            await ClownWeek.NOMINATION_POLLS[ctx.guild.id].add_reaction(emoji)
        await sleep_until(delay_datetime)

        # Refresh message for reaction changes
        try:
            refresh = await ctx.channel.fetch_message(ClownWeek.NOMINATION_POLLS[ctx.guild.id].id)
            ClownWeek.NOMINATION_POLLS[ctx.guild.id] = refresh
        except discord.HTTPException:
            ClownWeek.NOMINATION_POLLS.pop(ctx.guild.id)
            raise commands.BadArgument("Unable to retrieve votes. Canceling nomination.")

        # Check the results of the poll
        poll_reactions = ClownWeek.NOMINATION_POLLS[ctx.guild.id].reactions

        total_votes = sum(reaction.count for reaction in poll_reactions if reaction.emoji in valid_emoji) - 2
        user_votes = {reaction.emoji: (reaction.count - 1) for reaction in poll_reactions}
        self.log.debug("Results: %s / Total: %s", user_votes, total_votes)

        if total_votes < 0 or user_votes["✅"] < 0 or user_votes["❌"] < 0:
            ClownWeek.NOMINATION_POLLS.pop(ctx.guild.id)
            embed = self.bot.create_embed(
                description=f"{Icons.HMM} Someone manipulated the votes. Canceling nomination."
            )
            await ctx.send(embed=embed)
            return
        elif total_votes == 0:
            ClownWeek.NOMINATION_POLLS.pop(ctx.guild.id)
            raise commands.BadArgument("No one voted. Canceling nomination.")

        nomination_percent = round((user_votes["✅"] / total_votes) * 100)
        nomination_threshold = 67
        if nomination_percent < nomination_threshold:
            ClownWeek.NOMINATION_POLLS.pop(ctx.guild.id)
            raise commands.BadArgument(
                f"Nomination needs at least {nomination_threshold}% approval (currently {nomination_percent}%)."
            )

        # Change the clown because enough votes were in favor of the nomination
        async with async_session() as session:
            async with session.begin():
                if clown_data is None:
                    session.add(Clown(guild_id=ctx.guild.id, clown_id=user.id, previous_clown_id=user.id))
                else:
                    await session.execute(
                        update(Clown)
                        .where(Clown.guild_id == ctx.guild.id)
                        .values(clown_id=user.id, previous_clown_id=clown_data.clown_id)
                    )
                await session.commit()
        await self.update_cache()

        # Display who the new clown is
        result_embed = self.bot.create_embed(description=f"{Icons.ALERT} The clown is now {user.mention}.")
        await ctx.send(embed=result_embed)

        # Undo semaphore
        ClownWeek.NOMINATION_POLLS.pop(ctx.guild.id)

    @nominate_clown.error
    async def nominate_clown_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed = self.bot.create_embed()
        if isinstance(error, commands.MemberNotFound):
            error_embed.description = f"{Icons.ERROR} No user with that Discord username or server nickname was found."
            await ctx.send(embed=error_embed)
        elif isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "user":
                error_embed.description = f"{Icons.ERROR} Missing user to nominate."
                await ctx.send(embed=error_embed)
        elif isinstance(error, MissingData):
            error_embed.description = f"{Icons.WARN} {error}"
            await ctx.send(embed=error_embed)
        elif isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)
        else:
            ClownWeek.NOMINATION_POLLS.pop(ctx.guild.id)

    @commands.command(name="honk", hidden=True)
    @commands.is_owner()
    @clown_cache_exists()
    async def honk(self, ctx: commands.Context) -> None:
        """Honk at the clown in a voice channel"""
        if not self.clown_exists(ctx):
            raise MissingClown("No clown has been nominated.")

        clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == ctx.guild.id)
        time_spent = utcnow().date() - clown_data.nomination_date
        if time_spent >= timedelta(days=7):
            raise commands.BadArgument("A new clown nomination is needed.")

        found_channel = None
        channels = [channel for channel in ctx.guild.channels if channel.type == discord.ChannelType.voice]
        for channel in channels:
            channel_member_ids = set(member.id for member in channel.members)
            if clown_data.clown_id in channel_member_ids:
                found_channel = channel
                break

        player: wavelink.Player = wavelink.NodePool.get_node(id=ClownWeek.WAVELINK_NODE_NAME).get_player(ctx.guild)
        if not found_channel or (ctx.guild.afk_channel and found_channel.id == ctx.guild.afk_channel.id):
            raise commands.BadArgument("The clown is not in any voice channel(s).")
        if player and player.is_connected():
            raise commands.BadArgument("Already in another voice channel.")
        if not self.check_voice_permissions(found_channel):
            bot_permissions = found_channel.permissions_for(found_channel.guild.me)
            required_permissions = {
                "connect": bot_permissions.connect,
                "speak": bot_permissions.speak,
                "view channel": bot_permissions.view_channel,
            }
            missing_perms = "`, `".join(perm for perm, val in required_permissions.items() if not val)
            raise MissingVoicePermissions(f"I'm missing `{missing_perms}` permission(s) for the voice channel.")

        player = await found_channel.connect(cls=wavelink.Player)
        track = await wavelink.NodePool.get_node(id=ClownWeek.WAVELINK_NODE_NAME).get_tracks(
            cls=wavelink.YouTubeTrack,
            query="https://www.youtube.com/watch?v=x3SxEOvAOEg",
        )
        await player.play(track[0])

    @honk.error
    async def honk_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed = self.bot.create_embed()
        if isinstance(error, (MissingClown, MissingData, MissingVoicePermissions)):
            error_embed.description = f"{Icons.WARN} {error}"
            await ctx.send(embed=error_embed, delete_after=3)
        elif isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed, delete_after=3)

    @commands.command(name="disconnect", aliases=["dc"], hidden=True)
    @commands.is_owner()
    async def disconnect(self, ctx: commands.Context) -> None:
        """Disconnect Pingu from a voice channel for debugging purposes"""
        embed = self.bot.create_embed()
        player = ctx.guild.voice_client
        if player and player.is_connected():
            await player.disconnect()
            embed.description = f"{Icons.ALERT} Disconnected from voice channel."
            await ctx.send(embed=embed, delete_after=3)
            return

        embed.description = f"{Icons.WARN} No voice channel found to disconnect from."
        await ctx.send(embed=embed, delete_after=3)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Triggers when the clown joins a voice channel and was not previously in another voice
        channel in the server.

        It will ignore rapid connects and disconnects from the clown, and will only reconnect
        after a set amount of time.
        """
        if member.bot or not self.check_clown_voice_state(member, after.channel):
            return

        player = member.guild.voice_client
        track = await wavelink.NodePool.get_node(id=ClownWeek.WAVELINK_NODE_NAME).get_tracks(
            cls=wavelink.YouTubeTrack,
            query="https://www.youtube.com/watch?v=x3SxEOvAOEg",
        )

        # Clown connects to voice from disconnected state
        if not before.channel and after.channel:
            is_active = player and player.is_connected()
            is_clown_deaf = member.voice.self_deaf or member.voice.deaf

            if member.guild.id in ClownWeek.IDLE_PLAYERS:
                disconnect_task = ClownWeek.IDLE_PLAYERS.pop(member.guild.id)
                disconnect_task.cancel()

            if is_active:
                if is_clown_deaf or player.channel.id != after.channel.id:
                    await player.pause()
                    return

                if not is_clown_deaf and player.channel.id == after.channel.id:
                    await player.resume()
                    return
                return

            clown_data = next(clown for clown in ClownWeek.GUILD_CLOWNS if clown.guild_id == member.guild.id)

            # Skip if a week or more passed
            time_spent = utcnow().date() - clown_data.nomination_date
            if time_spent >= timedelta(days=6):
                self.log.debug(
                    "New nomination needed in '%s'",
                    member.guild.id,
                )
                return

            # Skip if the clown connected within the last hour
            last_joined = utcnow() - clown_data.join_time
            self.log.debug(
                "Clown '%s' last joined %s second(s) ago",
                member.id,
                last_joined.total_seconds(),
            )
            if last_joined <= timedelta(minutes=60):
                self.log.debug("Potential spam connect by '%s' in '%s'", member.id, member.guild.id)
                return

            # Play the audio if all conditions are met
            if not player and len(after.channel.members) >= 3 and self.check_voice_permissions(after.channel):
                # Only update the join time when it can connect and play
                async with async_session() as session:
                    async with session.begin():
                        await session.execute(
                            update(Clown).where(Clown.guild_id == member.guild.id).values(clown_id=member.id)
                        )
                    await session.commit()
                await self.update_cache()

                player = await after.channel.connect(cls=wavelink.Player)
                track = await wavelink.NodePool.get_node(id=ClownWeek.WAVELINK_NODE_NAME).get_tracks(
                    cls=wavelink.YouTubeTrack,
                    query="https://www.youtube.com/watch?v=x3SxEOvAOEg",
                )
                await player.play(track[0])
                # Pause if clown joined while deaf
                if member.voice.self_deaf or member.voice.deaf:
                    await player.pause()
            return

        # Play while the clown is not deafened
        if before.channel and after.channel:
            is_active = player and player.is_connected()
            is_clown_deaf = member.voice.self_deaf or member.voice.deaf

            if is_active:
                if is_clown_deaf or player.channel.id != after.channel.id:
                    await player.pause()
                    return

                if not is_clown_deaf and player.channel.id == after.channel.id:
                    await player.resume()
                    return
            return

        # Pause if clown disconnects from voice and auto disconnect after 10 minutes
        if before.channel and not after.channel:
            if player and player.is_connected():
                await player.pause()
                if member.guild.id not in ClownWeek.IDLE_PLAYERS:
                    ClownWeek.IDLE_PLAYERS[member.guild.id] = self.bot.loop.create_task(
                        self.disconnect_idle_player(player, member.guild.id)
                    )


async def setup(bot):
    await bot.add_cog(ClownWeek(bot))
