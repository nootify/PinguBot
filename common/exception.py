from discord.ext import commands


class PinguException(commands.BadArgument):
    """Base exception class for all Pingu related errors."""

    pass


class MissingData(PinguException):
    """Error raised when there is missing cache data that a command needs to reference."""

    pass


class MissingClown(PinguException):
    """Error raised when the clown in a guild is missing."""

    pass


class MissingVoicePermissions(PinguException):
    """Error raised when the bot is missing permissions for a voice channel."""

    pass
