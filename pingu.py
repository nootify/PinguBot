import discord
import pingutoken
import platform
import sys
import traceback
from discord.ext import commands


def main():
    """Main driver program to run the bot.

    Do not publish the ID nor auth token!
    """
    # The default values that are used when the bot initially starts up
    current = {'activity': discord.Activity(type=discord.ActivityType.watching, name='Pingu in the City'),
               'prefix': '%',
               'status': discord.Status.online,
               'version': '1.20.0001'}
    default = {'description': 'Noot noot',
               'prefix': '%'}

    # Instantiate the bot instance and attach said values to the instance
    pingu = commands.Bot(command_prefix=default['prefix'], description=default['description'])
    pingu.current = current
    pingu.default = default

    # Automatically load all essential cogs onto the bot
    # 'Cog modules' require dot notation to access child folders
    default_cogs = ['admin', 'clown', 'music', 'help']
    for cog in default_cogs:
        pingu.load_extension(f'cogs.{cog}')

    @pingu.event
    async def on_command_error(ctx, error):
        print(error)
        if isinstance(error, commands.CommandNotFound) or isinstance(error, commands.MissingRequiredArgument):
            # This prevents spam from malformed syntax or typos on a command by a user.
            return
        if isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f':rotating_light: Stop! You violated the law! Wait {error.retry_after:0.2f} second(s).')
        elif isinstance(error, commands.CheckFailure):
            await ctx.send(':x: You are missing permission(s) to run the command.')
        elif isinstance(error, commands.CommandError):
            try:
                await ctx.send(f':x: {error}')
            except discord.Forbidden as e:
                print('\nException caused by user {0.author} in guild {0.guild} with command {1.qualified_name}:\n{2}\n{3}'.format(
                        ctx.message, ctx.command, error, e), file=sys.stderr)
        elif isinstance(error, commands.CommandInvokeError):
            print('\nException caused by user {0.author} in guild {0.guild} with command {1.qualified_name}:'.format(
                ctx.message, ctx.command), file=sys.stderr)
            traceback.print_tb(error.original.__traceback__)
            print('{0.__class__.__name__}: {0}'.format(error.original), file=sys.stderr)

    @pingu.event
    async def on_message(message):
        """This runs every time a message is sent."""
        # Ignore responses from other bots (unable to distinguish from self-bots, who are breaking Discord ToS)
        # or a response from a private message (DMs) and continue to process queries
        if message.author.bot or message.guild is None:
            return

        await pingu.process_commands(message)

    @pingu.event
    async def on_ready():
        """This only runs after the bot is ready to process commands.

        These are the various discord activities available for the bot:
        Gaming:    discord.Game(name="some_game"))
        Streaming: discord.Streaming(name="some_stream", url="some_url"))
        Listening: discord.Activity(type=discord.ActivityType.listening, name="some_song"))
        Watching:  discord.Activity(type=discord.ActivityType.watching, name="some_movie"))
        """

        # Print relevant Pingu and library information to console
        # and sets initial Discord status
        total_guilds = len(pingu.guilds)
        total_users = len(set(pingu.get_all_members()))
        print('Logged in as: {0.user} | ID: {0.user.id}\nConnected to: {1} servers | {2} users'.format(
            pingu, total_guilds, total_users))
        print('Dependency Information: discord.py v{} | Python v{} | PinguBot v{}'.format(
            discord.__version__, platform.python_version(), pingu.current['version']))
        await pingu.change_presence(status=pingu.current['status'], activity=pingu.current['activity'])

    # Tokens are sacred
    pingu.run(pingutoken.secret)


if __name__ == "__main__":
    main()
