import logging
from datetime import datetime

import discord
from discord.ext import commands, tasks
from pytz import timezone

from common.util import Icons


class Alert(commands.Cog):
    """test"""

    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.snipe_location = None
        self.snipe_time = None
        self.sent_message = None

    # async def cog_check(self, ctx):
    #     return await self.bot.is_owner(ctx.author)

    def cog_unload(self):
        self.send_snipe.cancel()

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

    def check_snipe_permission(self, channel: discord.TextChannel) -> bool:
        self_permissions = channel.permissions_for(channel.guild.me)
        if not self_permissions.send_messages:
            return False
        return True

    async def setup_snipe(self):
        if self.send_snipe.is_running():
            self.send_snipe.restart()
        else:
            self.send_snipe.start()

    @commands.group(name="snipe", hidden=True)
    @commands.is_owner()
    async def snipe_info(self, ctx: commands.Context):
        """Check the snipe status"""
        if ctx.invoked_subcommand:
            return

        if not self.snipe_location:
            raise commands.BadArgument("No snipe has been set.")

        await ctx.send(
            f"{Icons.ALERT} Sending snipe to guild '{self.snipe_location.guild.name}'"
            + f" (id: {self.snipe_location.guild.id}) on channel '{self.snipe_location.name}'"
            + f" (id: {self.snipe_location.id}) at `{self.snipe_time}`."
        )

    @snipe_info.error
    async def snipe_error_handler(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{Icons.ERROR} {error}")

    @snipe_info.command(name="remote", aliases=["r"])
    async def remote_snipe(self, ctx: commands.Context, guild_id: str, channel_id: str):
        """Set the snipe location"""
        try:
            sniped_guild = self.bot.get_guild(int(guild_id))
        except ValueError:
            raise commands.BadArgument("Not a valid guild id.")
        if not sniped_guild:
            raise commands.BadArgument("Guild with this id does not exist.")

        sniped_channel = self.get_snipe_channel(sniped_guild, channel_id)
        if not self.check_snipe_permission(sniped_channel):
            raise commands.BadArgument("Missing permission to send messages.")

        self.snipe_location = sniped_channel
        await self.setup_snipe()
        await ctx.send(
            f"{Icons.ALERT} Sending snipe to guild '{sniped_guild.name}' (id: {sniped_guild.id})"
            + f" on channel '{sniped_channel.name}' (id: {sniped_channel.id})."
        )

    @remote_snipe.error
    async def remote_snipe_error_handler(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"{Icons.ERROR} Missing `{error.param.name}` to send message to")
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{Icons.ERROR} {error}")

    @commands.command(name="cancelsnipe", aliases=["csnipe"], hidden=True)
    @commands.is_owner()
    async def cancel_snipe(self, ctx: commands.Context):
        """Cancel the snipe if it exists"""
        if self.send_snipe.is_running():
            await ctx.send(f"{Icons.SUCCESS} Stopped snipe")
            self.send_snipe.cancel()
        else:
            raise commands.BadArgument("Snipe not active.")

    @cancel_snipe.error
    async def cancel_snipe_error_handler(self, ctx: commands.Context, error):
        if isinstance(error, commands.BadArgument):
            await ctx.send(f"{Icons.ERROR} {error}")

    @tasks.loop()
    async def send_snipe(self):
        if self.snipe_location:
            # Account for daylight savings ("US/Eastern" is EST only)
            adjusted_timezone = timezone("America/New_York")
            utc = timezone("UTC")

            now = datetime.now(adjusted_timezone)
            today_midnight = adjusted_timezone.localize(datetime(now.year, now.month, now.day, 0, 34))
            today_noon = adjusted_timezone.localize(datetime(now.year, now.month, now.day, 12, 34))
            tomorrow_midnight = adjusted_timezone.localize(datetime(now.year, now.month, now.day + 1, 0, 34))

            if now <= today_midnight:
                wait_time = today_midnight
            elif now <= today_noon:
                wait_time = today_noon
            else:
                wait_time = tomorrow_midnight

            self.snipe_time = wait_time
            self.log.debug(
                "Sending snipe at '%s' local time ('%s' utc)",
                self.snipe_time,
                self.snipe_time.astimezone(utc),
            )
            self.log.debug(
                "now: %s, today 12am: %s, today 12pm: %s, tomrrow 12am: %s",
                now,
                today_midnight,
                today_noon,
                tomorrow_midnight,
            )
            await discord.utils.sleep_until(wait_time)

            # Something could have happened in the meantime, so check the channel
            if self.bot.get_channel(self.snipe_location.id) and self.check_snipe_permission(self.snipe_location):
                self.sent_message = await self.snipe_location.send("12:34")
            else:
                self.log.error("Channel is inaccessible; stopping snipe")
                self.snipe_location = None
                self.snipe_time = None
                self.sent_message = None
                self.send_snipe.cancel()

    @send_snipe.before_loop
    async def prep_snipe(self):
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
