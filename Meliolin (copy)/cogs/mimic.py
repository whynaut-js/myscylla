import discord
from discord.ext import commands
from utils.checks import is_server_owner
from utils.webhook import get_relay_webhook

class Mimic(commands.Cog):
    """Send a message that appears to come from another member. Restricted to server/bot owner."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="mimic", aliases=["mim"])
    @is_server_owner()
    async def mimic(self, ctx, member: discord.Member, *, message: str):
        """Send a message styled as another member. Example: ~mimic @rey hi"""
        webhook = await get_relay_webhook(self.bot, ctx.channel)
        await webhook.send(
            message,
            username=member.display_name,
            avatar_url=member.display_avatar.url,
            allowed_mentions=discord.AllowedMentions.none(),
        )

        try:
            await ctx.message.delete()
        except discord.Forbidden:
            pass

        snipe_cog = self.bot.get_cog("Snipe")
        if snipe_cog:
            snipe_cog.deleted.pop(ctx.channel.id, None)
            snipe_cog.edited.pop(ctx.channel.id, None)
            snipe_cog.reactions_removed.pop(ctx.channel.id, None)

async def setup(bot):
    await bot.add_cog(Mimic(bot))
