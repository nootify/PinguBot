"""This module is used to subclass the built-in Help class in discord.py so that
it uses embed formatting instead of a simple code block output.
"""
from datetime import datetime

import discord
from discord.ext import commands


class PinguHelp(commands.HelpCommand):
    """Base code taken from:
    https://gist.github.com/Rapptz/31a346ed1eb545ddeb0d451d81a60b3b

    Warning: This breaks if there are more than 25 cogs or subcommands.
    This is because the max number of fields in a single embed is 25.
    """
    COLOUR = discord.Colour.from_rgb(138, 181, 252)

    def get_description(self):
        """Returns a helpful tip for the user."""
        return f"Type {self.clean_prefix}{self.invoked_with} <command> for more info."

    def get_command_signature(self, command):
        return f"{command.qualified_name} {command.signature}"

    # Display a list of available commands of each loaded cog
    async def send_bot_help(self, mapping):
        embed = discord.Embed(title="Pingu Commands", colour=self.COLOUR)
        embed.description = self.get_description()

        # mapping is a dictionary of cogs paired with its associated commands
        for cog, available_commands in mapping.items():
            # Hide these modules from the help command
            if cog and cog.qualified_name in ["Jishaku"]:
                continue
            cog_name = "No Category" if cog is None else cog.qualified_name
            # Skip over cogs that are meant to be hidden (e.g. admin, help)
            # since they don't have a class docstring associated with them
            if cog and cog.description:
                # Sort the commands in a module
                filtered_commands = await self.filter_commands(available_commands, sort=True)
                if filtered_commands:
                    # Better than using a for loop and then stripping off the last comma
                    visible_commands = "`, `".join(command.name for command in filtered_commands)
                    desc = f"*{cog.description}*\nCommands: `{visible_commands}`"
                else:
                    desc = f"*{cog.description}*"
                embed.add_field(name=cog_name, value=desc, inline=False)

        # embed.set_author(name="Pingu Commands", icon_url="")
        embed.set_footer(text=f"Requested by: {self.context.author}",
                         icon_url=self.context.author.avatar_url)
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog):
        embed = discord.Embed(title=f"{cog.qualified_name} Module Commands", colour=self.COLOUR)
        if cog.description:
            embed.description = cog.description

        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        for command in filtered:
            embed.add_field(name=self.get_command_signature(command),
                            value=command.short_doc or "...",
                            inline=False)

        embed.set_footer(text=f"Requested by: {self.context.author}",
                         icon_url=self.context.author.avatar_url)
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        embed = discord.Embed(title=group.qualified_name,
                              colour=self.COLOUR,
                              timestamp=datetime.utcnow())
        if group.help:
            embed.description = group.help

        if isinstance(group, commands.Group):
            filtered = await self.filter_commands(group.commands, sort=True)
            for command in filtered:
                embed.add_field(name=self.get_command_signature(command),
                                value=command.short_doc or "...",
                                inline=False)

        embed.set_footer(text=f"Requested by: {self.context.author}",
                         icon_url=self.context.author.avatar_url)
        await self.get_destination().send(embed=embed)

    # Assign individual command help output to the group command help output
    send_command_help = send_group_help


class Help(commands.Cog): # pylint: disable=missing-class-docstring
    # This is a helper class used to load the PinguHelp class in as a cog
    # No class docstring is provided, otherwise it will be displayed within the embed as well
    # It is also a better alternative to removing the default help command entirely
    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        bot.help_command = PinguHelp()
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


def setup(bot):
    """Adds this module in as a cog to Pingu."""
    bot.add_cog(Help(bot))
