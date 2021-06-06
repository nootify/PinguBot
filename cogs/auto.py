import logging
from datetime import datetime, timedelta
from inspect import Parameter

import discord
from discord.ext import commands, tasks
from discord.utils import sleep_until
from humanize import naturaldelta
from pytimeparse.timeparse import timeparse
from pytz import timezone

from common.utils import Icons
from db.models import Reminder


class Auto(commands.Cog):
    """All things automated™"""

    QUEUED_REMINDERS = {}

    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.snipe_location = None
        self.snipe_time = None
        self.sent_message = None
        self.check_reminders.start()

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

    @commands.group(name="remindme", aliases=["remind", "reminder"], invoke_without_command=True)
    @commands.cooldown(rate=1, per=3.0, type=commands.BucketType.member)
    async def remind(self, ctx: commands.Context, *, when: str):
        """Remind yourself about something in the future

        - The time goes first and it has to be some sort of human readable offset
        - For example: "1h 5m", "3.4 days", "4:13"
        - Then put `to` and what you want to be reminded about
        - e.g. `remindme 4 hours to do X and Y`
        """
        try:
            future_time, text = when.split(" to ", 1)
        except ValueError:
            raise commands.MissingRequiredArgument(Parameter("to", Parameter.POSITIONAL_ONLY))
        else:
            future_time = future_time.strip()
            text = text.strip()
            if not text:
                raise commands.MissingRequiredArgument(Parameter("text", Parameter.POSITIONAL_ONLY))
            if len(text) > 1000:
                raise commands.BadArgument("Reminder text is too long.")

        parsed_time = timeparse(future_time)
        if not parsed_time:
            raise commands.BadArgument("Unable to parse given time. Check if there are typos.")
        parsed_offset = timedelta(seconds=parsed_time)
        remind_offset = datetime.utcnow() + parsed_offset
        new_reminder = Reminder(
            reminder_text=text, reminder_time=remind_offset, user_id=ctx.author.id, channel_id=ctx.channel.id
        )
        await new_reminder.create()
        if parsed_offset < timedelta(minutes=30) and new_reminder.reminder_id not in Auto.QUEUED_REMINDERS:
            Auto.QUEUED_REMINDERS[new_reminder.reminder_id] = self.bot.loop.create_task(
                self.setup_reminder(new_reminder)
            )

        readable_offset = naturaldelta(remind_offset)
        embed = self.bot.create_embed(
            description=f"{Icons.ALERT} {ctx.author.mention}, you will be reminded about this in {readable_offset}"
        )
        await ctx.send(embed=embed)

    @remind.error
    async def remind_error_handler(self, ctx: commands.Context, error):
        error_embed = self.bot.create_embed()
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "when":
                error_embed.description = f"{Icons.ERROR} Missing time offset."
                await ctx.send(embed=error_embed)
            if error.param.name == "to":
                error_embed.description = f"{Icons.ERROR} Missing `to` keyword."
                await ctx.send(embed=error_embed)
            if error.param.name == "text":
                error_embed.description = f"{Icons.ERROR} Missing text to remind you about."
                await ctx.send(embed=error_embed)
            return
        if isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @remind.command(name="list", aliases=["ls"])
    async def list_reminders(self, ctx: commands.Context):
        """Show the ten latest reminders created by you

        - Also shows the id and when it will send the reminder
        - It will only show reminders that are still active
        - Reminders will be removed if the bot is unable to access the channel
        """
        reminders = (
            await Reminder.query.where(Reminder.user_id == ctx.author.id)
            .order_by(Reminder.reminder_time.asc())
            .limit(10)
            .gino.all()
        )

        embed = self.bot.create_embed(title="Reminders")
        if not reminders:
            embed.description = f"{Icons.ALERT} No reminders were found."
        for reminder in reminders:
            time_left = naturaldelta(reminder.reminder_time)
            embed.add_field(name=f"{reminder.reminder_id}: In {time_left}", value=reminder.reminder_text, inline=False)
        await ctx.send(embed=embed)

    @remind.command(name="clear")
    async def clear_reminders(self, ctx: commands.Context):
        """Clear all of the reminders you made"""
        await Reminder.delete.where(Reminder.user_id == ctx.author.id).gino.status()

        embed = self.bot.create_embed(description=f"{Icons.ALERT} All reminders deleted.")
        await ctx.send(embed=embed)

    @remind.command(name="delete", aliases=["del", "remove", "rm", "cancel"])
    async def delete_reminder(self, ctx: commands.Context, reminder_id: str):
        """Delete a reminder by its id

        - You can only delete reminders that you created
        """
        try:
            reminder_id = int(reminder_id)
        except ValueError:
            raise commands.BadArgument("Reminder id must be a number.")

        reminder = await Reminder.query.where(
            (Reminder.user_id == ctx.author.id) & (Reminder.reminder_id == reminder_id)
        ).gino.all()
        if not reminder:
            raise commands.BadArgument("Reminder with that id was not found.")
        await reminder[0].delete()

        embed = self.bot.create_embed(description=f"{Icons.ALERT} Reminder deleted succesfully.")
        await ctx.send(embed=embed)

    @delete_reminder.error
    async def delete_reminder_error_handler(self, ctx: commands.Context, error):
        error_embed = self.bot.create_embed()
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "reminder_id":
                error_embed.description = f"{Icons.ERROR} Missing reminder id to delete"
                await ctx.send(embed=error_embed)
            return
        if isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @commands.group(name="snipe", hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def snipe_info(self, ctx: commands.Context):
        """Check the snipe status"""
        if not self.snipe_location:
            raise commands.BadArgument("No snipe has been set.")

        snipe_details = f"{Icons.ALERT} Sending snipe to guild '{self.snipe_location.guild.name}'"
        +f" (id: {self.snipe_location.guild.id}) on channel '{self.snipe_location.name}'"
        +f" (id: {self.snipe_location.id}) at `{self.snipe_time}`."
        embed = self.bot.create_embed(description=snipe_details)
        await ctx.send(embed=embed)

    @snipe_info.error
    async def snipe_error_handler(self, ctx: commands.Context, error):
        error_embed = self.bot.create_embed()
        if isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

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
        snipe_details = f"{Icons.ALERT} Sending snipe to guild '{sniped_guild.name}' (id: {sniped_guild.id})"
        +f" on channel '{sniped_channel.name}' (id: {sniped_channel.id})."
        embed = self.bot.create_embed(description=snipe_details)
        await ctx.send(embed=embed)

    @remote_snipe.error
    async def remote_snipe_error_handler(self, ctx: commands.Context, error):
        error_embed = self.bot.create_embed()
        if isinstance(error, commands.MissingRequiredArgument):
            error_embed.description = f"{Icons.ERROR} Missing `{error.param.name}` to send message to"
            await ctx.send(embed=error_embed)
        if isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @snipe_info.command(name="cancel", hidden=True)
    @commands.is_owner()
    async def cancel_snipe(self, ctx: commands.Context):
        """Cancel the snipe if it exists"""
        if self.send_snipe.is_running():
            embed = self.bot.create_embed(description=f"{Icons.SUCCESS} Stopped snipe")
            await ctx.send(embed=embed)
            self.send_snipe.cancel()
        else:
            raise commands.BadArgument("Snipe not active.")

    @cancel_snipe.error
    async def cancel_snipe_error_handler(self, ctx: commands.Context, error):
        error_embed = self.bot.create_embed()
        if isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @tasks.loop(minutes=30)
    async def check_reminders(self):
        check_time = datetime.utcnow() + timedelta(minutes=30)
        rows = await Reminder.query.where(Reminder.reminder_time <= check_time).gino.all()
        for row in rows:
            if row.reminder_id not in Auto.QUEUED_REMINDERS:
                Auto.QUEUED_REMINDERS[row.reminder_id] = self.bot.loop.create_task(self.setup_reminder(row))

    async def setup_reminder(self, reminder: Reminder):
        await sleep_until(reminder.reminder_time)

        ping = self.bot.get_user(reminder.user_id)
        if not ping:
            await reminder.delete()
            return
        channel = self.bot.get_channel(reminder.channel_id)
        if not channel:
            await reminder.delete()
            return

        embed = self.bot.create_embed(title="Don't forget to:", description=reminder.reminder_text)
        try:
            await channel.send(content=ping.mention, embed=embed)
        except discord.HTTPException:
            self.log.debug("Reminder could not be sent because the channel is inaccessible")
        finally:
            await reminder.delete()
            Auto.QUEUED_REMINDERS.pop(reminder.reminder_id)

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
            await sleep_until(wait_time)

            # Something could have happened in the meantime, so check the channel
            if self.bot.get_channel(self.snipe_location.id) and self.check_snipe_permission(self.snipe_location):
                self.sent_message = await self.snipe_location.send("12:34")
            else:
                self.log.error("Channel is inaccessible; stopping snipe")
                self.snipe_location = None
                self.snipe_time = None
                self.sent_message = None
                self.send_snipe.cancel()

    @check_reminders.before_loop
    @send_snipe.before_loop
    async def wait_for_bot(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        """Check who is deleting the snipe message"""
        if self.sent_message and self.sent_message.id == message.id:
            message_deleter = None
            bot_permissions = message.channel.permissions_for(message.guild.me)
            if bot_permissions.view_audit_log:
                async for entry in message.guild.audit_logs(limit=20, action=discord.AuditLogAction.message_delete):
                    if entry.target == message.guild.me:
                        message_deleter = entry.user
                        break

            # Checking who deleted the message requires the Audit Log permission
            if not message_deleter:
                self.sent_message = await message.channel.send("Someone keeps deleting my message :neutral_face:")
            else:
                self.sent_message = await message.channel.send(
                    f"{message_deleter.mention} stop deleting my message :confused:"
                )
            return


def setup(bot):
    bot.add_cog(Auto(bot))
