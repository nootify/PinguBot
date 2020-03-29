from discord.ext import commands


class Admin(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        """This check is applied at a cog level, meaning the check is applied
        to every command.

        Note: Bot.is_owner() is a coroutine and so must be awaited.
        """
        return await self.bot.is_owner(ctx.author)

    @commands.command(name='shutdown', hidden=True)
    @commands.cooldown(1, 5, commands.BucketType.default)
    async def close_bot(self, ctx):
        """Shutdown the bot instance. PinguBot must be manually rebooted server-side if issued."""
        try:
            await self.bot.close()
        except Exception as e:
            await ctx.send(f'\N{BROKEN HEART} {type(e).__name__}: {e}')

    @commands.command(name='load', hidden=True)
    @commands.cooldown(1, 5, commands.BucketType.default)
    async def load_cog(self, ctx, *, module: str):
        """Loads a module."""
        try:
            self.bot.load_extension(f'cogs.{module}')
        except Exception as e:
            await ctx.send(f'\N{BROKEN HEART} {type(e).__name__}: {e}')
        else:
            await ctx.send('\N{check mark}')

    @commands.command(name='reload', hidden=True)
    @commands.cooldown(1, 5, commands.BucketType.default)
    async def reload_cog(self, ctx, *, module: str):
        """Reloads a module."""
        try:
            self.bot.reload_extension(f'cogs.{module}')
        except Exception as e:
            await ctx.send(f'\N{BROKEN HEART} {type(e).__name__}: {e}')
        else:
            await ctx.send('\N{check mark}')

    @commands.command(name='unload', hidden=True)
    @commands.cooldown(1, 5, commands.BucketType.default)
    async def unload_cog(self, ctx, *, module: str):
        """Unloads a module."""
        try:
            self.bot.unload_extension(f'cogs.{module}')
        except Exception as e:
            await ctx.send(f'\N{BROKEN HEART} {type(e).__name__}: {e}')
        else:
            await ctx.send('\N{check mark}')


def setup(bot):
    bot.add_cog(Admin(bot))
