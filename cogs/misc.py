import os
import logging
import platform

import discord
import psutil
from discord.ext import commands
from discord.utils import utcnow
from humanize import naturalsize

from common.utils import Icons


class Misc(commands.Cog):
    """Commands not in a specific category"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.proc = psutil.Process()
        self.proc.cpu_percent()

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

    @commands.command(name="yoink", aliases=["avatar", "pfp"])
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.member)
    async def yoink(self, ctx: commands.Context, *, user: discord.Member = None) -> None:
        """Steal someone's profile picture in the server

        - Omit **[user]** to yoink your own picture
        - You can either ping someone or type a Discord username/server nickname exactly without the @
        """
        if not user:
            await ctx.send(ctx.author.display_avatar)
        else:
            await ctx.send(user.display_avatar)

    @yoink.error
    async def yoink_error_handler(self, ctx: commands.Context, error) -> None:
        error_embed = self.bot.create_embed()
        if isinstance(error, commands.MemberNotFound):
            error_embed.description = f"{Icons.ERROR} No one with that username or nickname was found."
            await ctx.send(embed=error_embed)
            return
        if isinstance(error, commands.BadArgument):
            error_embed.description = f"{Icons.ERROR} {error}"
            await ctx.send(embed=error_embed)

    @commands.command(name="invite")
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.channel)
    async def invite_link(self, ctx: commands.Context) -> None:
        """Show the invite link for PinguBot"""
        invite_link = (
            "https://discord.com/api/oauth2/authorize?client_id=391016254938546188&permissions=3525696&scope=bot"
        )
        embed = self.bot.create_embed(description=f"Invite me by clicking [here]({invite_link})")
        await ctx.send(embed=embed)

    @commands.command(name="bots")
    @commands.cooldown(rate=1, per=1.0, type=commands.BucketType.channel)
    async def show_bots(self, ctx: commands.Context) -> None:
        """Show all the bots in the server"""
        bot_list = [
            f"{self.get_status_icon(member.status)} {member.mention}"
            for member in filter(self.is_bot, ctx.guild.members)
        ]
        embed = self.bot.create_embed(title=f"Bots Found: {len(bot_list)}", description="\n".join(bot_list))
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

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        """Automation process for a special person"""
        if member.guild.id == 143909103951937536 and member.id == 1069703628912332860:
            await member.edit(nick=os.environ.get("KYOHKO"))
            roles = [
                member.guild.get_role(868357561592725534),
                member.guild.get_role(273671436281970689),
                member.guild.get_role(667785085826891806),
                member.guild.get_role(1086394159700643890),
            ]
            await member.add_roles(*roles, atomic=False)


async def setup(bot):
    await bot.add_cog(Misc(bot))
