import asyncio
import logging
import os
import platform
from datetime import datetime

import psutil
from discord.ext import commands
from psutil._common import bytes2human


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.log = logging.getLogger(__name__)

    async def cog_check(self, ctx):
        """Checks if the user is the bot owner for every command.
        Note: The built-in method Bot.is_owner() is a coroutine and must be awaited.
        """
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="shutdown", hidden=True)
    async def shutdown_bot(self, ctx):
        """Shutdown the bot instance. Pingu must be manually rebooted server-side when issued."""
        # Grab id of user that issued the command
        original_issuer = ctx.message.author.id
        await ctx.send(":zzz: Shutdown this Pingu instance (y/N)?")

        # Used to confirm if the message received is indeed the user that sent it
        def confirm_user(msg):
            acceptable_input = ["y", "yes", "n", "no"]
            return (msg.content.lower() in acceptable_input) and msg.author.id == original_issuer

        # Check for acceptable input
        try:
            response = await self.bot.wait_for("message", timeout=10.0, check=confirm_user)
        except asyncio.TimeoutError:
            await ctx.send(f"{self.bot.icons['fail']} Shutdown attempt timed out.")
        else:
            # Respond as necessary to the input
            user_response = response.content
            if user_response == "y" or user_response == "yes":
                await ctx.send(f"{self.bot.icons['success']} Confirmation received. Attempting shutdown...")
                try:
                    await self.bot.close()
                    self.log.warning(f"Shutdown issued in server '{ctx.guild}' (id: {ctx.guild.id})"
                                     f" by user '{ctx.message.author}' (id: {ctx.message.author.id}).")
                except Exception as e:
                    await ctx.send(f"{self.bot.icons['fail']} {type(e).__name__}: {e}")
            else:
                await ctx.send(f"{self.bot.icons['fail']} Shutdown aborted by user.")

    @commands.command(name="load", hidden=True)
    async def load_cog(self, ctx, module: str):
        """Load a specified cog."""
        try:
            self.bot.load_extension(f"cogs.{module}")
        except Exception as e:
            await ctx.send(f"{self.bot.icons['fail']} {type(e).__name__}: {e}")
        else:
            await ctx.send(f"{self.bot.icons['success']} Operation was successful.")

    @commands.command(name="reload", hidden=True)
    async def reload_cog(self, ctx, module: str):
        """Reload a specified cog."""
        try:
            self.bot.reload_extension(f"cogs.{module}")
        except Exception as e:
            await ctx.send(f"{self.bot.icons['fail']} {type(e).__name__}: {e}")
        else:
            await ctx.send(f"{self.bot.icons['success']} Operation was successful.")

    @commands.command(name="unload", hidden=True)
    async def unload_cog(self, ctx, module: str):
        """Unload a specified cog."""
        try:
            self.bot.unload_extension(f"cogs.{module}")
        except Exception as e:
            await ctx.send(f"{self.bot.icons['fail']} {type(e).__name__}: {e}")
        else:
            await ctx.send(f"{self.bot.icons['success']} Operation was successful.")

    @commands.command(name="eval", hidden=True)
    async def debug_bot(self, ctx, *, expression: str):
        """Allows access to internal variables for debugging purposes."""
        try:
            result = eval(expression)
        except Exception as e:
            await ctx.send(f"{self.bot.icons['fail']} {type(e).__name__}: {e}")
        else:
            await ctx.send(f"{self.bot.icons['info']} {result}")

    @commands.command(name="usage", hidden=True)
    async def debug_info(self, ctx):
        cpu_usage = f"{psutil.cpu_percent():.02f}%"
        memory_usage = f"{bytes2human(psutil.virtual_memory().used)}"
        total_memory = f"{bytes2human(psutil.virtual_memory().total)}"
        usage_info = (f"{self.bot.icons['info']} Host Information\n"
                      f"CPU: {cpu_usage}\n"
                      f"RAM: {memory_usage}/{total_memory}\n"
                      f"OS: {platform.system()} {platform.release()}\n"
                      f"Running in: `{os.getcwd()}`\n"
                      f"Time: {datetime.utcnow()}")
        await ctx.send(usage_info)


def setup(bot):
    bot.add_cog(Admin(bot))
