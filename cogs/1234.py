import asyncio
import logging
from datetime import datetime, timedelta

import discord
from discord.ext import commands, tasks
from pytz import timezone


class Alert1234(commands.Cog):
    # pylint: disable=no-member
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.message_location = None

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    def cog_unload(self):
        self.log.info("Stopping 1234 and resetting message location to nowhere")
        self.message_location = None
        self.message_1234.cancel()

    @commands.command(name="1234", hidden=True)
    async def set_1234(self, ctx, requested_guild_id=None, requested_channel_id=None):
        # Parse IDs into workable arguments
        try:
            if requested_guild_id is not None and requested_channel_id is not None:
                requested_guild_id = int(requested_guild_id)
                requested_channel_id = int(requested_channel_id)
            elif requested_guild_id is not None and requested_channel_id is None:
                raise commands.BadArgument("Missing channel id to send to.")
            else:
                await ctx.send(f"{self.bot.icons['info']} No IDs specified. Sending message in current channel.")
        except ValueError:
            raise commands.BadArgument("Given ID(s) were not a numerical value.")

        # Reset cache on each call
        self.message_location = None

        # Search for the server id within all the ones that Pingu is connected to
        if requested_guild_id is not None and requested_channel_id is not None:
            selected_guild = self.bot.get_guild(requested_guild_id)
            if selected_guild is None:
                raise commands.BadArgument("Unable to find requested server")
            self.log.info(f"Found requested server (id: {selected_guild.id}, name: {selected_guild.name})")

            # Search for the channel id within all of the visible text channels in the server
            for text_channel in selected_guild.text_channels:
                if text_channel.id == requested_channel_id:
                    self.log.info(f"Found requested text channel (id: {text_channel.id}, name: {text_channel.name})")
                    self.message_location = text_channel
                    break
            if self.message_location is None:
                raise commands.BadArgument("Unable to find requested text channel in server")
        else:
            # Default to current channel when IDs are not given
            self.log.info("No location specified; sending in current channel")
            self.message_location = ctx.message.channel

        # Check the channel is usable
        self_permissions = self.message_location.permissions_for(ctx.me)
        if not self_permissions.send_messages:
            raise commands.BadArgument("Missing permission to send messages in that channel.")

        # Restart the task (the following condition will be used when discord.py 1.4.0 is released)
        # if self.message_1234.is_running():
        #     self.message_1234.restart()
        self.message_1234.cancel()
        await asyncio.sleep(1)
        self.message_1234.start()

    @tasks.loop(count=1)
    async def message_1234(self):
        if self.bot.get_channel(self.message_location.id) is not None:
            self.log.info(f"Sending message to text channel"
                          f" (id: {self.message_location.id}, name: {self.message_location.name})")
            await self.message_location.send("12:34")
        else:
            self.log.error("Channel was deleted before message was sent; resetting location and stopping task")
            self.message_location = None
            self.message_1234.cancel()

    @message_1234.before_loop
    async def prep_1234(self):
        await self.bot.wait_until_ready()

        # Python times, timezones, and daylight savings is hard
        utc = timezone("UTC")
        eastern = timezone("America/New_York")  # Accounts for daylight savings ("US/Eastern" is EST only)
        now = utc.localize(datetime.utcnow())
        if self.message_location is not None:
            today_12am = eastern.localize(datetime(now.year, now.month, now.day, 0, 34))
            today_12pm = eastern.localize(datetime(now.year, now.month, now.day, 12, 34))
            tomorrow_12am = eastern.localize(datetime(now.year, now.month, now.day + 1, 0, 34))

            debug_mode = False
            if debug_mode:
                self.log.info(f"UTC: {now.astimezone(utc)} | Eastern: {now.astimezone(eastern)}")
                self.log.info(f"UTC: {today_12am.astimezone(utc)} | Eastern: {today_12am.astimezone(eastern)}")
                self.log.info(f"UTC: {today_12pm.astimezone(utc)} | Eastern: {today_12pm.astimezone(eastern)}")
                self.log.info(f"UTC: {tomorrow_12am.astimezone(utc)} | Eastern: {tomorrow_12am.astimezone(eastern)}")
                self.log.info("DEBUG MODE ENABLED: Firing in the next 3 seconds")
                await asyncio.sleep(3)
            elif now <= today_12am:
                wait = (today_12am - now).total_seconds()
                self.log.info(f"Sending message at 12:34 AM ({str(timedelta(seconds=round(wait)))} left)")
                await discord.utils.sleep_until(today_12am)
            elif now <= today_12pm:
                wait = (today_12pm - now).total_seconds()
                self.log.info(f"Sending message at 12:34 PM ({str(timedelta(seconds=round(wait)))} left)")
                await discord.utils.sleep_until(today_12pm)
            else:
                wait = (tomorrow_12am - now).total_seconds()
                self.log.info(f"Sending message at 12:34 AM tomorrow ({str(timedelta(seconds=round(wait)))} left)")
                await discord.utils.sleep_until(tomorrow_12am)


def setup(bot):
    bot.add_cog(Alert1234(bot))
