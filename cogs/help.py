from difflib import get_close_matches

import discord
from discord.ext import commands

from common.settings import Icons


class PinguHelp(commands.HelpCommand):
    """Clean embed-style help pages"""

    def __init__(self, colour, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.embed_colour = colour

    def get_description(self):
        return f"Use {self.clean_prefix}{self.invoked_with} `[command]` to see more info."

    def get_command_signature(self, command):
        return f"{command.qualified_name} {command.signature}"

    def get_footer(self):
        return "Commands that have: <...> are needed • [...] are optional"

    def get_help_text(self, command):
        if command.aliases and command.help:
            aliases = "`, `".join(alias for alias in command.aliases)
            return f"**Aliases:** `{aliases}`\n{command.help}"
        elif command.aliases:
            aliases = "`, `".join(alias for alias in command.aliases)
            return f"**Aliases:** `{aliases}`"
        elif command.help:
            return command.help
        return "..."

    def get_help_short_doc(self, command):
        if command.aliases and command.short_doc:
            aliases = "`, `".join(alias for alias in command.aliases)
            return f"**Aliases:** `{aliases}`\n{command.short_doc}"
        elif command.aliases:
            aliases = "`, `".join(alias for alias in command.aliases)
            return f"**Aliases:** `{aliases}`"
        elif command.short_doc:
            return command.short_doc
        return "..."

    def get_help_embed(self, command):
        help_embed = discord.Embed(
            title=self.get_command_signature(command),
            description=self.get_help_text(command),
            colour=self.embed_colour,
        )
        help_embed.set_footer(text=self.get_footer())
        return help_embed

    async def send_bot_help(self, mapping):
        embed = discord.Embed(title="Pingu Commands", colour=self.embed_colour)
        embed.description = self.get_description()
        embed.set_footer(text=self.get_footer())

        # mapping != dict
        for cog, cog_commands in mapping.items():
            # Skip cogs with no class docstring
            if cog and cog.description:
                visible_commands = await self.filter_commands(cog_commands, sort=True)
                # Skip cogs with no visible commands (either hidden or denied because of cog_check)
                if visible_commands:
                    formatted_commands = "`, `".join(command.name for command in visible_commands)
                    cog_help = f"{cog.description}\n`{formatted_commands}`"
                    embed.add_field(name=cog.qualified_name, value=cog_help, inline=False)
        await self.get_destination().send(embed=embed)

    async def send_cog_help(self, cog):
        embed = discord.Embed(title=f"{cog.qualified_name} Commands", colour=self.embed_colour)
        if cog.description:
            embed.description = cog.description
        embed.set_footer(text=self.get_footer())

        visible_commands = await self.filter_commands(cog.get_commands(), sort=True)
        for command in visible_commands:
            embed.add_field(
                name=self.get_command_signature(command),
                value=self.get_help_short_doc(command),
                inline=False,
            )
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        embed = self.get_help_embed(group)
        visible_commands = await self.filter_commands(group.commands, sort=True)
        for command in visible_commands:
            embed.add_field(
                name=self.get_command_signature(command),
                value=self.get_help_short_doc(command),
                inline=False,
            )
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command):
        embed = self.get_help_embed(command)
        await self.get_destination().send(embed=embed)

    def command_not_found(self, string: str):
        commands_list = [str(command) for command in self.context.bot.commands]
        suggestions = "`\n- `".join(get_close_matches(string, commands_list))
        if suggestions:
            return f"There's no command called `{string}`, but did you mean...\n- `{suggestions}`"
        else:
            return f"{Icons.ERROR} There's no command called `{string}`"

    def subcommand_not_found(self, command, string: str):
        return f"{Icons.ERROR} There's no command called `{command}` `{string}`."


# Helper class used to load in the PinguHelp class as a cog
# Do not put a class docstring because it will show redundant information
class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._original_help_command = bot.help_command
        bot.help_command = PinguHelp(self.bot.embed_colour)
        bot.help_command.cog = self

    def cog_unload(self):
        self.bot.help_command = self._original_help_command


def setup(bot):
    bot.add_cog(Help(bot))
