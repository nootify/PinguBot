import logging
import platform
from datetime import datetime

import discord
import humanize
import psutil
from discord.ext import commands


class Miscellaneous(commands.Cog):
    """Have a look at what's available"""

    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        # self.ran_once = False
        self.proc = psutil.Process()
        self.proc.cpu_percent()
        psutil.cpu_percent()

    @commands.command(name="stats", aliases=["about", "statistics", "status"])
    @commands.cooldown(rate=1, per=5.0, type=commands.BucketType.member)
    async def pingu_stats(self, ctx):
        """Show more info about Pingu"""
        # Embed header and footer
        py_version = platform.python_version()
        dpy_version = discord.__version__
        bot_ping = round(self.bot.latency, 4) * 1000  # This is in ms
        ping_icon = "\N{large green circle}"
        if int(bot_ping) >= 200:
            ping_icon = "\N{large red circle}"
        elif int(bot_ping) >= 100:
            ping_icon = "\N{large yellow circle}"

        # Pingu
        bot_account = self.bot.user
        bot_version = self.bot.pingu_version
        bot_owner = self.bot.get_user(self.bot.owner_id)

        # System
        os_name = f"{platform.system()} {platform.release()}"
        logical_cores = psutil.cpu_count()
        physical_cores = psutil.cpu_count(logical=False)
        sys_mem = psutil.virtual_memory()
        sys_mem_total = humanize.naturalsize(sys_mem.total)
        # sys_mem_available = humanize.naturalsize(sys_mem.available)

        # Quick Overview
        total_guilds = len(self.bot.guilds)
        total_channels = sum(1 for _ in self.bot.get_all_channels())
        total_users = len(self.bot.users)
        total_cogs = len(self.bot.cogs)
        total_commands = sum(1 for _ in self.bot.walk_commands())

        # Usage
        # system_cpu_percent = psutil.cpu_percent()
        # if not self.ran_once:
        #     self.ran_once = True
        #     system_cpu_percent = psutil.cpu_percent()

        with self.proc.oneshot():
            # Memory used by the bot in bytes
            mem = self.proc.memory_full_info()
            all_mem_used = humanize.naturalsize(mem.rss)  # Physical memory
            # all_vmem_used = humanize.naturalsize(mem.vms) # Virtual memory
            main_mem_used = humanize.naturalsize(mem.uss)

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
        diff = datetime.now() - self.bot.boot_time
        hrs, remainder = divmod(int(diff.total_seconds()), 3600)
        mins, secs = divmod(remainder, 60)
        days, hrs = divmod(hrs, 24)
        total_uptime = f"**{days}** days, **{hrs}** hours,\n" + f"**{mins}** minutes, **{secs}** seconds"

        # Embed stats into the message
        stats_embed = discord.Embed(title="", description="", colour=self.bot.embed_colour)
        stats_embed.set_author(name="Pingu Status", icon_url=ctx.me.avatar_url)
        stats_embed.set_footer(
            text=f"{ping_icon} Pinged in: {bot_ping:.2f} ms • Running on Python {py_version} and Discord.py {dpy_version}"
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

    @commands.command(name="yoink", aliases=["avatar", "pfp"])
    @commands.cooldown(rate=1, per=5.0, type=commands.BucketType.member)
    async def yoink(self, ctx: commands.Context, *, user: discord.Member = None):
        """Steal someone's profile picture

        - You can either @ someone directly or do it discreetly without an @ (see below).
        - Omit **[user]** to yoink your own picture.

        To do it discreetly:
        - Make sure to type their Discord username/nickname exactly since it's case sensitive
        """
        if not user:
            await ctx.send(ctx.message.author.avatar_url)
        else:
            await ctx.send(user.avatar_url)

    @yoink.error
    async def yoink_error(self, ctx: commands.Context, error):
        """Error handler for the yoink command"""
        ctx.local_error_only = True
        if isinstance(error, commands.BadArgument):
            error_icon = self.bot.icons["fail"]
            await ctx.send(f"{error_icon} User is not in the server or the discreet yoink didn't find anyone.")
            return


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Miscellaneous(bot))
