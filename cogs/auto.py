import asyncio
import logging
import re
from datetime import datetime, timedelta
from inspect import Parameter

import arrow
import discord
from discord.ext import commands, tasks
from discord.utils import sleep_until, utcnow
from pytimeparse.timeparse import timeparse
from pytz import timezone
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils import Icons
from models import Reminder, async_session


class Auto(commands.Cog):
    """All things automated™"""

    QUEUED_REMINDERS = {}

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.snipe_location = None
        self.snipe_time = None
        self.sent_message = None
        self.check_reminders.start()

    async def cog_unload(self) -> None:
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

    async def setup_snipe(self) -> None:
        if self.send_snipe.is_running():
            self.send_snipe.restart()
        else:
            self.send_snipe.start()

    @commands.group(name="remindme", aliases=["remind", "reminder"], invoke_without_command=True)
    @commands.cooldown(rate=1, per=3.0, type=commands.BucketType.member)
    async def remind(self, ctx: commands.Context, *, when: str) -> None:
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
        remind_offset = utcnow() + parsed_offset

        session: AsyncSession
        async with async_session() as session:
            async with session.begin():
                new_reminder = Reminder(
                    reminder_text=text, reminder_time=remind_offset, user_id=ctx.author.id, channel_id=ctx.channel.id
                )
                session.add(new_reminder)
                await session.commit()
            await session.refresh(new_reminder)

        if parsed_offset < timedelta(minutes=30) and new_reminder.reminder_id not in Auto.QUEUED_REMINDERS:
            Auto.QUEUED_REMINDERS[new_reminder.reminder_id] = self.bot.loop.create_task(
                self.setup_reminder(new_reminder)
            )

        readable_offset = arrow.get(remind_offset).humanize()
        embed: discord.Embed = self.bot.create_embed(
            description=f"{Icons.ALERT} {ctx.author.mention}, you will be reminded about this {readable_offset}"
        )
        await ctx.send(embed=embed)

    @remind.error
    async def remind_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed: discord.Embed = self.bot.create_embed()
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "when":
                error_embed.description = f"{Icons.ERROR} Missing time offset."
                await ctx.send(embed=error_embed)
            elif error.param.name == "to":
                error_embed.description = f"{Icons.ERROR} Missing `to` keyword."
                await ctx.send(embed=error_embed)
            elif error.param.name == "text":
                error_embed.description = f"{Icons.ERROR} Missing text to remind you about."
                await ctx.send(embed=error_embed)
        elif isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @remind.command(name="list", aliases=["ls"])
    async def list_reminders(self, ctx: commands.Context) -> None:
        """Show the ten latest reminders created by you

        - Also shows the id and when it will send the reminder
        - It will only show reminders that are still active
        - Reminders will be removed if the bot is unable to access the channel
        """
        session: AsyncSession
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(
                    select(Reminder).where(Reminder.user_id == ctx.author.id).order_by(Reminder.reminder_time).limit(10)
                )
                reminders: list[Reminder] = result.scalars().all()

        embed: discord.Embed = self.bot.create_embed(title="Reminders")
        if not reminders:
            embed.description = f"{Icons.ALERT} No reminders were found."
        for reminder in reminders:
            time_left = arrow.get(reminder.reminder_time).humanize().capitalize()
            embed.add_field(name=f"{reminder.reminder_id} | {time_left}", value=reminder.reminder_text, inline=False)
        await ctx.send(embed=embed)

    @remind.command(name="clear")
    async def clear_reminders(self, ctx: commands.Context) -> None:
        """Clear all of the reminders you made"""
        session: AsyncSession
        async with async_session() as session:
            async with session.begin():
                await session.execute(delete(Reminder).where(Reminder.user_id == ctx.author.id))
                await session.commit()

        embed: discord.Embed = self.bot.create_embed(description=f"{Icons.ALERT} All reminders deleted.")
        await ctx.send(embed=embed)

    @remind.command(name="delete", aliases=["del", "remove", "rm", "cancel"])
    async def delete_reminder(self, ctx: commands.Context, reminder_id: str) -> None:
        """Delete a reminder by its id

        - You can only delete reminders that you created
        """
        try:
            reminder_id = int(reminder_id)
        except ValueError:
            raise commands.BadArgument("Reminder id must be a number.")

        session: AsyncSession
        async with async_session() as session:
            async with session.begin():
                reminder = await session.execute(
                    delete(Reminder).where((Reminder.user_id == ctx.author.id) & (Reminder.reminder_id == reminder_id))
                )
        if not reminder:
            raise commands.BadArgument("Reminder with that id was not found.")

        embed: discord.Embed = self.bot.create_embed(description=f"{Icons.ALERT} Reminder deleted succesfully.")
        await ctx.send(embed=embed)

    @delete_reminder.error
    async def delete_reminder_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed: discord.Embed = self.bot.create_embed()
        if isinstance(error, commands.MissingRequiredArgument):
            if error.param.name == "reminder_id":
                error_embed.description = f"{Icons.ERROR} Missing reminder id to delete"
                await ctx.send(embed=error_embed)
        elif isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @commands.group(name="snipe", hidden=True, invoke_without_command=True)
    @commands.is_owner()
    async def snipe_info(self, ctx: commands.Context) -> None:
        """Check the snipe status"""
        if not self.snipe_location:
            raise commands.BadArgument("No snipe has been set.")

        snipe_details = f"{Icons.ALERT} Sending snipe to guild '{self.snipe_location.guild.name}'"
        +f" (id: {self.snipe_location.guild.id}) on channel '{self.snipe_location.name}'"
        +f" (id: {self.snipe_location.id}) at `{self.snipe_time}`."
        embed: discord.Embed = self.bot.create_embed(description=snipe_details)
        await ctx.send(embed=embed)

    @snipe_info.error
    async def snipe_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed: discord.Embed = self.bot.create_embed()
        if isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @snipe_info.command(name="remote", aliases=["r"])
    async def remote_snipe(self, ctx: commands.Context, guild_id: str, channel_id: str) -> None:
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
        embed: discord.Embed = self.bot.create_embed(description=snipe_details)
        await ctx.send(embed=embed)

    @remote_snipe.error
    async def remote_snipe_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed: discord.Embed = self.bot.create_embed()
        if isinstance(error, commands.MissingRequiredArgument):
            error_embed.description = f"{Icons.ERROR} Missing `{error.param.name}` to send message to"
            await ctx.send(embed=error_embed)
        elif isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @snipe_info.command(name="cancel", hidden=True)
    @commands.is_owner()
    async def cancel_snipe(self, ctx: commands.Context) -> None:
        """Cancel the snipe if it exists"""
        if self.send_snipe.is_running():
            embed: discord.Embed = self.bot.create_embed(description=f"{Icons.SUCCESS} Stopped snipe")
            await ctx.send(embed=embed)
            self.send_snipe.cancel()
        else:
            raise commands.BadArgument("Snipe not active.")

    @cancel_snipe.error
    async def cancel_snipe_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed: discord.Embed = self.bot.create_embed()
        if isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @tasks.loop(minutes=30)
    async def check_reminders(self) -> None:
        check_time = utcnow() + timedelta(minutes=30)
        session: AsyncSession
        async with async_session() as session:
            async with session.begin():
                result = await session.execute(select(Reminder).where(Reminder.reminder_time <= check_time))
                rows: list[Reminder] = result.scalars().all()
        for row in rows:
            if row.reminder_id not in Auto.QUEUED_REMINDERS:
                Auto.QUEUED_REMINDERS[row.reminder_id] = self.bot.loop.create_task(self.setup_reminder(row))

    async def setup_reminder(self, reminder: Reminder) -> None:
        await sleep_until(reminder.reminder_time)

        session: AsyncSession
        ping = self.bot.get_user(reminder.user_id)
        channel = self.bot.get_channel(reminder.channel_id)
        if not ping or not channel:
            async with async_session() as session:
                async with session.begin():
                    await session.execute(delete(Reminder).where(Reminder.reminder_id == reminder.reminder_id))
                    await session.commit()
            return

        embed: discord.Embed = self.bot.create_embed(title="Don't forget to:", description=reminder.reminder_text)
        try:
            await channel.send(content=ping.mention, embed=embed)
        except discord.HTTPException:
            self.log.debug("Reminder could not be sent because the channel is inaccessible")
        finally:
            async with async_session() as session:
                async with session.begin():
                    await session.execute(delete(Reminder).where(Reminder.reminder_id == reminder.reminder_id))
                    await session.commit()
            Auto.QUEUED_REMINDERS.pop(reminder.reminder_id)

    @tasks.loop()
    async def send_snipe(self) -> None:
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
    async def wait_for_bot(self) -> None:
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return

        if tiktok_link := re.search(
            r"https?://(www\.)?tiktok\.com/(t/([a-zA-Z0-9]+)|@(.*?)/video/(\d+))(.*?)/?", message.content
        ):
            await asyncio.sleep(1)
            await message.edit(suppress=True)  # hide the fake video preview from tiktok

            tiktok_embed = tiktok_link.group(0).replace("tiktok.com/", "vxtiktok.com/", 1)
            await message.channel.send(f"[[View on Tiktok]]({tiktok_embed})", mention_author=False, view=DeleteButton())
            return

        if twitter_link := re.search(
            r"https?://(www\.)?(twitter|x)\.com/([a-zA-Z0-9_]+)/status/(\d+)", message.content
        ):
            await asyncio.sleep(1)
            await message.edit(suppress=True)

            twitter_embed = twitter_link.group(0)
            if "x.com/" in twitter_embed:
                twitter_embed = twitter_embed.replace("x.com/", "fxtwitter.com/", 1)
                await message.channel.send(
                    f"[[View on Twitter/X]]({twitter_embed})", mention_author=False, view=DeleteButton()
                )
            elif "twitter.com/":
                twitter_embed = twitter_embed.replace("twitter.com/", "fxtwitter.com/", 1)
                await message.channel.send(
                    f"[[View on Twitter/X]]({twitter_embed})", mention_author=False, view=DeleteButton()
                )
            else:
                self.log.error("Twitter link embed failed with link: '%s' (found: '%s')", twitter_link, twitter_embed)
            return

        if reddit_link := re.search(
            r"https?://(www\.|old\.)?reddit\.com/(((r|u|user)/([a-zA-Z0-9_]+)(/s/|/comments/)?([a-zA-Z0-9_]+)(/[a-zA-Z0-9_]+)?(/[a-zA-Z0-9_]+)?)|([a-zA-Z0-9]+))/?",
            message.content,
        ):
            await asyncio.sleep(1)
            if re.search(r"https?://(www\.|old\.)?reddit\.com/(r|u|user)/([a-zA-Z0-9_]+)/?$", message.content):
                return
            await message.edit(suppress=True)

            if "old.reddit.com/" in reddit_link.group(0):
                reddit_embed = reddit_link.group(0).replace("old.reddit.com/", "vxreddit.com/", 1)
            else:
                reddit_embed = reddit_link.group(0).replace("reddit.com/", "vxreddit.com/", 1)
            await message.channel.send(f"[[View on Reddit]]({reddit_embed})", mention_author=False, view=DeleteButton())
            return


class DeleteButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(style=discord.ButtonStyle.blurple, custom_id="persistent_view:delete", emoji="\N{WASTEBASKET}")
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.message.edit(view=None)

        # emoji list: https://www.unicode.org/Public/15.0.0/ucd/emoji/emoji-data.txt
        confirm_view = ConfirmButtonView()
        await interaction.response.send_message(
            content="Delete this message?", view=confirm_view, ephemeral=True, delete_after=10.0
        )
        await confirm_view.wait()

        try:
            if confirm_view.value is True:
                await interaction.edit_original_response(content="Message successfully deleted", view=None)
                await interaction.message.delete()
            else:
                await interaction.edit_original_response(content="Message was not deleted", view=None)
                await interaction.message.edit(view=self)
        except discord.NotFound:
            await interaction.edit_original_response(content="Message no longer exists", view=None)


class ConfirmButtonView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=7)
        self.value = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.blurple)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.grey)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self.stop()


async def setup(bot: commands.Bot):
    await bot.add_cog(Auto(bot))
