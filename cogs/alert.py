import asyncio
import logging
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
from pytz import timezone

from common.util import Icons


class Alert(commands.Cog):
    """test"""

    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.message_location = None
        self.sent_message = None

    # async def cog_check(self, ctx):
    #     return await self.bot.is_owner(ctx.author)

    def cog_unload(self):
        self.message_1234.cancel()

    def get_snipe_channel(self, guild: discord.Guild, channel_id: str) -> discord.TextChannel:
        try:
            channel = guild.get_channel(int(channel_id))
        except ValueError:
            raise commands.BadArgument("Not a valid channel id.")
        if not channel:
            raise commands.BadArgument("Channel with this id in the guild does not exist.")
        if channel.type != discord.ChannelType.text:
            raise commands.BadArgument(f"Cannot snipe a {channel.type} channel.")

        self.log.info("Sniping on channel: %s", channel.id)
        return channel

    def check_snipe_permission(self, ctx: commands.Context, channel: discord.TextChannel):
        self_permissions = channel.permissions_for(ctx.me)
        if not self_permissions.send_messages:
            self.log.error("Missing permission to send messages")
            raise commands.BadArgument("Missing permission to send messages.")

    async def start_snipe(self):
        if self.message_1234.is_running():
            self.message_1234.restart()
        else:
            self.message_1234.start()

    @commands.group(name="snipe", hidden=True)
    @commands.is_owner()
    async def snipe(self, ctx: commands.Context):
        """Check the snipe status"""
        if ctx.invoked_subcommand:
            return

        # TODO: Add mechanism to get the snipe time
        await ctx.send(f"{Icons.ALERT} Next snipe will happen in: [TODO: implement]", delete_after=3)

    @snipe.command(name="remote", aliases=["r"])
    async def remote_snipe(self, ctx: commands.Context, guild_id: str, channel_id: str):
        try:
            sniped_guild = self.bot.get_guild(int(guild_id))
        except ValueError:
            raise commands.BadArgument("Not a valid guild id.")
        if not sniped_guild:
            raise commands.BadArgument("Guild with this id does not exist.")

        sniped_channel = self.get_snipe_channel(sniped_guild, channel_id)
        self.check_snipe_permission(ctx, sniped_channel)

        self.message_location = sniped_channel
        await self.start_snipe()
        await ctx.send(f"{Icons.ALERT} Snipe set to guild/channel: {sniped_guild.id}/{sniped_channel.id}")

    @remote_snipe.error
    async def remote_snipe_error_handler(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{Icons.ERROR} Missing `{error.param.name}` to send message to", delete_after=3)
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{Icons.ERROR} {error}", delete_after=3)

    @commands.command(name="cancelsnipe", aliases=["csnipe"], hidden=True)
    @commands.is_owner()
    async def cancel_snipe(self, ctx: commands.Context):
        if self.message_1234.is_running():
            self.sent_message = None
            self.message_1234.cancel()
            await ctx.send(f"{Icons.SUCCESS} Stopped snipe on channel: {self.message_location.id}")
        else:
            raise commands.BadArgument("Task already stopped.")

    @cancel_snipe.error
    async def cancel_snipe_error_handler(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{Icons.ERROR} {error}", delete_after=3)

    @tasks.loop()
    async def message_1234(self):
        # Python times, timezones, and daylight savings is hard
        utc = timezone("UTC")
        # Account for daylight savings ("US/Eastern" is EST only)
        eastern = timezone("America/New_York")
        now = utc.localize(datetime.utcnow())
        if self.message_location:
            today_12am = eastern.localize(datetime(now.year, now.month, now.day, 0, 34))
            today_12pm = eastern.localize(datetime(now.year, now.month, now.day, 12, 34))
            tomorrow_12am = eastern.localize(datetime(now.year, now.month, now.day + 1, 0, 34))

            debug_mode = False
            if debug_mode:
                wait_this_long = 60
                self.log.info(
                    "UTC: %s | Eastern: %s",
                    now.astimezone(utc),
                    now.astimezone(eastern),
                )
                self.log.info(
                    "UTC: %s | Eastern: %s",
                    today_12am.astimezone(utc),
                    today_12am.astimezone(eastern),
                )
                self.log.info(
                    "UTC: %s | Eastern: %s",
                    today_12pm.astimezone(utc),
                    today_12pm.astimezone(eastern),
                )
                self.log.info(
                    "UTC: %s | Eastern: %s",
                    tomorrow_12am.astimezone(utc),
                    tomorrow_12am.astimezone(eastern),
                )
                self.log.warning("DEBUG MODE ENABLED: Firing in the next %s seconds", wait_this_long)
                await asyncio.sleep(wait_this_long)
            elif now <= today_12am:
                wait = (today_12am - now).total_seconds()
                self.log.info(
                    "Sending message at 12:34 AM (%s left)",
                    str(timedelta(seconds=round(wait))),
                )
                await discord.utils.sleep_until(today_12am)
            elif now <= today_12pm:
                wait = (today_12pm - now).total_seconds()
                self.log.info(
                    "Sending message at 12:34 PM (%s left)",
                    str(timedelta(seconds=round(wait))),
                )
                await discord.utils.sleep_until(today_12pm)
            else:
                wait = (tomorrow_12am - now).total_seconds()
                self.log.info(
                    "Sending message at 12:34 AM tomorrow (%s left)",
                    str(timedelta(seconds=round(wait))),
                )
                await discord.utils.sleep_until(tomorrow_12am)

        # Things could have happened in the meantime, so check again
        if self.bot.get_channel(self.message_location.id):
            self.log.info(
                "Sending message to text channel (id: %s, name: %s)",
                self.message_location.id,
                self.message_location.name,
            )
            self.sent_message = await self.message_location.send("12:34")
        else:
            self.log.error("Channel disappeared before message was sent; stopping task")
            self.message_location = None
            self.message_1234.cancel()

    @message_1234.before_loop
    async def prep_1234(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Sense if someone with moderator powers deletes 12:34"""
        if self.sent_message and self.sent_message.id == message.id:
            message_guild = message.guild
            message_deleter = None
            if message_guild.id == 143909103951937536 or message_guild.id == 276571138455502848:
                self_permissions = message.channel.permissions_for(message_guild.me)
                if self_permissions.view_audit_log:
                    async for entry in message_guild.audit_logs(limit=20, action=discord.AuditLogAction.message_delete):
                        if entry.target == message_guild.me:
                            message_deleter = entry.user
                            break

            # Checking who deleted the message requires the Audit Log permission
            if not message_deleter:
                self.sent_message = await message.channel.send("Stop deleting my messages >:(")
            else:
                self.sent_message = await message.channel.send(
                    f"{message_deleter.mention} Stop deleting my messages >:("
                )


def setup(bot):
    bot.add_cog(Alert(bot))
