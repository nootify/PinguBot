"""This module is reserved for debugging purposes. Only the token owner may access any of the
commands. It's dangerous to allow everyone to access these, which is why the restriction is in
place.
"""
import asyncio
import logging
import platform
from datetime import datetime

import discord
import humanize
import psutil
from discord.ext import commands

import settings


class Admin(commands.Cog):  # pylint: disable=missing-class-docstring
    # Only a true noot noot can use this
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)
        self.ran_once = False

    async def cog_check(self, ctx): # pylint: disable=invalid-overridden-method
        """Checks if the user is the bot owner for every command.
        Note: The built-in method Bot.is_owner() is a coroutine and must be awaited.
        """
        return await self.bot.is_owner(ctx.author)

    def cog_unload(self):
        self.ran_once = False

    @commands.command(name="shutdown", hidden=True)
    async def shutdown_bot(self, ctx):
        """Shutdown the bot instance. Pingu must be manually rebooted server-side when issued."""
        # Grab id of user that issued the command
        original_issuer = ctx.message.author.id
        await ctx.send(":zzz: Shutdown this Pingu instance (y/N)?")

        # Used to confirm if the message received is indeed the user that sent it
        def confirm_user(msg):
            response = msg.content.lower()
            return msg.author.id == original_issuer and response in ["y", "yes", "n", "no"]

        # Check for acceptable input
        try:
            response = await self.bot.wait_for("message", timeout=10.0, check=confirm_user)
        except asyncio.TimeoutError:
            await ctx.send(f"{self.bot.icons['fail']} Shutdown attempt timed out.")
        else:
            # Respond as necessary to the input
            user_response = response.content.lower()
            if user_response in ["y", "yes"]:
                await ctx.send(f"{self.bot.icons['success']} Attempting shutdown...")
                await self.bot.db.close()
                await self.bot.close()
                self.log.warning("Shutdown issued in server '%s' (id: %s) by user '%s' (id: %s).",
                                 ctx.guild, ctx.guild.id, ctx.message.author, ctx.message.author.id)
            else:
                await ctx.send(f"{self.bot.icons['fail']} Shutdown aborted by user.")

    @commands.command(name="stats", aliases=["info"], hidden=True)
    async def debug_info(self, ctx): # pylint: disable=too-many-locals
        """Show at-a-glance information about Pingu."""
        # Embed header and footer
        py_version = platform.python_version()
        dpy_version = discord.__version__
        bot_ping = round(self.bot.latency, 4) * 1000 # This is in ms
        ping_icon = "\N{large green circle}"
        if int(bot_ping) >= 200:
            ping_icon = "\N{large red circle}"
        elif int(bot_ping) >= 100:
            ping_icon = "\N{large yellow circle}"

        # Pingu
        bot_ref = self.bot.user
        pingu_version = settings.VERSION
        bot_owner = self.bot.get_user(self.bot.owner_id)

        # System
        os_name = f"{platform.system()} {platform.release()}"
        total_cores = psutil.cpu_count()
        physical_cores = psutil.cpu_count(logical=False)
        sys_mem = psutil.virtual_memory()
        sys_mem_total = humanize.naturalsize(sys_mem.total)
        sys_mem_available = humanize.naturalsize(sys_mem.available)

        # Quick Overview
        total_servers = len(self.bot.guilds)
        total_channels = sum(1 for channel in self.bot.get_all_channels())
        total_unique_users = len(self.bot.users)
        total_cogs = len(self.bot.cogs)
        total_commands = sum(1 for command in self.bot.walk_commands())

        # Usage
        system_cpu_percent = psutil.cpu_percent()
        if not self.ran_once:
            self.ran_once = True
            system_cpu_percent = psutil.cpu_percent()

        # Bot usage percentages
        proc = psutil.Process()
        with proc.oneshot():
            # Memory used by the bot in bytes
            mem = proc.memory_full_info()
            all_mem_used = humanize.naturalsize(mem.rss) # Physical memory
            # all_vmem_used = humanize.naturalsize(mem.vms) # Virtual memory
            main_mem_used = humanize.naturalsize(mem.uss)

            # Percentage calculations
            bot_cpu_percent = proc.cpu_percent()
            main_mem_percent = (mem.uss / sys_mem.total) * 100 # Memory usage of main thread
            all_mem_percent = (mem.rss / sys_mem.total) * 100 # Memory usage of all threads
            sys_mem_percent = 100 - sys_mem.percent # Memory usage of the OS

        # Processes
        bot_threads = [str(thread.id) for thread in proc.threads()]
        bot_threads.sort()

        # Uptime calculations
        diff = datetime.now() - self.bot.boot_time
        hrs, remainder = divmod(int(diff.total_seconds()), 3600)
        mins, secs = divmod(remainder, 60)
        days, hrs = divmod(hrs, 24)
        total_uptime = f"**{days}** days, **{hrs}** hours,\n**{mins}** minutes, **{secs}** seconds"

        # Stats embed message
        stats_embed = discord.Embed(title=None, description=None, colour=self.bot.embed_colour)
        stats_embed.set_author(name="About Me", icon_url=ctx.me.avatar_url)
        stats_embed.set_footer(
            text="{} Pinged in: {:.2f} ms • Running on Python {} and Discord.py {}".format(
                ping_icon, bot_ping, py_version, dpy_version))
        stats_fields = [
            ("Pingu",
             "**Name:** {}\n**Tag:** {}\n**ID:** {}\n**Version:** {}\n**Owner**\n{}#{}".format(
                 bot_ref.name, bot_ref.discriminator, bot_ref.id,
                 pingu_version, bot_owner.name, bot_owner.discriminator), True),
            ("System",
             "**OS**\n{}\n**CPU Cores**\nLogical: {}, Physical: {}\n**RAM**\nTotal: {}".format(
                 os_name, total_cores, physical_cores, sys_mem_total), True),
            ("Quick Overview",
             "**Guilds:** {}\n**Channels:** {}\n**Users:** {}\n**Cogs:** {}\n**Commands:** {}".format(
                 total_servers, total_channels, total_unique_users,
                 total_cogs, total_commands), True),
            ("Usage",
             "**CPU**\nSystem: {:.02f}%\nBot: {:.02f}%\n**RAM**\nMain: {} ({:.02f}%)\nAll: {} ({:.02f}%)\nAvailable: {} ({:.02f}%)".format(
                 system_cpu_percent, bot_cpu_percent,
                 main_mem_used, main_mem_percent,
                 all_mem_used, all_mem_percent,
                 sys_mem_available, sys_mem_percent), True),
            ("Processes",
             "**PIDs**\n{}\n**Threads**\n{}\n**Uptime**\n{}".format(
                 ", ".join(thread_id for thread_id in bot_threads),
                 len(bot_threads), total_uptime), True),
            ("Sharding",
             "Sharding not enabled", True)
        ]
        for name, value, inline in stats_fields:
            stats_embed.add_field(name=name, value=value, inline=inline)
        await ctx.send(embed=stats_embed)


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Admin(bot))
