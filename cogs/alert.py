"""You already know what this does 👀"""
import asyncio
import logging
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
from pytz import timezone


class Alert(commands.Cog):
    """12:34"""

    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.message_location = None  # Singular location
        self.sent_message = None

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    def cog_unload(self):
        self.log.info("Cog unloaded; stopping 1234 and resetting message location to nowhere")
        self.message_location = None
        self.sent_message = None
        self.message_1234.cancel()

    @commands.command(name="1234", hidden=True)
    async def set_1234(self, ctx, guild_id: str = None, channel_id: str = None):
        """Sets where to send 12:34"""
        # Temporary variable to compare with the cog level location
        preliminary_location = None

        # Parse the location to send the message
        if not guild_id:
            self.log.info("No location specified; sending in current channel")
            preliminary_location = ctx.message.channel
            # await ctx.send(
            #     f"{self.bot.icons['info']} No IDs specified. Sending message in current channel.")
        elif not channel_id:
            raise commands.BadArgument("Missing channel ID to send in server.")

        # Locate requested server and channel
        if not preliminary_location:
            # Error checking if given IDs are not random strings
            try:
                guild_id = int(guild_id)
                channel_id = int(channel_id)
            except ValueError as exc:
                self.log.error("Failed to parse server ID and/or text channel ID")
                raise commands.BadArgument("Given ID(s) were not a numerical value.") from exc

            # Search for the server using its ID
            selected_guild = self.bot.get_guild(guild_id)
            if not selected_guild:
                self.log.error("Unable to find requested server")
                raise commands.BadArgument("Unable to find requested server")
            self.log.info(
                "Found requested server (id: %s, name: %s)",
                selected_guild.id,
                selected_guild.name,
            )

            # Search for the channel using its ID
            selected_channel = selected_guild.get_channel(channel_id)
            if not selected_channel:
                self.log.error("Unable to find requested channel")
                raise commands.BadArgument("Specified text channel does not exist or read permission(s) were not given")
            self.log.info(
                "Found requested text channel (id: %s, name: %s)",
                selected_channel.id,
                selected_channel.name,
            )

            preliminary_location = selected_channel

        self.message_location = preliminary_location

        # Check the channel permissions
        self_permissions = self.message_location.permissions_for(ctx.me)
        if not self_permissions.send_messages:
            self.log.error("Missing permission to send messages in the specified location")
            raise commands.BadArgument("Missing permission to send messages in that channel.")

        # Restart the task (the following condition will be used when discord.py 1.4.0 is released)
        if self.message_1234.is_running():  # pylint: disable=no-member
            self.message_1234.restart()  # pylint: disable=no-member
        # self.message_1234.cancel() # pylint: disable=no-member
        # await asyncio.sleep(1)
        else:
            self.message_1234.start()  # pylint: disable=no-member

    @commands.command(name="no1234", hidden=True)
    async def stop_1234(self, ctx):  # pylint: disable=unused-argument
        """Stop 12:34 from running"""
        self.log.info("Manual override to stop 1234 received; stopping task")
        self.message_location = None
        self.sent_message = None
        self.message_1234.cancel()  # pylint: disable=no-member

    @tasks.loop()
    async def message_1234(self):
        """Become the King of 12:34 in a channel; complains if admin abuse is detected"""
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
        """Stop the task from running until Pingu is in the ready state"""
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
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Alert(bot))
