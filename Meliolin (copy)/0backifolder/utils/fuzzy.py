import difflib
from discord.ext import commands

class FuzzyRole(commands.RoleConverter):
    """Same as discord.Role, but if there's no exact match (mention, ID,
    or exact name), falls back to finding the closest-spelled role name."""

    async def convert(self, ctx, argument):
        try:
            return await super().convert(ctx, argument)
        except commands.RoleNotFound:
            names = [r.name for r in ctx.guild.roles]
            matches = difflib.get_close_matches(argument, names, n=1, cutoff=0.5)
            if matches:
                for r in ctx.guild.roles:
                    if r.name == matches[0]:
                        return r
            raise commands.RoleNotFound(argument)
