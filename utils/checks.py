from discord.ext import commands
from config.owner import Me

def is_owner():
    async def predicate(ctx):
        return ctx.author.id in Me or await ctx.bot.is_owner(ctx.author)
    return commands.check(predicate)

def is_server_owner():
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        return ctx.guild is not None and ctx.author.id == ctx.guild.owner_id
    return commands.check(predicate)

def is_server_owner_or_botowner():
    async def predicate(ctx):
        if ctx.guild is None:
            return False
        if ctx.author.id == ctx.guild.owner_id:
            return True
        return await ctx.bot.is_owner(ctx.author)
    return commands.check(predicate)

def is_top_tier():
    """Bot owner, this server's owner, or an antinuke owner — nobody else."""
    async def predicate(ctx):
        if ctx.guild is None:
            return False
        if await ctx.bot.is_owner(ctx.author):
            return True
        if ctx.author.id == ctx.guild.owner_id:
            return True
        from utils import antinuke as an
        return await an.is_antinuke_owner(ctx.bot, ctx.guild, ctx.author)
    return commands.check(predicate)
