import discord
from discord.ext import commands

class AutoSend(commands.Cog):
    """Persistent auto-reply — unlike ~annoy, these messages stay (not deleted)."""

    def __init__(self, bot):
        self.bot = bot
        self.auto_send_configs = {}  # {channel_id: "message"}

    @commands.command(name="autosend")
    async def autosend(self, ctx, *, text: str):
        """Set a persistent auto-reply for this channel. Use ~autosend off to disable."""
        channel_id = ctx.channel.id

        if text.lower() == "off":
            if channel_id in self.auto_send_configs:
                del self.auto_send_configs[channel_id]
                await ctx.send("❌ Auto-send disabled for this channel.")
            else:
                await ctx.send("⚠️ Auto-send wasn't active in this channel.")
            return

        self.auto_send_configs[channel_id] = text
        await ctx.send(f'✅ Auto-send activated! Replying with: "{text}"')

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.channel.id in self.auto_send_configs:
            await message.channel.send(self.auto_send_configs[message.channel.id])

async def setup(bot):
    await bot.add_cog(AutoSend(bot))
