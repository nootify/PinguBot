import logging
import platform
from datetime import datetime
from zoneinfo import ZoneInfo

import discord
import psutil
from discord import app_commands
from discord.ext import commands
from discord.utils import utcnow
from humanize import naturalsize
from playwright.async_api import async_playwright
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.utils import Icons
from models import Nickname, async_session


class Misc(commands.Cog):
    """Commands not in a specific category"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.proc = psutil.Process()
        self.proc.cpu_percent()

    @app_commands.command(name="word")
    async def word_daily(self, interaction: discord.Interaction, date: str = None):
        """Gets the word of the day from the Merriam-Webster dictionary

        Args:
            date (str): the day to look up in [mm/dd/yy] format
        """
        tz_origin = ZoneInfo("America/New_York")
        if not date:
            lookup_date = datetime.now(tz=tz_origin).date()
        else:
            try:
                given_datetime = datetime.strptime(date, "%m/%d/%y").replace(tzinfo=tz_origin)
                lookup_date = given_datetime.date()
            except ValueError:
                await interaction.response.send_message(
                    "Invalid date given. Make sure you formatted it like: mm/dd/yy",
                    ephemeral=True,
                    delete_after=5.0,
                )
                return
            else:
                today = datetime.now(tz=tz_origin)
                if given_datetime > today:
                    await interaction.response.send_message(
                        "Sorry, time traveling is off-limits.",
                        ephemeral=True,
                        delete_after=5.0,
                    )
                    return

        await interaction.response.defer()
        url = f"https://www.merriam-webster.com/word-of-the-day/{lookup_date}"
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page()
            await page.goto(url)

            try:
                word_locator = page.locator('[class="word-header-txt"]')
                word = await word_locator.text_content()

                attribute_locator = page.locator('[class="main-attr"]')
                attribute = await attribute_locator.text_content()

                pronunciation_locator = page.locator('[class="word-syllables"]')
                pronunciation = await pronunciation_locator.text_content()

                content_locator = page.locator('[class="wod-definition-container"]')
                definition = await content_locator.locator(":nth-match(p, 1)").text_content()
            except TimeoutError:
                await interaction.followup.send(
                    "Sorry, something went wrong or the website is not available. Try again later."
                )
                await browser.close()
                return
            else:
                await browser.close()

        description = f"*{attribute}* | {pronunciation}\n\n{definition}"
        embed: discord.Embed = self.bot.create_embed(title=word, description=description, url=url)
        embed.set_footer(text=f"Word of the day for {lookup_date.strftime('%B %-m, %Y')}")
        await interaction.followup.send(embed=embed)

    @commands.command(name="status", aliases=["about", "stats"])
    @commands.cooldown(rate=1, per=3.0, type=commands.BucketType.channel)
    async def pingu_status(self, ctx: commands.Context) -> None:
        """Show some detailed info about Pingu"""
        # Embed header and footer
        py_version = platform.python_version()
        dpy_version = discord.__version__
        bot_ping = round(self.bot.latency, 4) * 1000  # This is in ms
        ping_icon = "🟢"
        if int(bot_ping) >= 100:
            ping_icon = "🟡"
        elif int(bot_ping) >= 200:
            ping_icon = "🔴"

        # Pingu
        bot_account = self.bot.user
        bot_version = self.bot.pingu_version
        bot_owner = self.bot.get_user(self.bot.owner_id)

        # System
        os_name = f"{platform.system()} {platform.release()}"
        logical_cores = psutil.cpu_count()
        physical_cores = psutil.cpu_count(logical=False)
        sys_mem = psutil.virtual_memory()
        sys_mem_total = naturalsize(sys_mem.total, binary=True)
        # sys_mem_available = naturalsize(sys_mem.available)

        # Quick Overview
        total_guilds = len(self.bot.guilds)
        total_channels = sum(1 for _ in self.bot.get_all_channels())
        total_users = len(self.bot.users)
        total_cogs = len(self.bot.cogs)
        total_commands = sum(1 for _ in self.bot.walk_commands())

        # Usage
        with self.proc.oneshot():
            # Memory used by the bot in bytes
            mem = self.proc.memory_full_info()
            all_mem_used = naturalsize(mem.rss, binary=True)  # Physical memory
            # all_vmem_used = naturalsize(mem.vms) # Virtual memory
            main_mem_used = naturalsize(mem.uss, binary=True)

            # Percentage calculations
            bot_cpu_percent = self.proc.cpu_percent()
            main_mem_percent = (mem.uss / sys_mem.total) * 100  # Memory usage of main thread
            all_mem_percent = (mem.rss / sys_mem.total) * 100  # Memory usage of all threads
            # sys_mem_percent = 100 - sys_mem.percent  # Memory usage of the OS

        # Processes
        bot_threads = [thread.id for thread in self.proc.threads()]
        bot_threads.sort()
        bot_pids = ", ".join(str(thread_id) for thread_id in bot_threads)

        # Uptime calculations
        diff = utcnow() - self.bot.boot_time
        hrs, remainder = divmod(int(diff.total_seconds()), 3600)
        mins, secs = divmod(remainder, 60)
        days, hrs = divmod(hrs, 24)
        total_uptime = f"**{days}** days, **{hrs}** hours,\n" + f"**{mins}** minutes, **{secs}** seconds"

        # Embed stats into the message
        stats_embed: discord.Embed = self.bot.create_embed()
        stats_embed.set_author(name="Pingu Status", icon_url=ctx.me.display_avatar)
        stats_embed.set_footer(
            text=f"{ping_icon} Ping: {bot_ping:.2f} ms • Running on Python {py_version} and Discord.py {dpy_version}"
        )
        stats_fields = [
            (
                "Bot",
                f"**Name:** {bot_account.name}\n"
                + f"**Tag:** {bot_account.discriminator}\n"
                + f"**ID:** {bot_account.id}\n"
                + f"**Version:** {bot_version}\n"
                + f"**Owner:** {bot_owner}",
            ),
            (
                "System",
                f"**OS:** {os_name}\n"
                + "**CPU Cores:**\n"
                + f"Physical: {physical_cores} / Logical: {logical_cores}\n"
                + f"**RAM:** {sys_mem_total}",
            ),
            (
                "Overview",
                f"**Guilds:** {total_guilds}\n"
                + f"**Channels:** {total_channels}\n"
                + f"**Users:** {total_users}\n"
                + f"**Cogs:** {total_cogs}\n"
                + f"**Commands:** {total_commands}",
            ),
            (
                "Usage",
                f"**CPU:** {bot_cpu_percent:.02f}%\n"
                + "**RAM:**\n"
                + f"Main: {main_mem_used} ({main_mem_percent:.02f}%)\n"
                + f"Total: {all_mem_used} ({all_mem_percent:.02f}%)\n",
            ),
            (
                "Processes",
                f"**PIDs:** {bot_pids}\n" + f"**Threads:** {len(bot_threads)}\n" + f"**Uptime:**\n{total_uptime}",
            ),
            ("Sharding", "Currently not enabled"),
        ]
        for name, value in stats_fields:
            stats_embed.add_field(name=name, value=value, inline=True)
        await ctx.send(embed=stats_embed)

    @commands.group(name="yoink", invoke_without_command=True)
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.member)
    async def yoink(self, ctx: commands.Context, *, user: discord.Member = None) -> None:
        """Steal a picture from someone's profile or the server itself

        - Omit **[user]** to yoink your own profile picture
        - You can either ping someone or type a Discord username/server nickname exactly without the @
        """
        if not user:
            await ctx.send(ctx.author.display_avatar)
        else:
            await ctx.send(user.display_avatar)

    @yoink.command(name="banner")
    @commands.cooldown(rate=1, per=10.0, type=commands.BucketType.guild)
    async def yoink_banner(self, ctx: commands.Context, *, user: discord.Member = None) -> None:
        """Steal someone's banner (but you can't steal the server profile banner)

        - Omit **[user]** to yoink your own banner
        - You can either ping someone or type a Discord username/server nickname exactly without the @
        """
        reply_embed: discord.Embed = self.bot.create_embed()
        if not user:
            author = await self.bot.fetch_user(ctx.author.id)
            if author.banner:
                await ctx.send(author.banner)
            else:
                reply_embed.description = f"{Icons.WARN} You have no banner set"
                await ctx.send(embed=reply_embed)
        else:
            found_user = await self.bot.fetch_user(user.id)
            if found_user.banner:
                await ctx.send(found_user.banner)
            else:
                reply_embed.description = f"{Icons.WARN} This user has no banner set"
                await ctx.send(embed=reply_embed)

    @yoink.command(name="profile")
    async def yoink_profile(self, ctx: commands.Context, *, user: discord.Member = None) -> None:
        """Steal someone's user profile picture

        - Omit **[user]** to yoink your own banner
        - You can either ping someone or type a Discord username/server nickname exactly without the @
        """
        reply_embed: discord.Embed = self.bot.create_embed()
        if not user:
            if ctx.author.avatar:
                await ctx.send(ctx.author.avatar)
            else:
                reply_embed.description = f"{Icons.WARN} You have no user profile picture set"
                await ctx.send(embed=reply_embed)
        else:
            if user.avatar:
                await ctx.send(user.avatar)
            else:
                reply_embed.description = f"{Icons.WARN} This user has no profile picture set"
                await ctx.send(embed=reply_embed)

    @yoink.command(name="server")
    async def yoink_server(self, ctx: commands.Context, asset_type: str = "") -> None:
        """Steal whatever image you want from the server

        - Available options: icon, banner, and invite
        """
        reply_embed: discord.Embed = self.bot.create_embed()
        match asset_type.lower():
            case "icon":
                if ctx.guild.icon is not None:
                    await ctx.send(ctx.guild.icon)
                else:
                    reply_embed.description = f"{Icons.WARN} This server has no icon set"
                    await ctx.send(embed=reply_embed)
            case "banner":
                if ctx.guild.banner is not None:
                    await ctx.send(ctx.guild.banner)
                else:
                    reply_embed.description = f"{Icons.WARN} This server has no banner set"
                    await ctx.send(embed=reply_embed)
            case "invite":
                if ctx.guild.splash is not None:
                    await ctx.send(ctx.guild.splash)
                else:
                    reply_embed.description = f"{Icons.WARN} This server has no invite background set"
                    await ctx.send(embed=reply_embed)
            case _:
                reply_embed.description = f"{Icons.ERROR} Unknown option (or it wasn't given). Use `{self.bot.command_prefix}help yoink server` to view all available server assets."
                await ctx.send(embed=reply_embed)

    @yoink.error
    @yoink_banner.error
    @yoink_profile.error
    @yoink_server.error
    async def yoink_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed: discord.Embed = self.bot.create_embed()
        if isinstance(error, commands.MemberNotFound):
            error_embed.description = f"{Icons.ERROR} No one with that username or nickname was found."
            await ctx.send(embed=error_embed)
        elif isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @commands.command(name="invite")
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.channel)
    async def invite_link(self, ctx: commands.Context) -> None:
        """Show the invite link for PinguBot"""
        invite_link = (
            "https://discord.com/api/oauth2/authorize?client_id=391016254938546188&permissions=3525696&scope=bot"
        )
        embed: discord.Embed = self.bot.create_embed(description=f"Invite me by clicking [here]({invite_link})")
        await ctx.send(embed=embed)

    @commands.command(name="bots")
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.channel)
    async def show_bots(self, ctx: commands.Context) -> None:
        """Show all the bots in the server"""
        bot_list = [
            f"{self.get_status_icon(member.status)} {member.mention}"
            for member in filter(self.is_bot, ctx.guild.members)
        ]
        embed: discord.Embed = self.bot.create_embed(
            title=f"Bots Found: {len(bot_list)}", description="\n".join(bot_list)
        )
        await ctx.send(embed=embed)

    def is_bot(self, member: discord.Member) -> bool:
        """Helper method to filter out regular Discord users"""
        if member.bot:
            return True
        return False

    def get_status_icon(self, status: discord.Status) -> str:
        """Helper method to display a bot's status"""
        if status in (discord.Status.offline, discord.Status.invisible):
            return "🔴"
        return "🟢"

    async def get_or_create(self, session: AsyncSession, model, defaults=None, **kwargs) -> Nickname:
        """Helper function to check if a record exists or not and create one if it does not"""
        instance = await session.execute(select(model).filter_by(**kwargs))
        instance = instance.scalar_one_or_none()
        if instance:
            return instance
        else:
            kwargs |= defaults or {}
            instance = model(**kwargs)
            try:
                await session.add(instance)
            except Exception:
                instance = await session.execute(select(model).filter_by(**kwargs))
                instance = instance.scalar_one()
                return instance
            else:
                return instance

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        """Automation process for a special person"""
        await self.bot.wait_until_ready()

        session: AsyncSession
        async with async_session() as session:
            async with session.begin():
                result = await self.get_or_create(session, Nickname, guild_id=member.guild.id)
                result.nicknames[str(member.id)] = member.nick
                await session.commit()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Automation process for a special person"""
        await self.bot.wait_until_ready()

        if member.guild.id == 143909103951937536 and member.id in (1069703628912332860, 996500705617657978):
            roles = [
                member.guild.get_role(868357561592725534),
                member.guild.get_role(273671436281970689),
                member.guild.get_role(667785085826891806),
                member.guild.get_role(1086394159700643890),
                member.guild.get_role(517877827123675156),
                member.guild.get_role(1043579702998220900),
            ]
            # await member.add_roles(*roles, atomic=False)

            session: AsyncSession
            async with async_session() as session:
                async with session.begin():
                    result = await self.get_or_create(session, Nickname, guild_id=member.guild.id)
                    name: str | None = result.nicknames[str(member.id)] if str(member.id) in result.nicknames else None
            await member.edit(nick=name, roles=roles)


async def setup(bot: commands.Bot):
    await bot.add_cog(Misc(bot))
