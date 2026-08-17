import discord
from discord.ext import commands
from utils.permissions import can_ping_role, check_pingrole_cooldown, record_pingrole_use
from utils.webhook import get_relay_webhook

class PingRole(commands.Cog):
    """Ping a specific role through the bot, gated by bot-perms."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="pingrole", aliases=["pr"])
    async def pingrole(self, ctx, role: discord.Role, *, message: str = ""):
        """Ping a role via the bot, if you have permission. Example: ~pingrole @Events Starting soon!"""
        if role.id == ctx.guild.default_role.id:
            await ctx.send("You can't ping @everyone through this command.")
            return

        allowed = await can_ping_role(self.bot, ctx.guild, ctx.author, role)
        if not allowed:
            await ctx.send(f"You don't have permission to ping {role.mention}.")
            return

        can_use, wait_seconds = await check_pingrole_cooldown(self.bot, ctx.guild, ctx.author, role)
        if not can_use:
            hours, remainder = divmod(wait_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            await ctx.send(f"You can ping {role.mention} again in {hours}h {minutes}m {seconds}s.")
            return

        content = f"{role.mention} {message}".strip()

        try:
            webhook = await get_relay_webhook(self.bot, ctx.channel)
            await webhook.send(
                content,
                username=ctx.author.display_name,
                avatar_url=ctx.author.display_avatar.url,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=[role], users=False),
            )
            await ctx.message.delete()
        except discord.Forbidden:
            await ctx.send(
                content,
                allowed_mentions=discord.AllowedMentions(everyone=False, roles=[role], users=False),
            )

        await record_pingrole_use(self.bot, ctx.guild, ctx.author, role)

async def setup(bot):
    await bot.add_cog(PingRole(bot))
