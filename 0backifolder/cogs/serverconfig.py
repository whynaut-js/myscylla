import discord
from discord.ext import commands
from config.settings import PREFIX as DEFAULT_PREFIX

class ServerConfig(commands.Cog):
    """Server-specific bot configuration."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="prefix")
    async def prefix(self, ctx, new_prefix: str = None):
        """View or set this server's command prefix. Example: ~prefix !"""
        if new_prefix is None:
            row = await self.bot.db.fetchone(
                "SELECT prefix FROM guild_config WHERE guild_id = ?", (ctx.guild.id,)
            )
            current = row[0] if row and row[0] else DEFAULT_PREFIX
            await ctx.send(
                f"Current prefix: `{current}` "
                f"(the bot owner can also always use `~` or no prefix at all, regardless of this setting)"
            )
            return

        if ctx.author.id != ctx.guild.owner_id and not await ctx.bot.is_owner(ctx.author):
            await ctx.send("Only the server owner can change the prefix.")
            return

        if len(new_prefix) > 5:
            await ctx.send("Prefix must be 5 characters or fewer.")
            return

        await self.bot.db.execute(
            """
            INSERT INTO guild_config (guild_id, prefix) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET prefix = excluded.prefix
            """,
            (ctx.guild.id, new_prefix),
        )
        await ctx.send(f"Prefix set to `{new_prefix}` for this server.")

async def setup(bot):
    await bot.add_cog(ServerConfig(bot))
